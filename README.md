# PTRK – Prayer Task Tracker

PTRK is a Python-based tool to automatically track Islamic prayer times as Google Tasks.
It can run as a daemon, automatically adding the next sequence of prayers when the current Fajr task is completed,
and provides an “iterate” task to force-add the next day’s prayers.

Features
--------
- Auto-adds the next five prayers: Zuhr, Asr, Maghrib, Isha, Fajr (unorthodox order so you can see the next day’s Fajr).
- Provides an “Iterate” task to force-add the next prayer sequence for planning future days.
- Keeps track of completed Fajr tasks in a non-volatile `.dat` file.
- Runs as a daemon, periodically checking for completed tasks and updating automatically.
- Uses Google Tasks API and Aladhan API for prayer timings.

Getting Started
---------------

1. Clone the repository:

    git clone https://github.com/ONDER1E/ptrk.git
    cd ptrk

2. Install dependencies:

    pip install -r requirements.txt

   requirements.txt should contain at least:

    google-api-python-client
    google-auth-httplib2
    google-auth-oauthlib
    requests

3. Setup Google API Credentials:

   - Go to https://console.cloud.google.com/
   - Create a project and enable the Google Tasks API.
   - Create OAuth 2.0 Client ID credentials.
   - Download `credentials.json` and place it in the project folder.

4. First run:

    python prayer_tasks.py

   - Initializes task tracking, creates the next 5 prayer tasks, and sets up the Iterate task if missing.

5. Running the daemon:

    python prayer_daemon.py

   - Runs continuously and checks for:
     - Completion of the current Fajr task to auto-add the next sequence.
     - Completion of the Iterate task to force-add the next prayer sequence.
   - Adjust the interval in `prayer_daemon.py` to comply with Google Tasks rate limits (default: 5–10 minutes).

File Structure
--------------
prtk/
│
├─ prayer_tasks.py       # Core logic, object-oriented
├─ prayer_daemon.py      # Function-oriented daemon for continuous execution
├─ trk.dat               # Tracks the current Fajr task (auto-generated)
├─ credentials.json      # Google OAuth credentials (not included in repo)
├─ requirements.txt      # Dependencies
└─ README.md

Security
--------
- Never commit `credentials.json` or `token.json` to Git. Add them to `.gitignore`.
- `trk.dat` stores task IDs for internal tracking and is safe to include locally.

Customization
-------------
- You can change your city and country for prayer timings in `prayer_tasks.py`.
- Adjust prayer sequence or daemon check interval as needed.
