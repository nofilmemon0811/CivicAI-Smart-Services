from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class Complaint:
    complaint_id: str
    description: str
    location: str
    date: str
    status: str = "Submitted"
    category: str = "Other"
    priority: str = "Medium"
    assigned_department: str = "General Civic Services"
    summary: str = ""
    reason: str = ""
    confidence: str = "Unknown"
    name: str = ""
    contact: str = ""
    image: str | None = None
    duplicate_matches: list = None
    resolved_at: str | None = None
    owner_username: str = ""
    risk_level: str = "Medium"
    public_impact: str = "Medium"
    recommended_response_time: str = "24 hours"
    risk_reason: str = ""

    def to_dict(self):
        data = asdict(self)
        data["duplicate_matches"] = self.duplicate_matches or []
        return data

    @classmethod
    def new(cls, complaint_id, description, location, name="", contact="", image=None, owner_username=""):
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            complaint_id=complaint_id,
            description=description,
            location=location,
            date=now,
            name=name,
            contact=contact,
            image=image,
            owner_username=owner_username,
            duplicate_matches=[],
        )
