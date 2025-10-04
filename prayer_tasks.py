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

# User-friendly sequence
PRAYER_SEQUENCE = ["Zuhr", "Asr", "Maghrib", "Isha", "Fajr"]

# Map to API keys returned by Aladhan
API_NAME_MAP = {
    "Zuhr": "Dhuhr",
    "Asr": "Asr",
    "Maghrib": "Maghrib",
    "Isha": "Isha",
    "Fajr": "Fajr"
}

# ---------- Google API Setup ----------
def google_authenticate():
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

def get_tasklist_id(service, name):
    results = service.tasklists().list(maxResults=50).execute()
    for item in results.get("items", []):
        if item["title"] == name:
            return item["id"]
    raise RuntimeError(f"Task list '{name}' not found.")

# ---------- Prayer API ----------
def get_prayer_times(city="London", country="UK", date=None):
    if not date:
        date = datetime.date.today().isoformat()
    url = f"http://api.aladhan.com/v1/timingsByCity/{date}?city={city}&country={country}&method=2"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    return data["data"]["timings"]

# ---------- File Helpers ----------
def load_track():
    if os.path.exists(TRACK_FILE):
        with open(TRACK_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_track(store):
    with open(TRACK_FILE, "w") as f:
        json.dump(store, f, indent=2)

# ---------- Core Logic ----------
def add_prayer_sequence(service, tasklist_id, start_date):
    timings_today = get_prayer_times(date=start_date)
    timings_tomorrow = get_prayer_times(
        date=(datetime.date.fromisoformat(start_date) + datetime.timedelta(days=1)).isoformat()
    )

    task_ids = {}
    for prayer in PRAYER_SEQUENCE:
        api_key = API_NAME_MAP[prayer]
        if prayer == "Fajr":
            t = timings_tomorrow[api_key]
            date = datetime.date.fromisoformat(start_date) + datetime.timedelta(days=1)
        else:
            t = timings_today[api_key]
            date = datetime.date.fromisoformat(start_date)

        hour, minute = map(int, t.split(":"))
        due_time = datetime.datetime.combine(date, datetime.time(hour, minute)).isoformat() + "Z"

        task = {
            "title": f"{prayer} Prayer",
            "due": due_time,
            "notes": f"Date: {date}"
        }
        created = service.tasks().insert(tasklist=tasklist_id, body=task).execute()
        task_ids[prayer] = created["id"]

    return task_ids

def ensure_iterate_task(service, tasklist_id):
    # delete any old Iterate tasks
    tasks = service.tasks().list(tasklist=tasklist_id).execute().get("items", [])
    for t in tasks:
        if t["title"] == ITERATE_TASK_TITLE:
            service.tasks().delete(tasklist=tasklist_id, task=t["id"]).execute()

    task = {"title": ITERATE_TASK_TITLE, "notes": "Force add next 5 prayers"}
    created = service.tasks().insert(tasklist=tasklist_id, body=task).execute()
    return created["id"]

def main():
    creds = google_authenticate()
    service = build("tasks", "v1", credentials=creds)
    tasklist_id = get_tasklist_id(service, TASKLIST_NAME)

    track = load_track()

    # Check if we have fajr stored
    fajr_id = track.get("fajr_id")
    fajr_date = track.get("fajr_date")

    if not fajr_id:
        # Look for the newest Fajr task
        tasks = service.tasks().list(tasklist=tasklist_id, showCompleted=True).execute().get("items", [])
        fajr_tasks = [t for t in tasks if "Fajr" in t["title"]]
        if fajr_tasks:
            fajr_tasks.sort(key=lambda x: x.get("due", ""), reverse=True)
            latest = fajr_tasks[0]
            track["fajr_id"] = latest["id"]
            track["fajr_date"] = latest.get("notes", "").replace("Date: ", "")
            save_track(track)
        else:
            # No Fajr found, initialize
            today = datetime.date.today().isoformat()
            task_ids = add_prayer_sequence(service, tasklist_id, today)
            track["fajr_id"] = task_ids["Fajr"]
            track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            save_track(track)

    # Check if current fajr is completed
    try:
        fajr_task = service.tasks().get(tasklist=tasklist_id, task=track["fajr_id"]).execute()
        if fajr_task["status"] == "completed":
            today = datetime.date.today().isoformat()
            task_ids = add_prayer_sequence(service, tasklist_id, today)
            track["fajr_id"] = task_ids["Fajr"]
            track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            save_track(track)
    except Exception:
        print("Stored Fajr task not found, reinitializing.")
        today = datetime.date.today().isoformat()
        task_ids = add_prayer_sequence(service, tasklist_id, today)
        track["fajr_id"] = task_ids["Fajr"]
        track["fajr_date"] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        save_track(track)

    # Ensure iterate task exists
    ensure_iterate_task(service, tasklist_id)
    print("Program finished. Tasks are updated.")

if __name__ == "__main__":
    main()
