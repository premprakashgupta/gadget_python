"""
gadget/utils/local_db.py
========================
Local SQLite buffer for all gadget data.
Everything captured on the gadget is written here first.
A separate batch_sync.py process reads and uploads to the Node.js server.

Tables:
  - attendance      : teacher presence sessions
  - session_activity: Mixed events (TRANSCRIPT segment or SNAPSHOT proof)
"""

import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/gadget_local.db')


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS attendance (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id          INTEGER NOT NULL,
                date                TEXT    NOT NULL,
                status              TEXT    NOT NULL DEFAULT 'PRESENT',
                entry_time          TEXT,
                exit_time           TEXT,
                last_pulse_time     TEXT,
                total_unavail_mins  REAL    DEFAULT 0,
                actual_avail_mins   REAL    DEFAULT 0,
                server_id           INTEGER,          -- set after sync
                synced              INTEGER DEFAULT 0, -- 0=pending, 1=synced
                created_at          TEXT    DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS session_activity (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                local_att_id    INTEGER NOT NULL,  -- references attendance.id (local)
                server_att_id   INTEGER,           -- set after attendance is synced
                timestamp       TEXT    NOT NULL,
                type            TEXT    NOT NULL,  -- 'TRANSCRIPT' or 'SNAPSHOT'
                image_path      TEXT,
                transcript      TEXT,
                synced          INTEGER DEFAULT 0,
                created_at      TEXT    DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (local_att_id) REFERENCES attendance(id)
            );
        """)
    print("[LocalDB] Initialised SQLite at:", os.path.abspath(DB_PATH))


# ─── Attendance ───────────────────────────────────────────────────────────────

def upsert_attendance(teacher_id, date, status='PRESENT', entry_time=None):
    """Return existing row ONLY if it hasn't bin 'exited' yet. Otherwise create fresh session."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM attendance WHERE teacher_id=? AND date=? AND exit_time IS NULL",
            (teacher_id, date)
        ).fetchone()
        if row:
            return dict(row)
        conn.execute(
            """INSERT INTO attendance (teacher_id, date, status, entry_time, last_pulse_time)
               VALUES (?, ?, ?, ?, ?)""",
            (teacher_id, date, status, entry_time,
             datetime.datetime.now().isoformat())
        )
        row = conn.execute(
            "SELECT * FROM attendance WHERE teacher_id=? AND date=? AND exit_time IS NULL ORDER BY id DESC LIMIT 1",
            (teacher_id, date)
        ).fetchone()
        return dict(row)


def update_pulse(local_att_id, total_unavail, actual_avail):
    """Update pulse timing fields after each detection cycle."""
    with _conn() as conn:
        conn.execute(
            """UPDATE attendance
               SET last_pulse_time=?, total_unavail_mins=?, actual_avail_mins=?, synced=0
               WHERE id=?""",
            (datetime.datetime.now().isoformat(), total_unavail, actual_avail, local_att_id)
        )


def set_attendance_synced(local_id, server_id):
    with _conn() as conn:
        conn.execute(
            "UPDATE attendance SET server_id=?, synced=1 WHERE id=?",
            (server_id, local_id)
        )
        # Also update session_activities that now know the server attendance id
        conn.execute(
            "UPDATE session_activity SET server_att_id=? WHERE local_att_id=?",
            (server_id, local_id)
        )


def get_unsynced_attendance():
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM attendance WHERE synced=0 ORDER BY id"
        ).fetchall()]


# ─── Session Activity (Transcripst & Snapshots) ──────────────────────────────

def insert_activity(local_att_id, timestamp, type, image_path=None, transcript=None):
    """Save a transcript segment or proof snapshot locally."""
    with _conn() as conn:
        # PULL server_att_id if the parent is already synced
        att = conn.execute("SELECT server_id FROM attendance WHERE id=?", (local_att_id,)).fetchone()
        server_att_id = att['server_id'] if att else None

        conn.execute(
            """INSERT INTO session_activity
               (local_att_id, server_att_id, timestamp, type, image_path, transcript)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (local_att_id, server_att_id, timestamp, type, image_path, transcript)
        )
    
    if type == 'TRANSCRIPT':
        print(f"[LocalDB] Saved Transcript: {transcript[:60]}...")
    else:
        print(f"[LocalDB] Saved Snapshot: {os.path.basename(image_path) if image_path else 'N/A'}")


def get_unsynced_activities():
    """Return activities whose parent attendance has been synced (server_att_id is set)."""
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT * FROM session_activity
               WHERE synced=0 AND server_att_id IS NOT NULL
               ORDER BY id"""
        ).fetchall()]


def set_activity_synced(local_id):
    with _conn() as conn:
        conn.execute("UPDATE session_activity SET synced=1 WHERE id=?", (local_id,))


# ─── Stats helper ─────────────────────────────────────────────────────────────

def get_stats():
    with _conn() as conn:
        att_total   = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
        att_pending = conn.execute("SELECT COUNT(*) FROM attendance WHERE synced=0").fetchone()[0]
        act_total   = conn.execute("SELECT COUNT(*) FROM session_activity").fetchone()[0]
        act_pending = conn.execute("SELECT COUNT(*) FROM session_activity WHERE synced=0").fetchone()[0]
    return {
        "attendance": {"total": att_total, "pending_sync": att_pending},
        "activity":   {"total": act_total, "pending_sync": act_pending},
    }
