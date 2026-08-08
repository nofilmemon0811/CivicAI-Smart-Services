
import json
import os
import threading
import tempfile

class JSONDatabase:
    """Small JSON repository with atomic writes and a process-local lock."""
    _lock = threading.RLock()

    def __init__(self, path, default=None):
        self.path = path
        self.default = [] if default is None else default
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            self.save(self.default)

    def load(self):
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return self.default.copy() if isinstance(self.default, list) else dict(self.default)

    def save(self, data):
        with self._lock:
            directory = os.path.dirname(self.path) or "."
            fd, tmp = tempfile.mkstemp(prefix=".jsondb-", dir=directory, text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    def add(self, item):
        data = self.load()
        data.append(item)
        self.save(data)
        return item

    def update(self, key, value, id_field="complaint_id"):
        data = self.load()
        for index, item in enumerate(data):
            if item.get(id_field) == key:
                data[index] = value
                self.save(data)
                return value
        return None

    def delete(self, key, id_field="complaint_id"):
        data = self.load()
        new_data = [item for item in data if item.get(id_field) != key]
        self.save(new_data)
        return len(new_data) != len(data)

    def find(self, key, id_field="complaint_id"):
        return next((x for x in self.load() if x.get(id_field) == key), None)

    def get_all(self):
        return self.load()
