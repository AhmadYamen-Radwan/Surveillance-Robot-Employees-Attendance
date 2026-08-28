import json
import os
import time
import threading
from datetime import datetime
from typing import List


class AttendanceTracker:
    """
        Tracks employee attendance based on face recognition events.
        Logs check-in when a known face is first detected,
        and check-out when the face disappears for a threshold period.
    """
    ATTENDANCE_FILE = "attendance_log.json"
    CHECKIN_COOLDOWN = 10  # seconds between re-checkin for same session

    def __init__(self):
        self.lock = threading.Lock()
        self._checked_in = {}  # name, timestamp of last check-in
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.ATTENDANCE_FILE):
            with open(self.ATTENDANCE_FILE, 'w') as f:
                json.dump({}, f, indent=2)

    def _load_data(self) -> dict:
        try:
            with open(self.ATTENDANCE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_data(self, data: dict):
        with open(self.ATTENDANCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def check_in(self, name: str) -> bool:
        """
            Log check-in for an employee.
            Returns True if a new record was created.
        """
        if not name or name == "Unknown":
            return False

        now = time.time()
        with self.lock:
            # Prevent duplicate check-ins within cooldown
            if name in self._checked_in:
                if now - self._checked_in[name] < self.CHECKIN_COOLDOWN:
                    return False

            self._checked_in[name] = now

            data = self._load_data()
            today = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%H:%M:%S")

            if today not in data:
                data[today] = []

            # Check if there is already an open session for today
            for record in data[today]:
                if record['name'] == name and record.get('check_out') is None:
                    return False

            record = {
                'name': name,
                'check_in': current_time,
                'check_out': None,
                'duration_seconds': 0
            }
            data[today].append(record)
            self._save_data(data)
            print(f"[ATTENDANCE] {name} checked in at {current_time}")
            return True

    def check_out(self, name: str) -> bool:
        """
            Log check-out for an employee.
            Returns True if a record was updated.
        """
        if not name or name == "Unknown":
            return False

        with self.lock:
            if name in self._checked_in:
                del self._checked_in[name]

            data = self._load_data()
            today = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%H:%M:%S")

            if today not in data:
                return False

            # Find the most recent open record
            for record in reversed(data[today]):
                if record['name'] == name and record.get('check_out') is None:
                    record['check_out'] = current_time
                    try:
                        check_in_dt = datetime.strptime(
                            f"{today} {record['check_in']}", "%Y-%m-%d %H:%M:%S"
                        )
                        check_out_dt = datetime.strptime(
                            f"{today} {current_time}", "%Y-%m-%d %H:%M:%S"
                        )
                        duration = int((check_out_dt - check_in_dt).total_seconds())
                        record['duration_seconds'] = max(0, duration)
                    except Exception:
                        record['duration_seconds'] = 0

                    self._save_data(data)
                    print(f"[ATTENDANCE] {name} checked out at {current_time}")
                    return True
            return False

    def checkout_all(self):
        """
            Check out all currently checked-in employees.
        """
        with self.lock:
            names = list(self._checked_in.keys())
            for name in names:
                self.check_out(name)

    def get_today_records(self) -> List[dict]:
        data = self._load_data()
        today = datetime.now().strftime("%Y-%m-%d")
        return data.get(today, [])

    def get_present_employees(self) -> List[str]:
        """
            Return list of names currently checked in.
        """
        data = self._load_data()
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in data:
            return []
        return [
            r['name'] for r in data[today]
            if r.get('check_out') is None
        ]

    def get_all_records(self) -> dict:
        return self._load_data()

    def export_to_csv(self, filepath: str = "attendance_export.csv") -> str:
        import csv
        data = self._load_data()
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date', 'Name', 'Check In', 'Check Out',
                'Duration (seconds)', 'Duration (HH:MM:SS)'
            ])
            for date, records in sorted(data.items()):
                for record in records:
                    duration = record.get('duration_seconds', 0)
                    hours = duration // 3600
                    minutes = (duration % 3600) // 60
                    secs = duration % 60
                    duration_fmt = f"{hours:02d}:{minutes:02d}:{secs:02d}"
                    writer.writerow([
                        date,
                        record['name'],
                        record['check_in'],
                        record.get('check_out', 'N/A'),
                        duration,
                        duration_fmt
                    ])
        return filepath
