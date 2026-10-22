import os
import csv
import json
import time
from typing import List, Dict, Any, Optional
import uuid
from core.paths import get_data_path


class SessionStorage:
    """
    Persists grinding session logs to CSV and JSON files in the data directory.
    Supports reading, appending, deleting, and updating session records.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or get_data_path()
        os.makedirs(self.data_dir, exist_ok=True)
        self.csv_path = os.path.join(self.data_dir, "exp_log.csv")
        self.json_path = os.path.join(self.data_dir, "exp_log.json")

        self.fieldnames = [
            "id", "date", "map", "lv", "party", "time",
            "exp_hr", "mesos_hr", "gained_exp", "gained_mesos", "timestamp"
        ]

        # Initialize CSV header if file doesn't exist
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()

    def load_sessions(self) -> List[Dict[str, Any]]:
        """Loads all historical sessions sorted by timestamp descending."""
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, mode="r", encoding="utf-8") as f:
                    data = json.load(f)
                    return sorted(data, key=lambda x: x.get("timestamp", 0), reverse=True)
            except Exception:
                pass

        # Fallback load from CSV
        sessions = []
        if os.path.exists(self.csv_path):
            try:
                with open(self.csv_path, mode="r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sessions.append({
                            "id": row.get("id", str(uuid.uuid4())),
                            "date": row.get("date", ""),
                            "map": row.get("map", "Unknown"),
                            "lv": int(row.get("lv", 1)),
                            "party": row.get("party", "Solo"),
                            "time": row.get("time", "0m"),
                            "exp_hr": int(float(row.get("exp_hr", 0))),
                            "mesos_hr": int(float(row.get("mesos_hr", 0))),
                            "gained_exp": int(float(row.get("gained_exp", 0))),
                            "gained_mesos": int(float(row.get("gained_mesos", 0))),
                            "timestamp": float(row.get("timestamp", 0.0))
                        })
            except Exception:
                pass

        return sorted(sessions, key=lambda x: x.get("timestamp", 0), reverse=True)

    def _sync_to_disk(self, sessions: List[Dict[str, Any]]):
        """Save sessions list to both JSON and CSV."""
        # JSON
        with open(self.json_path, mode="w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)

        # CSV
        with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
            for s in sessions:
                writer.writerow({
                    "id": s.get("id", ""),
                    "date": s.get("date", ""),
                    "map": s.get("map", ""),
                    "lv": s.get("lv", 1),
                    "party": s.get("party", "Solo"),
                    "time": s.get("time", ""),
                    "exp_hr": s.get("exp_hr", 0),
                    "mesos_hr": s.get("mesos_hr", 0),
                    "gained_exp": s.get("gained_exp", 0),
                    "gained_mesos": s.get("gained_mesos", 0),
                    "timestamp": s.get("timestamp", 0.0)
                })

    def add_session(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Appends a new completed session."""
        sessions = self.load_sessions()
        if "id" not in record or not record["id"]:
            record["id"] = str(uuid.uuid4())
        if "timestamp" not in record or not record["timestamp"]:
            record["timestamp"] = time.time()
        if "date" not in record or not record["date"]:
            record["date"] = time.strftime("%b %d")

        sessions.insert(0, record)
        self._sync_to_disk(sessions)
        return record

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session by ID."""
        sessions = self.load_sessions()
        initial_len = len(sessions)
        sessions = [s for s in sessions if s.get("id") != session_id]
        if len(sessions) < initial_len:
            self._sync_to_disk(sessions)
            return True
        return False

    def update_session(self, session_id: str, new_map: Optional[str] = None, new_party: Optional[str] = None) -> bool:
        """Updates map name or party size on a historical session."""
        sessions = self.load_sessions()
        updated = False
        for s in sessions:
            if s.get("id") == session_id:
                if new_map is not None:
                    s["map"] = new_map
                if new_party is not None:
                    s["party"] = new_party
                updated = True
                break
        if updated:
            self._sync_to_disk(sessions)
            return True
        return False

