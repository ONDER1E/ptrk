**PTRK – Prayer Task Tracker**

PTRK is a Python-based tool to automatically track Islamic prayer times as Google Tasks.
It can run as a daemon, automatically adding the next sequence of prayers when the current Fajr task is completed,
and provides an “iterate” task to force-add the next day’s prayers.

Features:
- Auto-adds the next five prayers: Zuhr, Asr, Maghrib, Isha, Fajr (unorthodox order so you can see the next day’s Fajr).
- Provides an “Iterate” task to force-add the next prayer sequence for planning future days.
- Keeps track of completed Fajr tasks in a non-volatile .dat file.
- Runs as a daemon, periodically checking for completed tasks and updating automatically.
