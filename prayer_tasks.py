import datetime
import json
import os
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/tasks"]
TRACK_FILE = "trk.dat"
TASKLIST_NAME = "ptrk"
ITERATE_TASK_TITLE = "Iterate"
PRAYER_SEQUENCE = ["Dhuhr", "Asr", "Maghrib", "Isha", "Fajr"]


class PrayerTaskManager:
    def __init__(self, city="London", country="UK"):
        self.city = city
        self.country = country
        self.creds = self.google_authenticate()
        self.service = build("tasks", "v1", credentials=self.creds)
        self.tasklist_id = self.get_tasklist_id(TASKLIST_NAME)
        self.track = self.load_track()
    
    # ---------- Google API ----------
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

    # ---------- File helpers ----------
    def load_track(self):
        if os.path.exists(TRACK_FILE):
            with open(TRACK_FILE, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def save_track(self):
        with open(TRACK_FILE, "w") as f:
            json.dump(self.track, f, indent=2)

    # ---------- Prayer API ----------
    def get_prayer_times(self, date=None):
        if not date:
            date = datetime.date.today().isoformat()
        url = f"http://api.aladhan.com/v1/timingsByCity/{date}?city={self.city}&country={self.country}&method=2"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data["data"]["timings"]

    # ---------- Core Logic ----------
    def add_prayer_sequence(self, start_date):
        timings_today = self.get_prayer_times(date=start_date)
        timings_tomorrow = self.get_prayer_times(
            date=(datetime.date.fromisoformat(start_date) + datetime.timedelta(days=1)).isoformat()
        )

        task_ids = {}
        for prayer in PRAYER_SEQUENCE:
            if prayer == "Fajr":
                t = timings_tomorrow[prayer]
                date = datetime.date.fromisoformat(start_date) + datetime.timedelta(days=1)
            else:
                t = timings_today[prayer]
                date = datetime.date.fromisoformat(start_date)

            hour, minute = map(int, t.split(":"))
            due_time = datetime.datetime.combine(date, datetime.time(hour, minute)).isoformat() + "Z"

            task = {
                "title": f"{prayer} Prayer",
                "due": due_time,
                "notes": f"Date: {date}"
            }
            created = self.service.tasks().insert(tasklist=self.tasklist_id, body=task).execute()
            task_ids[prayer] = created["id"]

        return task_ids

    def ensure_iterate_task(self):
        tasks = self.service.tasks().list(tasklist=self.tasklist_id).execute().get("items", [])
        for t in tasks:
            if t["title"] == ITERATE_TASK_TITLE:
                self.service.tasks().delete(tasklist=self.tasklist_id, task=t["id"]).execute()

        task = {"title": ITERATE_TASK_TITLE, "notes": "Force add next 5 prayers"}
        created = self.service.tasks().insert(tasklist=self.tasklist_id, body=task).execute()
        return created["id"]

    def check_and_update_fajr(self):
        fajr_id = self.track.get("fajr_id")
        today = datetime.date.today().isoformat()
        if fajr_id:
            try:
                fajr_task = self.service.tasks().get(tasklist=self.tasklist_id, task=fajr_id).execute()
                if fajr_task.get("status") == "completed":
                    print(f"[{datetime.datetime.now()}] Fajr checked, adding...")
                    task_ids = self.add_prayer_sequence(today)
                    self.track["fajr_id"] = task_ids["Fajr"]
                    self.track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
                    self.save_track()
            except Exception:
                print("Fajr task not found, reinitializing...")
                task_ids = self.add_prayer_sequence(today)
                self.track["fajr_id"] = task_ids["Fajr"]
                self.track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
                self.save_track()

    def check_and_update_iterate(self):
        tasks = self.service.tasks().list(tasklist=self.tasklist_id).execute().get("items", [])
        today = datetime.date.today().isoformat()
        for t in tasks:
            if t["title"] == ITERATE_TASK_TITLE and t.get("status") == "completed":
                print(f"[{datetime.datetime.now()}] Iterate checked, adding...")
                task_ids = self.add_prayer_sequence(today)
                self.track["fajr_id"] = task_ids["Fajr"]
                self.track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
                self.save_track()
                # Reset iterate task
                self.service.tasks().delete(tasklist=self.tasklist_id, task=t["id"]).execute()
                self.ensure_iterate_task()
