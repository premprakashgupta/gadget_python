"""
batch_sync.py
=============
Reads all unsynced records from local SQLite and uploads to Node.js server.
Includes internet connectivity check — skips upload gracefully if offline.

Run manually or on a schedule:
    python batch_sync.py

Used internally by main.py when a sync is triggered.
"""

import os
import sys
import time
import socket
import datetime
import yaml

sys.path.insert(0, os.path.dirname(__file__))

from gadget.utils.local_db import (
    init_db, get_stats,
    get_unsynced_attendance, set_attendance_synced,
    get_unsynced_activities, set_activity_synced
)
from gadget.utils.sync_manager import SyncManager

# ─── Load config ──────────────────────────────────────────────────────────────
config_path = os.path.join(os.path.dirname(__file__), 'config/config.yaml')
with open(config_path) as f:
    config = yaml.safe_load(f)

sync = SyncManager(config['api']['url'])

def has_internet(host="8.8.8.8", port=53, timeout=3):
    """Quick connectivity check: try connecting to Google DNS."""
    # SKIP if localhost (development)
    if 'localhost' in config['api']['url'] or '127.0.0.1' in config['api']['url']:
        return True

    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except OSError:
        return False


def can_reach_server():
    """Check if the Node.js server is reachable."""
    import urllib.request
    try:
        urllib.request.urlopen(f"{config['api']['url']}/api/gadgets/list", timeout=3)
        return True
    except Exception:
        return False


def run_batch_sync():
    print(f"\n{'='*58}")
    print(f"    Batch Sync  —  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*58}")

    # Fetch device token from local hardware identifier (required to avoid 401s)
    sync.check_activation_status()

    # ── Connectivity check ────────────────────────────────────────────────────
    if not has_internet():
        print("     No internet connection. All data remains safely in SQLite.")
        print(f"{'='*58}\n")
        return False

    if not can_reach_server():
        print("     Server unreachable. Will retry next time.")
        print(f"{'='*58}\n")
        return False

    print("    Internet OK. Server reachable. Starting upload...")

    stats = get_stats()
    print(f"\n  Pending  -  Attendance: {stats['attendance']['pending_sync']}  "
          f"|  Activities: {stats['activity']['pending_sync']}\n")

    att_ok = att_fail = act_ok = act_fail = 0

    # ── Phase 1: Upload attendance ─────────────────────────────────────────────
    pending_att = get_unsynced_attendance()
    if not pending_att:
        print("    Attendance: nothing to sync.")
    else:
        print(f"    Uploading {len(pending_att)} attendance record(s)...")
        for att in pending_att:
            result = sync.sync_attendance(
                teacher_id=att['teacher_id'],
                date=att['date'],
                status=att['status'],
                entry_time=att['entry_time'],
                exit_time=att['exit_time']
            )
            if result and result.get('id'):
                set_attendance_synced(att['id'], result['id'])
                print(f"        #{att['id']}  teacher={att['teacher_id']}  {att['date']}  ->  server_id={result['id']}")
                att_ok += 1
            else:
                print(f"        #{att['id']}  failed — will retry next sync")
                att_fail += 1

    print()

    # ── Phase 2: Upload session activities (only when parent att is synced) ─────
    pending_act = get_unsynced_activities()
    if not pending_act:
        print("    Activities: nothing to sync.")
    else:
        print(f"    Uploading {len(pending_act)} activity record(s)...")
        for act in pending_act:
            result = sync.log_session_activity(
                attendance_id=act['server_att_id'],
                timestamp=act['timestamp'],
                activity_type=act['type'],
                image_path=act['image_path'],
                transcript=act['transcript']
            )
            
            label = act['type']
            if result and result.get('id'):
                set_activity_synced(act['id'])
                desc = (act['transcript'] or '')[:40] if act['type'] == 'TRANSCRIPT' else os.path.basename(act['image_path'] or 'N/A')
                print(f"        [{label}] {desc}  ->  server_id={result['id']}")
                act_ok += 1
            else:
                print(f"        [{label}] failed — will retry")
                act_fail += 1

    # ── Tell server sync is done ───────────────────────────────────────────────
    try:
        import requests
        hw = sync.hardware_id
        requests.post(f"{config['api']['url']}/api/gadgets/clear-sync/{hw}", timeout=5)
    except Exception:
        pass

    print()
    print(f"{'='*58}")
    print(f"    Result:  Attendance {att_ok}  {att_fail}   |  Activities {act_ok}  {act_fail} ")
    print(f"{'='*58}\n")
    return att_fail + act_fail == 0



if __name__ == "__main__":
    init_db()
    ok = run_batch_sync()
    sys.exit(0 if ok else 1)
