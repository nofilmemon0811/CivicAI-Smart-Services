
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from services.complaint_service import ComplaintManager

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

def seed():
    manager = ComplaintManager()
    samples = [
        ("Large water leak near the main road is making traffic difficult.", "Latifabad Main Road", "Water", "Critical", "Water & Drainage", "In Progress"),
        ("Garbage bins have been overflowing for three days.", "Unit 7 Market", "Waste", "High", "Waste Management", "Assigned"),
        ("Several potholes are damaging vehicles near the school.", "Auto Bhan Road", "Road", "High", "Roads & Infrastructure", "In Progress"),
        ("Streetlight is broken and the road is very dark at night.", "Citizen Colony Street 4", "Electricity", "High", "Electricity Services", "Assigned"),
        ("Drain is blocked and dirty water is collecting outside houses.", "Qasimabad Block B", "Drainage", "Critical", "Water & Drainage", "In Progress"),
        ("Public park gate is damaged and children can enter an unsafe area.", "Rani Bagh", "Safety", "High", "Public Safety", "Submitted"),
        ("Water pressure has been low since yesterday.", "Unit 5", "Water", "Medium", "Water & Drainage", "Resolved"),
        ("Road markings have faded at the intersection.", "Market Road", "Road", "Medium", "Roads & Infrastructure", "Resolved"),
        ("Waste collection was missed this week.", "Hirabad", "Waste", "Medium", "Waste Management", "Resolved"),
        ("Electric pole has a damaged cover.", "Gul Centre", "Electricity", "High", "Electricity Services", "AI Analyzed"),
        ("Sewage smell is coming from a blocked drain.", "Phuleli Area", "Drainage", "High", "Water & Drainage", "Assigned"),
        ("Pedestrian crossing sign is missing.", "Station Road", "Safety", "Medium", "Public Safety", "Submitted"),
        ("Deep pothole beside the bus stop is a safety risk.", "Market Road Bus Stop", "Road", "Critical", "Roads & Infrastructure", "In Progress"),
        ("Trash is scattered around the community bin.", "Unit 9", "Waste", "Medium", "Waste Management", "Assigned"),
        ("Streetlight flickers every night.", "Saddar Street 2", "Electricity", "Low", "Electricity Services", "Submitted"),
        ("Water is leaking from a broken pipe near the mosque.", "Gulshan-e-Sajjad", "Water", "High", "Water & Drainage", "Resolved"),
        ("Storm drain is blocked with plastic waste.", "Qasimabad Phase 1", "Drainage", "High", "Water & Drainage", "Resolved"),
        ("A broken sidewalk is causing people to walk on the road.", "Thandi Sarak", "Road", "High", "Roads & Infrastructure", "Assigned"),
        ("Garbage collection point is attracting stray animals.", "Unit 10", "Waste", "High", "Waste Management", "Submitted"),
        ("Power line appears loose near a public walkway.", "Citizen Colony", "Electricity", "Critical", "Electricity Services", "In Progress"),
        ("A dark alley feels unsafe after sunset.", "Hirabad Lane 5", "Safety", "High", "Public Safety", "Assigned"),
        ("Small leak is forming near the water meter.", "Latifabad Unit 6", "Water", "Medium", "Water & Drainage", "Submitted"),
        ("Road surface is cracked near the hospital entrance.", "Civil Hospital Road", "Road", "High", "Roads & Infrastructure", "AI Analyzed"),
        ("Public bin is missing from a busy market corner.", "Resham Gali", "Waste", "Medium", "Waste Management", "Submitted"),
        ("Drain cover is broken and could cause someone to fall.", "Qasimabad Block C", "Drainage", "Critical", "Water & Drainage", "In Progress"),
        ("Streetlight near the playground is not working.", "Rani Bagh Road", "Electricity", "Medium", "Electricity Services", "Resolved"),
        ("Footpath is damaged around the bus station.", "Station Road", "Road", "Medium", "Roads & Infrastructure", "Resolved"),
        ("Waste has not been collected from the lane.", "Unit 8", "Waste", "High", "Waste Management", "Assigned"),
        ("Open drain is creating a hazard for pedestrians.", "Phuleli Road", "Drainage", "Critical", "Water & Drainage", "Submitted"),
        ("Park boundary is damaged and needs attention.", "Public Park Block A", "Safety", "Medium", "Public Safety", "AI Analyzed"),
        ("Large water leak is visible near the main road.", "Latifabad Main Road", "Water", "Critical", "Water & Drainage", "Submitted"),
    ]

    records = []
    now = datetime.now(timezone.utc)
    for i, item in enumerate(samples):
        description, location, category, priority, department, status = item
        record = manager.create(description, location)
        created = now - timedelta(days=(i % 15), hours=(i * 2) % 20)
        manager.update(
            record["complaint_id"],
            category=category,
            priority=priority,
            assigned_department=department,
            status=status,
            summary=description,
            reason="Seeded demonstration complaint for dashboard testing.",
            confidence="Demo",
            date=created.isoformat(),
        )
        if status == "Resolved":
            manager.update(record["complaint_id"], resolved_at=(created + timedelta(hours=8 + i % 30)).isoformat())
    print(f"Seeded {len(samples)} demo complaints.")

if __name__ == "__main__":
    seed()
