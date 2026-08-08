
from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median, mode, StatisticsError, pstdev

class AnalyticsService:
    def _counts(self, complaints, field):
        return dict(Counter(c.get(field, "Unknown") for c in complaints))

    def _resolution_hours(self, complaints):
        values = []
        for c in complaints:
            if c.get("resolved_at") and c.get("date"):
                try:
                    start = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(c["resolved_at"].replace("Z", "+00:00"))
                    values.append(max(0, (end - start).total_seconds() / 3600))
                except ValueError:
                    pass
        return values

    def summary(self, complaints):
        total = len(complaints)
        resolved = sum(c.get("status") == "Resolved" for c in complaints)
        open_count = total - resolved
        critical = sum(c.get("priority") == "Critical" for c in complaints)
        return {
            "total": total,
            "open": open_count,
            "critical": critical,
            "resolved": resolved,
        }

    def full(self, complaints):
        resolution = self._resolution_hours(complaints)
        stats = self.summary(complaints)
        stats.update({
            "categories": self._counts(complaints, "category"),
            "priorities": self._counts(complaints, "priority"),
            "departments": self._counts(complaints, "assigned_department"),
            "statuses": self._counts(complaints, "status"),
            "locations": self._counts(complaints, "location"),
            "resolution": self._numeric(resolution),
            "insight": self._insight(complaints),
            "recent": sorted(complaints, key=lambda x: x.get("date", ""), reverse=True)[:8],
        })
        return stats

    def _numeric(self, values):
        if not values:
            return {"count": 0, "mean": 0, "median": 0, "mode": None, "min": 0, "max": 0, "range": 0, "std_dev": 0}
        try:
            m = mode(values)
        except StatisticsError:
            m = None
        return {
            "count": len(values),
            "mean": round(mean(values), 2),
            "median": round(median(values), 2),
            "mode": round(m, 2) if m is not None else None,
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "range": round(max(values) - min(values), 2),
            "std_dev": round(pstdev(values), 2) if len(values) > 1 else 0,
        }

    def _insight(self, complaints):
        if not complaints:
            return "No complaint data is available yet."
        categories = self._counts(complaints, "category")
        top_category = max(categories, key=categories.get)
        critical = sum(c.get("priority") == "Critical" for c in complaints)
        pct = round((critical / len(complaints)) * 100, 1)
        return f"{top_category} complaints are currently the most common issue. Critical complaints represent {pct}% of all complaints."
