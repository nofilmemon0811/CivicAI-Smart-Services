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
        text = (description or "").lower()

        rules = [
            (["water", "pani", "leak", "pipe", "tap"], "Water"),
            (["drain", "drainage", "nala", "sewage", "gutter", "flood", "sewer"], "Drainage"),
            (["garbage", "waste", "trash", "kachra", "bin"], "Waste"),
            (["streetlight", "electricity", "bijli", "power", "pole", "light"], "Electricity"),
            (["road", "pothole", "sarak", "street", "traffic"], "Road"),
            (["unsafe", "danger", "khatarnaak", "crime", "security"], "Safety"),
        ]

        category = "Other"
        for words, candidate in rules:
            if any(w in text for w in words):
                category = candidate
                break

        critical_terms = [
            "huge", "major", "danger", "accident", "traffic",
            "flood", "unsafe", "emergency", "critical",
            "bohat zyada", "bara masla"
        ]
        high_terms = [
            "broken", "overflow", "leak", "blocked", "damaged",
            "toot", "leakage", "band"
        ]

        if any(w in text for w in critical_terms):
            priority = "Critical"
        elif any(w in text for w in high_terms):
            priority = "High"
        else:
            priority = "Medium"

        response_map = {
            "Critical": "Immediate review",
            "High": "8 hours",
            "Medium": "24 hours",
            "Low": "72 hours",
        }

        return {
            "category": category,
            "priority": priority,
            "summary": (description or "")[:180].strip(),
            "department": self.departments[category],
            "reason": "Fallback rule-based analysis was used because the AI service was unavailable.",
            "confidence": "Low",
            "risk_level": priority,
            "public_impact": "High" if priority in {"Critical", "High"} else "Medium",
            "recommended_response_time": response_map[priority],
            "risk_reason": "Risk estimate is based on keywords in the submitted complaint.",
        }

    # ---------------- GEMINI ----------------

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
        text = "\n".join(
            p.get("text", "") for p in parts if p.get("text")
        ).strip()

        if not text:
            raise RuntimeError("Gemini returned an empty response.")

        return text

    # ---------------- HUGGING FACE / QWEN ----------------

    def _request_huggingface(self, prompt, max_tokens=500):
        if not Config.HF_TOKEN:
            raise RuntimeError("HF_TOKEN is not configured.")

        model = getattr(
            Config,
            "HF_MODEL",
            "Qwen/Qwen2.5-7B-Instruct"
        )

        # Hugging Face's OpenAI-compatible router is used for
        # instruction/chat models such as Qwen.
        url = "https://router.huggingface.co/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {Config.HF_TOKEN}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are CivicAI, a helpful civic-services AI assistant. "
                        "Answer clearly, concisely and do not invent facts."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
        )

        response.raise_for_status()
        data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("Hugging Face returned no choices.")

        message = choices[0].get("message", {})
        text = message.get("content", "")

        if not text:
            raise RuntimeError("Hugging Face returned an empty response.")

        return text.strip()

    # ---------------- PROVIDER FALLBACK ----------------

    def _request_ai(self, prompt, max_tokens=500):
        errors = []

        # Gemini first
        try:
            return self._request(
                [{"parts": [{"text": prompt}]}],
                max_tokens=max_tokens,
            )
        except Exception as error:
            errors.append(f"Gemini: {error}")
            print(f"[CivicAI] Gemini failed: {error}")

        # Qwen / Hugging Face second
        try:
            return self._request_huggingface(
                prompt,
                max_tokens=max_tokens,
            )
        except Exception as error:
            errors.append(f"Hugging Face: {error}")
            print(f"[CivicAI] Hugging Face failed: {error}")

        raise RuntimeError(
            "All AI providers failed. " + " | ".join(errors)
        )

    # ---------------- COMPLAINT ANALYSIS ----------------

    def analyze(self, description, location="", image_path=None):
        try:
            parts = [
                {
                    "text": self._prompt(
                        description,
                        location,
                        bool(image_path),
                    )
                }
            ]

            if image_path:
                path = Path(image_path)

                if path.exists() and path.stat().st_size <= 4 * 1024 * 1024:
                    mime = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".webp": "image/webp",
                    }.get(path.suffix.lower())

                    if mime:
                        encoded = base64.b64encode(
                            path.read_bytes()
                        ).decode("utf-8")

                        parts.append(
                            {
                                "inline_data": {
                                    "mime_type": mime,
                                    "data": encoded,
                                }
                            }
                        )

            # Gemini is preferred here because the current complaint
            # analyzer can send the image to Gemini.
            text = self._request(
                [{"parts": parts}],
                max_tokens=700,
            )

            text = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                text.strip(),
                flags=re.I,
            )

            data = json.loads(text)

            category = data.get("category", "Other")
            priority = data.get("priority", "Medium")

            if category not in self.categories:
                category = "Other"

            if priority not in self.priorities:
                priority = "Medium"

            risk = str(
                data.get("risk_level", priority)
            ).title()

            if risk not in self.priorities:
                risk = priority

            impact = str(
                data.get("public_impact", "Medium")
            ).title()

            if impact not in {"Low", "Medium", "High"}:
                impact = "Medium"

            confidence = str(
                data.get("confidence", "Medium")
            ).strip().title()

            if confidence not in {"Low", "Medium", "High"}:
                confidence = "Medium"

            return {
                "category": category,
                "priority": priority,
                "summary": str(
                    data.get(
                        "summary",
                        (description or "")[:180],
                    )
                ).strip()[:300],
                "department": str(
                    data.get("department")
                    or self.departments[category]
                ).strip(),
                "reason": str(
                    data.get(
                        "reason",
                        "AI analysis of the complaint.",
                    )
                ).strip()[:500],
                "confidence": confidence,
                "risk_level": risk,
                "public_impact": impact,
                "recommended_response_time": str(
                    data.get(
                        "recommended_response_time",
                        "24 hours",
                    )
                ).strip()[:80],
                "risk_reason": str(
                    data.get(
                        "risk_reason",
                        "Risk estimated from the reported details.",
                    )
                ).strip()[:500],
            }

        except Exception as error:
            print(f"[CivicAI] Complaint analysis failed: {error}")
            return self._fallback(description)

    # ---------------- IMPROVE WITH AI ----------------

    def improve_complaint(self, description, location=""):
        prompt = f"""
Rewrite this citizen civic complaint so it is clear, specific,
professional and useful for a municipal service team.

Do not add facts that the citizen did not provide.
Do not change the meaning.
Keep it under 100 words.
Return ONLY the improved complaint text.

Location:
{location}

Original complaint:
{description}
""".strip()

        text = self._request_ai(
            prompt,
            max_tokens=180,
        )

        # Remove accidental markdown/code fences.
        text = re.sub(
            r"^```(?:text)?\s*|\s*```$",
            "",
            text.strip(),
            flags=re.I,
        )

        return text.strip().strip('"')

    # ---------------- AI INSIGHTS ----------------

    def generate_insights(self, stats):
        prompt = f"""
You are CivicAI's administrative analytics assistant.

Using ONLY the supplied complaint statistics, write:
1. Three concise operational insights.
2. Two practical recommended actions.

Do not invent numbers.
Only mention category, department, priority or status trends
that are supported by the supplied statistics.

Return clean plain text with exactly these headings:

INSIGHTS
- ...

ACTIONS
- ...

Statistics:
{json.dumps(stats, ensure_ascii=False)}
""".strip()

        return self._request_ai(
            prompt,
            max_tokens=400,
        )

    # ---------------- ADMIN COPILOT ----------------

    def copilot(self, question, complaints):
        compact = []

        for complaint in complaints[:120]:
            compact.append(
                {
                    "id": complaint.get("complaint_id"),
                    "category": complaint.get("category"),
                    "priority": complaint.get("priority"),
                    "status": complaint.get("status"),
                    "department": complaint.get("assigned_department"),
                    "location": complaint.get("location"),
                    "summary": (
                        complaint.get("summary")
                        or complaint.get("description", "")[:160]
                    ),
                }
            )

        prompt = f"""
You are CivicAI Admin Copilot.

Answer the administrator's question using ONLY the complaint
records provided below.

Rules:
- Do not invent complaint records.
- Do not invent statistics.
- If the data is insufficient, clearly say so.
- Be concise and operational.
- Mention complaint IDs when useful.
- If the administrator asks for a count, calculate it from
  the supplied records.
- If the administrator asks for the most common category,
  priority or department, calculate it from the supplied records.

Administrator question:
{question}

Complaint records:
{json.dumps(compact, ensure_ascii=False)}
""".strip()

        return self._request_ai(
            prompt,
            max_tokens=450,
        )
