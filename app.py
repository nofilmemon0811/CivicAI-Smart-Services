import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from werkzeug.utils import secure_filename

from config import Config
from services.complaint_service import ComplaintManager
from services.ai_service import AIAnalyzer
from services.rag_service import RAGService
from services.analytics_service import AnalyticsService
from services.duplicate_service import DuplicateDetector
from services.auth_service import AuthService

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

manager = ComplaintManager()
ai = AIAnalyzer()
rag = RAGService()
analytics = AnalyticsService()
duplicates = DuplicateDetector()
auth = AuthService()

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Please sign in as an administrator.", "warning")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    return {
        "current_user": {
            "username": session.get("username"),
            "name": session.get("name"),
            "role": session.get("role"),
        }
    }


@app.route("/")
def index():
    stats = analytics.summary(manager.get_all())
    return render_template("index.html", stats=stats)


# ---------------- AUTH ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("username"):
        return redirect(url_for("dashboard" if session.get("role") == "citizen" else "admin"))

    if request.method == "POST":
        try:
            user = auth.register(
                request.form.get("username", ""),
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
            )
            session.update({
                "username": user["username"],
                "name": user["name"],
                "role": user["role"],
            })
            flash("Account created successfully.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as error:
            flash(str(error), "danger")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("username"):
        return redirect(url_for("dashboard" if session.get("role") == "citizen" else "admin"))

    if request.method == "POST":
        user = auth.authenticate(
            request.form.get("username", ""),
            request.form.get("password", ""),
        )
        if user:
            session.clear()
            session.update({
                "username": user["username"],
                "name": user.get("name", user["username"]),
                "role": user.get("role", "citizen"),
            })
            next_url = request.args.get("next") or request.form.get("next")
            if user.get("role") == "admin":
                return redirect(url_for("admin"))
            return redirect(next_url if next_url and next_url.startswith("/") else url_for("dashboard"))
        flash("Invalid username or password.", "danger")

    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "admin":
        return redirect(url_for("admin"))
    username = session["username"]
    complaints = [
        c for c in manager.get_all()
        if c.get("owner_username") == username
    ]
    complaints.sort(key=lambda x: x.get("date", ""), reverse=True)
    stats = analytics.summary(complaints)
    return render_template("dashboard.html", complaints=complaints, stats=stats)


# ---------------- COMPLAINTS ----------------

@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "GET":
        return render_template("report.html")

    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    name = request.form.get("name", "").strip()
    contact = request.form.get("contact", "").strip()

    if len(description) < 10:
        flash("Please provide at least 10 characters describing the problem.", "danger")
        return render_template("report.html")
    if not location:
        flash("Please provide the problem location.", "danger")
        return render_template("report.html")

    image_name = None
    image_path = None
    image = request.files.get("image")
    if image and image.filename:
        if not allowed_file(image.filename):
            flash("Only PNG, JPG, JPEG and WEBP are allowed.", "danger")
            return render_template("report.html")
        image_name = secure_filename(image.filename)
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_name)
        image.save(image_path)

    owner_username = session.get("username", "")
    if not name and session.get("name"):
        name = session["name"]

    complaint = manager.create(
        description=description,
        location=location,
        name=name,
        contact=contact,
        image=image_name,
        owner_username=owner_username,
    )

    try:
        analysis = ai.analyze(description, location, image_path=image_path)
        complaint = manager.attach_ai(complaint["complaint_id"], analysis)
        ai_message = "AI analysis completed, including risk assessment."
    except Exception as error:
        print(f"AI analysis error: {error}")
        ai_message = "Complaint saved. AI analysis is temporarily unavailable."

    try:
        duplicate_matches = duplicates.find(complaint, manager.get_all())
        manager.attach_duplicates(complaint["complaint_id"], duplicate_matches)
    except Exception as error:
        print(f"Duplicate detection error: {error}")

    flash(ai_message, "success" if "completed" in ai_message else "warning")
    return redirect(url_for("complaint_detail", complaint_id=complaint["complaint_id"]))


@app.route("/track", methods=["GET", "POST"])
def track():
    complaint = None
    if request.method == "POST":
        complaint_id = request.form.get("complaint_id", "").strip().upper()
        complaint = manager.get(complaint_id)
        if not complaint:
            flash("No complaint found with that ID.", "danger")
    return render_template("track.html", complaint=complaint)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/complaint/<complaint_id>")
def complaint_detail(complaint_id):
    complaint = manager.get(complaint_id.upper())
    if not complaint:
        return render_template("not_found.html", title="Complaint Not Found"), 404
    return render_template("complaint.html", complaint=complaint)


# ---------------- ADMIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = auth.authenticate(
            request.form.get("username", ""),
            request.form.get("password", ""),
        )
        if user and user.get("role") == "admin":
            session.clear()
            session.update({
                "username": user["username"],
                "name": user.get("name", "Administrator"),
                "role": "admin",
            })
            return redirect(url_for("admin"))
        flash("Invalid administrator credentials.", "danger")
    return render_template("login.html", admin_mode=True)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():
    complaints = manager.list_filtered(
        query=request.args.get("q", ""),
        category=request.args.get("category", ""),
        priority=request.args.get("priority", ""),
        status=request.args.get("status", ""),
        department=request.args.get("department", ""),
        location=request.args.get("location", ""),
    )
    all_complaints = manager.get_all()
    stats = analytics.full(all_complaints)
    return render_template(
        "admin.html",
        complaints=complaints,
        stats=stats,
        categories=manager.categories,
        priorities=manager.priorities,
        statuses=manager.statuses,
        departments=manager.departments,
    )


@app.post("/admin/update/<complaint_id>")
@admin_required
def admin_update(complaint_id):
    status = request.form.get("status")
    department = request.form.get("department")
    if status not in manager.statuses:
        flash("Invalid status.", "danger")
        return redirect(url_for("admin"))
    manager.update(complaint_id, status=status, assigned_department=department)
    flash(f"{complaint_id} updated successfully.", "success")
    return redirect(request.referrer or url_for("admin"))


# ---------------- RAG ----------------

@app.route("/assistant", methods=["GET", "POST"])
def assistant():
    answer = None
    sources = []
    question = ""
    provider = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if not question:
            flash("Please enter a question.", "danger")
        else:
            try:
                result = rag.ask(question)
                answer, sources = result[0], result[1]
                provider = result[2] if len(result) > 2 else "unknown"
            except Exception as error:
                print(f"RAG assistant error: {error}")
                answer = "The CivicAI assistant could not process your question right now."

    return render_template(
        "assistant.html",
        answer=answer,
        sources=sources,
        question=question,
        provider=provider
    )


# ---------------- AI APIs ----------------

@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    description = str(data.get("description", "")).strip()
    location = str(data.get("location", "")).strip()
    if len(description) < 10:
        return jsonify({"error": "Description must contain at least 10 characters."}), 400
    try:
        return jsonify(ai.analyze(description, location))
    except Exception as error:
        print(f"AI API error: {error}")
        return jsonify({"error": "AI analysis is temporarily unavailable."}), 503


@app.post("/api/improve")
def api_improve():
    data = request.get_json(silent=True) or {}
    description = str(data.get("description", "")).strip()
    location = str(data.get("location", "")).strip()
    if len(description) < 5:
        return jsonify({"error": "Please enter a little more detail first."}), 400
    try:
        return jsonify({"improved": ai.improve_complaint(description, location)})
    except Exception as error:
        print(f"AI improvement error: {error}")
        return jsonify({"error": "AI improvement is temporarily unavailable."}), 503


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"error": "Please enter a question."}), 400

    try:
        result = rag.ask(question)
        answer, sources = result[0], result[1]
        provider = result[2] if len(result) > 2 else "unknown"
        return jsonify({
            "answer": answer,
            "sources": sources,
            "provider": provider
        })
    except Exception as error:
        print(f"RAG API error: {error}")
        return jsonify({
            "answer": "The CivicAI assistant could not process your question right now.",
            "sources": [],
            "provider": "error"
        }), 200


@app.post("/api/ai-insights")
@admin_required
def api_ai_insights():
    try:
        stats = analytics.full(manager.get_all())
        return jsonify({"insight": ai.generate_insights(stats)})
    except Exception as error:
        print(f"AI insight error: {error}")
        return jsonify({"error": "AI insights are temporarily unavailable."}), 503


@app.post("/api/copilot")
@admin_required
def api_copilot():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"error": "Please enter an admin question."}), 400
    try:
        return jsonify({"answer": ai.copilot(question, manager.get_all())})
    except Exception as error:
        print(f"Admin copilot error: {error}")
        return jsonify({"error": "Admin Copilot is temporarily unavailable."}), 503


@app.get("/api/stats")
def api_stats():
    return jsonify(analytics.full(manager.get_all()))


# ---------------- ERRORS ----------------

@app.errorhandler(413)
def too_large(_):
    return render_template("error.html", message="The uploaded file is too large."), 413


@app.errorhandler(500)
def server_error(_):
    return render_template("error.html", message="Something went wrong. Please try again."), 500


if __name__ == "__main__":
    app.run(debug=Config.DEBUG)
