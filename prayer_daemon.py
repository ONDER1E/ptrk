import time
import datetime
from prayer_tasks import PrayerTaskManager, ITERATE_TASK_TITLE

# Poll interval in seconds (safe for free API usage)
POLL_INTERVAL = 300  # 5 minutes

def run_daemon():
    manager = PrayerTaskManager()
    
    while True:
        print(f"[{datetime.datetime.now()}] Checking Fajr and Iterate tasks...")
        
        # Auto-add if Fajr completed
        manager.check_and_update_fajr()
        
        # Handle Iterate task
        manager.check_and_update_iterate()
        
        print(f"Sleeping for {POLL_INTERVAL} seconds...\n")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_daemon()
