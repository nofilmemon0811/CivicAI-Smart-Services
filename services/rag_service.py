from pathlib import Path
import re
import requests

from .text_similarity import cosine_similarity
from config import Config


class RAGService:
    """Broad civic assistant: grounded RAG when possible, AI general civic mode otherwise."""

    STOPWORDS = {
        "what", "which", "where", "when", "who", "does", "do", "is", "are",
        "the", "a", "an", "to", "for", "of", "and", "in", "on", "with",
        "how", "can", "should", "handle", "handles", "department", "please",
        "tell", "me", "about", "this", "that", "it", "my", "your", "you",
        "could", "would", "i", "we", "they", "be", "from", "or", "as"
    }

    def __init__(self):
        self.base = Path(__file__).resolve().parent.parent / "knowledge_base"
        self.documents = self._load_documents()

    def _load_documents(self):
        documents = []
        if not self.base.exists():
            return documents

        for path in sorted(self.base.glob("*.md")):
            try:
                documents.append({
                    "source": path.name,
                    "text": path.read_text(encoding="utf-8")
                })
            except OSError as exc:
                print(f"RAG knowledge-base read error ({path.name}): {exc}")
        return documents

    def _tokens(self, text):
        words = re.findall(r"[a-zA-Z0-9]+", text.lower())
        return {
            word for word in words
            if len(word) > 2 and word not in self.STOPWORDS
        }

    def retrieve(self, question, top_k=5):
        """Retrieve useful local civic documents, but never block the AI on retrieval."""
        if not self.documents:
            return []

        question_tokens = self._tokens(question)
        ranked = []

        for document in self.documents:
            document_tokens = self._tokens(document["text"])
            overlap = len(question_tokens & document_tokens)
            keyword_score = min(
                overlap / max(len(question_tokens), 1),
                1.0
            )
            similarity = cosine_similarity(
                question,
                document["text"]
            )
            combined = 0.72 * float(similarity) + 0.28 * keyword_score

            ranked.append({
                "source": document["source"],
                "text": document["text"],
                "score": combined,
                "tfidf": float(similarity),
                "keyword_overlap": overlap
            })

        ranked.sort(key=lambda item: item["score"], reverse=True)

        # Keep only genuinely useful matches. The important difference is that
        # an empty result does NOT stop Gemini/Qwen from answering general civic questions.
        return [
            item for item in ranked[:top_k]
            if (
                item["score"] >= 0.035
                or item["keyword_overlap"] >= 1
                or item["tfidf"] >= 0.02
            )
        ][:top_k]

    def _build_prompt(self, question, retrieved):
        if retrieved:
            context = "\n\n".join(
                f"SOURCE: {item['source']}\n{item['text']}"
                for item in retrieved
            )
        else:
            context = "No specific local knowledge-base article matched this question."

        return f"""You are CivicAI, a professional AI civic-service assistant helping citizens understand and solve civic problems.

You can answer broad questions about civic services, municipalities, local government concepts, public infrastructure, roads, water, drainage, waste, electricity, public safety, transport, accessibility, sanitation, parks, environment, disaster preparedness, permits, complaints, community services, urban planning, and how citizens can report or describe public problems.

IMPORTANT ANSWERING POLICY:
1. If the supplied civic knowledge base contains relevant information, use it as the primary source and cite it naturally when useful.
2. If the knowledge base does NOT contain enough information, you MAY answer using your general civic knowledge. Do NOT refuse merely because retrieval found no document.
3. Never invent local phone numbers, addresses, laws, fees, government offices, department names, opening hours, emergency contacts, or policies. If a location-specific fact is required and is not supplied, say that it depends on the user's city/country and ask for the location.
4. For current or real-time information such as today's weather, current road closures, live outages, current government announcements, or today's public transport status, explain that CivicAI needs a live data source and do not pretend the information is current.
5. For emergencies or immediate danger, advise the citizen to contact the appropriate local emergency service instead of relying on CivicAI.
6. Give practical next steps whenever appropriate: what information to collect, what type of department/service normally handles it, how to describe the issue, and what urgency factors matter.
7. If the user asks a normal civic question that is not in the knowledge base, answer it helpfully rather than saying the knowledge base is insufficient.
8. Be concise, friendly, professional, and easy for a citizen to understand.
9. Never claim that you contacted a department, filed a complaint, or checked live data unless the application actually performed that action.
10. If the user asks about something outside civic/public-service topics, answer briefly if it is useful, then explain how it relates (or does not relate) to CivicAI.

CIVIC KNOWLEDGE BASE:
{context}

USER QUESTION:
{question}
""".strip()

    @staticmethod
    def _extract_openai_text(data):
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Model returned no choices.")

        message = choices[0].get("message") or {}
        content = message.get("content", "")

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )

        answer = str(content).strip()
        if not answer:
            raise RuntimeError("Model returned an empty answer.")
        return answer

    def _gemini(self, question, retrieved):
        if not Config.GEMINI_API_KEY:
            raise RuntimeError("Gemini API key is not configured.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{Config.GEMINI_MODEL}:generateContent"
            f"?key={Config.GEMINI_API_KEY}"
        )

        payload = {
            "contents": [{
                "parts": [{"text": self._build_prompt(question, retrieved)}]
            }],
            "generationConfig": {
                "temperature": 0.25,
                "maxOutputTokens": 500
            }
        }

        response = requests.post(url, json=payload, timeout=25)
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except Exception:
                detail = ""
            raise RuntimeError(
                f"Gemini API error {response.status_code}: {detail}"
            )

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates.")

        parts = (candidates[0].get("content") or {}).get("parts") or []
        answer = "\n".join(
            part.get("text", "") for part in parts if part.get("text")
        ).strip()
        if not answer:
            raise RuntimeError("Gemini returned an empty answer.")
        return answer

    def _qwen(self, question, retrieved):
        if not Config.HF_TOKEN:
            raise RuntimeError("Hugging Face token is not configured.")

        url = Config.HF_CHAT_URL
        payload = {
            "model": Config.HF_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are CivicAI, a helpful civic-service assistant. "
                        "Use the supplied local civic context when relevant, but answer broad "
                        "civic questions from your general knowledge when the context has no match. "
                        "Never invent location-specific facts or claim real-time knowledge."
                    )
                },
                {
                    "role": "user",
                    "content": self._build_prompt(question, retrieved)
                }
            ],
            "temperature": 0.25,
            "max_tokens": 500
        }

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {Config.HF_TOKEN}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        if response.status_code >= 400:
            try:
                detail = response.json().get("error", "")
            except Exception:
                detail = response.text[:300]
            raise RuntimeError(
                f"Hugging Face API error {response.status_code}: {detail}"
            )

        return self._extract_openai_text(response.json())

    def _local_answer(self, question, retrieved):
        """Only used when both AI providers are unavailable."""
        if not retrieved:
            return (
                "I can answer this civic question when an AI provider is configured. "
                "Please add GEMINI_API_KEY or HF_TOKEN in your environment."
            )

        question_tokens = self._tokens(question)
        candidates = []

        for document in retrieved:
            for line in document["text"].splitlines():
                line = re.sub(r"^[#*\-\s]+", "", line.strip())
                if not line:
                    continue

                overlap = len(question_tokens & self._tokens(line))
                if overlap:
                    candidates.append((overlap, line))

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]

        return (
            "CivicAI could not generate an AI response because no AI provider "
            "is currently configured."
        )

    def ask(self, question):
        question = str(question or "").strip()
        if not question:
            return "Please enter a civic question.", [], "local"

        # IMPORTANT: retrieval is enrichment, not a gatekeeper.
        # This allows Gemini/Qwen to answer broad civic questions even when
        # there is no exact knowledge-base article.
        retrieved = self.retrieve(question)

        providers = []
        if Config.GEMINI_API_KEY:
            providers.append(("Gemini", self._gemini))
        if Config.HF_TOKEN:
            providers.append(("Qwen / Hugging Face", self._qwen))

        answer = None
        used_provider = None

        for provider_name, provider in providers:
            try:
                answer = provider(question, retrieved)
                used_provider = provider_name
                break
            except Exception as exc:
                print(f"{provider_name} RAG error: {exc}")

        if answer is None:
            answer = self._local_answer(question, retrieved)
            used_provider = "Local knowledge fallback"

        sources = [
            {
                "name": item["source"],
                "score": round(item["score"], 2)
            }
            for item in retrieved[:3]
        ]

        return answer, sources, used_provider
