import base64
import json
import re
from pathlib import Path

import requests

from config import Config


class AIAnalyzer:
    categories = ["Water", "Road", "Waste", "Electricity", "Drainage", "Safety", "Other"]
    priorities = ["Low", "Medium", "High", "Critical"]
    departments = {
        "Water": "Water & Drainage",
        "Drainage": "Water & Drainage",
        "Road": "Roads & Infrastructure",
        "Waste": "Waste Management",
        "Electricity": "Electricity Services",
        "Safety": "Public Safety",
        "Other": "General Civic Services",
    }

    def _prompt(self, description, location, has_image=False):
        return f"""
You are CivicAI, an AI assistant for a civic complaint management system.
Analyze the citizen complaint and return ONLY valid JSON.

Required keys:
category, priority, summary, department, reason, confidence,
risk_level, public_impact, recommended_response_time, risk_reason.

Allowed category values: {", ".join(self.categories)}
Allowed priority values: {", ".join(self.priorities)}
Allowed risk_level values: Low, Medium, High, Critical
Allowed public_impact values: Low, Medium, High
Recommended response time must be a short human-readable value such as "24 hours", "8 hours", "2 hours", or "Immediate review".
Department should normally match the category mapping.
Confidence must be Low, Medium, or High.
Do not invent facts. Base risk only on the reported information.
If an image is supplied, use only visible evidence from the image and say so in risk_reason when relevant.
Image supplied: {"yes" if has_image else "no"}

Complaint:
{description}

Location:
{location}
""".strip()

    def _fallback(self, description):
        text = description.lower()
        rules = [
            (["water", "leak", "pipe", "tap"], "Water"),
            (["drain", "sewage", "flood", "sewer"], "Drainage"),
            (["garbage", "waste", "trash", "bin"], "Waste"),
            (["streetlight", "electricity", "power", "pole", "light"], "Electricity"),
            (["road", "pothole", "street", "traffic"], "Road"),
            (["unsafe", "danger", "crime", "security"], "Safety"),
        ]
        category = "Other"
        for words, candidate in rules:
            if any(w in text for w in words):
                category = candidate
                break

        critical_terms = ["huge", "major", "danger", "accident", "traffic", "flood", "unsafe", "emergency"]
        high_terms = ["broken", "overflow", "leak", "blocked", "damaged"]
        if any(w in text for w in critical_terms):
            priority = "Critical"
        elif any(w in text for w in high_terms):
            priority = "High"
        else:
            priority = "Medium"

        risk_map = {"Critical": "Critical", "High": "High", "Medium": "Medium", "Low": "Low"}
        response_map = {"Critical": "Immediate review", "High": "8 hours", "Medium": "24 hours", "Low": "72 hours"}
        return {
            "category": category,
            "priority": priority,
            "summary": description[:180].strip(),
            "department": self.departments[category],
            "reason": "Fallback rule-based analysis was used because the AI service was unavailable.",
            "confidence": "Low",
            "risk_level": risk_map[priority],
            "public_impact": "High" if priority in {"Critical", "High"} else "Medium",
            "recommended_response_time": response_map[priority],
            "risk_reason": "Risk estimate is based on keywords in the submitted complaint.",
        }

    def _request(self, contents, max_tokens=700):
        if not Config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{Config.GEMINI_MODEL}:generateContent?key={Config.GEMINI_API_KEY}"
        )
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": max_tokens,
            },
        }
        response = requests.post(url, json=payload, timeout=35)
        response.raise_for_status()
        body = response.json()
        candidates = body.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text

    def analyze(self, description, location="", image_path=None):
        try:
            parts = [{"text": self._prompt(description, location, bool(image_path))}]
            if image_path:
                path = Path(image_path)
                if path.exists() and path.stat().st_size <= 4 * 1024 * 1024:
                    mime = {
                        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png", ".webp": "image/webp"
                    }.get(path.suffix.lower())
                    if mime:
                        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
                        parts.append({"inline_data": {"mime_type": mime, "data": encoded}})

            text = self._request([{"parts": parts}], max_tokens=700)
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
            data = json.loads(text)

            category = data.get("category", "Other")
            priority = data.get("priority", "Medium")
            if category not in self.categories:
                category = "Other"
            if priority not in self.priorities:
                priority = "Medium"

            risk = str(data.get("risk_level", priority)).title()
            if risk not in self.priorities:
                risk = priority

            impact = str(data.get("public_impact", "Medium")).title()
            if impact not in {"Low", "Medium", "High"}:
                impact = "Medium"

            return {
                "category": category,
                "priority": priority,
                "summary": str(data.get("summary", description[:180])).strip()[:300],
                "department": str(data.get("department") or self.departments[category]).strip(),
                "reason": str(data.get("reason", "AI analysis of the complaint.")).strip()[:500],
                "confidence": str(data.get("confidence", "Medium")).strip().title(),
                "risk_level": risk,
                "public_impact": impact,
                "recommended_response_time": str(data.get("recommended_response_time", "24 hours")).strip()[:80],
                "risk_reason": str(data.get("risk_reason", "Risk estimated from the reported details.")).strip()[:500],
            }
        except Exception:
            return self._fallback(description)

    def improve_complaint(self, description, location=""):
        prompt = f"""
Rewrite this citizen civic complaint to be clear, specific and useful for a municipal service team.
Do not add facts that the citizen did not provide. Keep it under 100 words.
Return ONLY the improved complaint text.

Location: {location}
Original complaint: {description}
""".strip()
        try:
            text = self._request([{"parts": [{"text": prompt}]}], max_tokens=180)
            return text.strip().strip('"')
        except Exception:
            return description.strip()

    def generate_insights(self, stats):
        prompt = f"""
You are CivicAI's administrative analytics assistant.
Using ONLY the supplied complaint statistics, write 3 concise operational insights and 2 recommended actions.
Do not invent numbers. Mention the actual category/department/status trends when supported.
Return plain text with headings: INSIGHTS and ACTIONS.

Statistics:
{json.dumps(stats, ensure_ascii=False)}
""".strip()
        try:
            return self._request([{"parts": [{"text": prompt}]}], max_tokens=400)
        except Exception:
            return stats.get("insight", "No AI insight is available right now.")

    def copilot(self, question, complaints):
        compact = []
        for c in complaints[:120]:
            compact.append({
                "id": c.get("complaint_id"),
                "category": c.get("category"),
                "priority": c.get("priority"),
                "status": c.get("status"),
                "department": c.get("assigned_department"),
                "location": c.get("location"),
                "summary": c.get("summary") or c.get("description", "")[:160],
            })
        prompt = f"""
You are CivicAI Admin Copilot.
Answer the administrator's question using ONLY the complaint records below.
Do not invent records or statistics. If the data is insufficient, say so.
Be concise and operational. Mention complaint IDs when useful.

Question: {question}

Complaint records:
{json.dumps(compact, ensure_ascii=False)}
""".strip()
        try:
            return self._request([{"parts": [{"text": prompt}]}], max_tokens=450)
        except Exception:
            return "I couldn't generate the admin copilot answer right now."
