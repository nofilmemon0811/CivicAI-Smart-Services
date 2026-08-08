
from pathlib import Path
from models.complaint import Complaint
from utils.json_database import JSONDatabase
from config import Config

class ComplaintManager:
    categories = ["Water", "Road", "Waste", "Electricity", "Drainage", "Safety", "Other"]
    priorities = ["Low", "Medium", "High", "Critical"]
    statuses = ["Submitted", "AI Analyzed", "Assigned", "In Progress", "Resolved"]
    departments = [
        "Water & Drainage",
        "Roads & Infrastructure",
        "Waste Management",
        "Electricity Services",
        "Public Safety",
        "General Civic Services",
    ]

    def __init__(self):
        path = Path(Config.DATA_DIR) / "complaints.json"
        self.db = JSONDatabase(str(path), [])

    def _next_id(self):
        ids = []
        for item in self.db.get_all():
            try:
                ids.append(int(str(item["complaint_id"]).split("-")[-1]))
            except (KeyError, ValueError):
                pass
        return f"CMP-{(max(ids) + 1 if ids else 1):04d}"

    def create(self, description, location, name="", contact="", image=None, owner_username=""):
        complaint = Complaint.new(self._next_id(), description, location, name, contact, image, owner_username)
        self.db.add(complaint.to_dict())
        return complaint.to_dict()

    def get(self, complaint_id):
        return self.db.find(complaint_id.upper())

    def get_all(self):
        return self.db.get_all()

    def update(self, complaint_id, **changes):
        complaint = self.get(complaint_id)
        if not complaint:
            return None
        complaint.update(changes)
        if complaint.get("status") == "Resolved" and not complaint.get("resolved_at"):
            from datetime import datetime, timezone
            complaint["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return self.db.update(complaint_id.upper(), complaint)

    def attach_ai(self, complaint_id, analysis):
        return self.update(
            complaint_id,
            category=analysis["category"],
            priority=analysis["priority"],
            summary=analysis["summary"],
            assigned_department=analysis["department"],
            reason=analysis["reason"],
            confidence=analysis["confidence"],
            status="AI Analyzed",
        )

    def attach_duplicates(self, complaint_id, matches):
        return self.update(complaint_id, duplicate_matches=matches)

    def list_filtered(self, query="", category="", priority="", status="", department="", location=""):
        query = query.lower().strip()
        items = []
        for c in self.get_all():
            searchable = " ".join([
                c.get("complaint_id", ""), c.get("description", ""), c.get("location", "")
            ]).lower()
            if query and query not in searchable:
                continue
            if category and c.get("category") != category:
                continue
            if priority and c.get("priority") != priority:
                continue
            if status and c.get("status") != status:
                continue
            if department and c.get("assigned_department") != department:
                continue
            if location and location.lower() not in c.get("location", "").lower():
                continue
            items.append(c)
        return sorted(items, key=lambda x: x.get("date", ""), reverse=True)
