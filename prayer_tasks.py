import datetime
import json
import os
import requests
import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json

# initialise json configuration
with open("conifg.json", "r") as f:
    json_file = json.load(f)

# ---------- CONFIGURATION ----------
SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar.events"
]
TRACK_FILE = json_file["TRACK_FILE"]
TASKLIST_NAME = json_file["TASKLIST_NAME"]
ITERATE_TASK_TITLE = json_file["ITERATE_TASK_TITLE"]
PRAYER_SEQUENCE = json_file["PRAYER_SEQUENCE"]


class PrayerTaskManager:
    def __init__(self, city="London", country="UK"):
        self.city = city
        self.country = country
        self.creds = self.google_authenticate()
        self.service = build("tasks", "v1", credentials=self.creds)
        self.calendar_service = build("calendar", "v3", credentials=self.creds)
        self.tasklist_id = self.get_tasklist_id(TASKLIST_NAME)
        self.track = self.load_track()

    # ---------- GOOGLE AUTH ----------
    def google_authenticate(self):
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        return creds

    def get_tasklist_id(self, name):
        results = self.service.tasklists().list(maxResults=50).execute()
        for item in results.get("items", []):
            if item["title"] == name:
                return item["id"]
        raise RuntimeError(f"Task list '{name}' not found.")

    # ---------- FILE HANDLING ----------
    def load_track(self):
        if os.path.exists(TRACK_FILE):
            try:
                with open(TRACK_FILE, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("[Warning] Track file corrupted — reinitializing.")
                return {}
        return {}

    def save_track(self):
        with open(TRACK_FILE, "w") as f:
            json.dump(self.track, f, indent=2)

    # ---------- PRAYER API ----------
    def get_prayer_times(self, date=None):
        if not date:
            date = datetime.date.today().isoformat()
        url = f"http://api.aladhan.com/v1/timingsByCity/{date}?city={self.city}&country={self.country}&method=2"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()["data"]["timings"]

    # ---------- CORE LOGIC ----------
    def add_prayer_sequence(self, start_date):
        timings_today = self.get_prayer_times(date=start_date)
        timings_tomorrow = self.get_prayer_times(
            date=(datetime.date.fromisoformat(start_date) + datetime.timedelta(days=1)).isoformat()
        )

        tz = pytz.timezone("Europe/London")  # replace dynamically if needed
        task_ids = {}

        for prayer in PRAYER_SEQUENCE:
            # Fajr comes from the next day's timings
            if prayer == "Fajr":
                t = timings_tomorrow[prayer]
                date = datetime.date.fromisoformat(start_date) + datetime.timedelta(days=1)
            else:
                t = timings_today[prayer]
                date = datetime.date.fromisoformat(start_date)

            hour, minute = map(int, t.split(":"))
            local_dt = tz.localize(datetime.datetime.combine(date, datetime.time(hour, minute)))
            due_utc = local_dt.astimezone(pytz.UTC)
            due_rfc3339 = due_utc.isoformat().replace("+00:00", "Z")

            # Format notes
            task_notes = f"Date: {local_dt.strftime('%d/%m/%Y')}\nTime: {local_dt.strftime('%I:%M %p')}"

            # Create Google Task
            task = {
                "title": f"{prayer} Prayer",
                "due": due_rfc3339,
                "notes": task_notes
            }
            created_task = self.service.tasks().insert(tasklist=self.tasklist_id, body=task).execute()
            task_ids[prayer] = created_task["id"]

            # Create corresponding Calendar Event with 0-min reminder
            event = {
                "summary": f"{prayer} Prayer",
                "description": task_notes,
                "start": {"dateTime": local_dt.isoformat(), "timeZone": str(tz)},
                "end": {"dateTime": (local_dt + datetime.timedelta(minutes=15)).isoformat(), "timeZone": str(tz)},
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 0}]
                }
            }
            self.calendar_service.events().insert(calendarId="primary", body=event).execute()

        print("[Setup] Created new prayer sequence.")
        return task_ids

    def ensure_iterate_task(self):
        """Ensures the 'Iterate' task exists and is tracked."""
        tasks = self.service.tasks().list(tasklist=self.tasklist_id).execute().get("items", [])
        existing = None
        for t in tasks:
            if t["title"] == ITERATE_TASK_TITLE:
                existing = t
                break

        if existing:
            iterate_id = existing["id"]
        else:
            task = {"title": ITERATE_TASK_TITLE, "notes": "Force add next 5 prayers"}
            created = self.service.tasks().insert(tasklist=self.tasklist_id, body=task).execute()
            iterate_id = created["id"]
            print("[Init] Created new Iterate task.")

        self.track["iterate_id"] = iterate_id
        self.save_track()
        return iterate_id

    # ---------- CHECKS & UPDATES ----------
    def check_and_update_fajr(self):
        fajr_id = self.track.get("fajr_id")
        today = datetime.date.today().isoformat()

        # If missing or reinitializing
        if not fajr_id:
            print("[Init] No track or Fajr task — initializing new sequence...")
            task_ids = self.add_prayer_sequence(today)
            self.track["fajr_id"] = task_ids["Fajr"]
            self.track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            self.save_track()
            self.ensure_iterate_task()
            return

        try:
            fajr_task = self.service.tasks().get(tasklist=self.tasklist_id, task=fajr_id).execute()
            if fajr_task.get("status") == "completed":
                print(f"[{datetime.datetime.now()}] Fajr completed — scheduling next cycle.")
                task_ids = self.add_prayer_sequence(today)
                self.track["fajr_id"] = task_ids["Fajr"]
                self.track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
                self.save_track()
                self.ensure_iterate_task()
        except Exception:
            print("[Error] Fajr task not found — reinitializing sequence.")
            task_ids = self.add_prayer_sequence(today)
            self.track["fajr_id"] = task_ids["Fajr"]
            self.track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            self.save_track()
            self.ensure_iterate_task()

    def check_and_update_iterate(self):
        iterate_id = self.track.get("iterate_id")

        if not iterate_id:
            print("[Init] No Iterate task found — creating one now.")
            self.ensure_iterate_task()
            return

        try:
            iterate_task = self.service.tasks().get(tasklist=self.tasklist_id, task=iterate_id).execute()
            if iterate_task.get("status") == "completed":
                print(f"[{datetime.datetime.now()}] Iterate completed — regenerating sequence.")

                # Get date of latest Fajr and use that as the next start date
                fajr_id = self.track.get("fajr_id")
                if fajr_id:
                    fajr_task = self.service.tasks().get(tasklist=self.tasklist_id, task=fajr_id).execute()
                    fajr_due = fajr_task.get("due")
                    fajr_date = datetime.date.fromisoformat(fajr_due[:10])
                    next_start_date = fajr_date.isoformat()
                else:
                    next_start_date = datetime.date.today().isoformat()

                task_ids = self.add_prayer_sequence(next_start_date)
                self.track["fajr_id"] = task_ids["Fajr"]
                self.track["fajr_date"] = (datetime.date.fromisoformat(next_start_date) + datetime.timedelta(days=1)).isoformat()
                self.save_track()

                self.service.tasks().delete(tasklist=self.tasklist_id, task=iterate_id).execute()
                new_iterate_id = self.ensure_iterate_task()
                print(f"[Cycle] New Iterate task created (ID: {new_iterate_id}).")
        except Exception:
            print("[Error] Iterate task missing — reinitializing.")
            self.ensure_iterate_task()
