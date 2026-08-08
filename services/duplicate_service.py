
import re
from .text_similarity import cosine_similarity

class DuplicateDetector:
    def _clean(self, text):
        return re.sub(r"[^a-z0-9\s]", " ", text.lower())

    def find(self, complaint, existing, threshold=0.30):
        candidates = [x for x in existing if x.get("complaint_id") != complaint.get("complaint_id")]
        if not candidates:
            return []
        source = self._clean(complaint["description"])
        matches = []
        for candidate in candidates:
            score = cosine_similarity(source, self._clean(candidate["description"]))
            if float(score) >= threshold:
                matches.append({
                    "complaint_id": candidate["complaint_id"],
                    "similarity": round(float(score) * 100, 1),
                    "status": "possible_duplicate",
                })
        return sorted(matches, key=lambda x: x["similarity"], reverse=True)[:3]
