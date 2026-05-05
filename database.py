"""
database.py  –  Synergy Dashboard Tool
SQLite persistence layer: students, behaviours, field mappings, settings.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

APP_DIR = Path.home() / ".synergy_tool"
DB_FILE = APP_DIR / "synergy.db"


class DB:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────────

    def _init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            student_ref  TEXT    DEFAULT '',
            year_group   INTEGER DEFAULT 7,
            form_class   TEXT    DEFAULT '',
            phones       TEXT    DEFAULT '[]',
            notes        TEXT    DEFAULT '',
            synergy_url  TEXT    DEFAULT '',
            sync_time    TEXT,
            created      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS behaviours (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            btype       TEXT    NOT NULL CHECK(btype IN ('praise','sanction')),
            points      INTEGER DEFAULT 1,
            reason      TEXT    DEFAULT '',
            event_date  TEXT    DEFAULT (datetime('now')),
            week        INTEGER,
            term        TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS mappings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            field       TEXT UNIQUE NOT NULL,
            selector    TEXT DEFAULT '',
            url_pattern TEXT DEFAULT '',
            sample_text TEXT DEFAULT '',
            updated     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            k TEXT PRIMARY KEY,
            v TEXT DEFAULT ''
        );
        """)
        self.conn.commit()

    # ── Settings ──────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)", (key, str(value))
        )
        self.conn.commit()

    # ── Students ──────────────────────────────────────────────────────────

    def add_student(
        self,
        name: str,
        ref: str = "",
        year: int = 7,
        form: str = "",
        phones: Optional[List[str]] = None,
        url: str = "",
    ) -> int:
        c = self.conn.execute(
            "INSERT INTO students(name,student_ref,year_group,form_class,phones,synergy_url)"
            " VALUES(?,?,?,?,?,?)",
            (name, ref, year, form, json.dumps(phones or []), url),
        )
        self.conn.commit()
        return c.lastrowid  # type: ignore

    def update_student(self, sid: int, **kwargs):
        if "phones" in kwargs:
            kwargs["phones"] = json.dumps(kwargs["phones"])
        sets = ", ".join(f"{k}=?" for k in kwargs)
        self.conn.execute(
            f"UPDATE students SET {sets}, sync_time=datetime('now') WHERE id=?",
            (*kwargs.values(), sid),
        )
        self.conn.commit()

    def get_students(self, search: str = "") -> List[Dict]:
        if search:
            rows = self.conn.execute(
                "SELECT * FROM students"
                " WHERE name LIKE ? OR form_class LIKE ? OR student_ref LIKE ?"
                " ORDER BY name",
                (f"%{search}%",) * 3,
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM students ORDER BY name"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["phones"] = json.loads(d.get("phones") or "[]")
            result.append(d)
        return result

    def get_student(self, sid: int) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM students WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["phones"] = json.loads(d.get("phones") or "[]")
        return d

    def delete_student(self, sid: int):
        self.conn.execute("DELETE FROM students WHERE id=?", (sid,))
        self.conn.commit()

    def student_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]

    # ── Behaviours ────────────────────────────────────────────────────────

    def add_behaviour(
        self,
        student_id: int,
        btype: str,
        points: int = 1,
        reason: str = "",
        date: Optional[str] = None,
    ):
        week = datetime.now().isocalendar()[1]
        self.conn.execute(
            "INSERT INTO behaviours(student_id,btype,points,reason,event_date,week)"
            " VALUES(?,?,?,?,?,?)",
            (student_id, btype, points, reason, date or datetime.now().isoformat(), week),
        )
        self.conn.commit()

    def get_behaviours(self, student_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM behaviours WHERE student_id=? ORDER BY event_date DESC",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_behaviour(self, bid: int):
        self.conn.execute("DELETE FROM behaviours WHERE id=?", (bid,))
        self.conn.commit()

    def get_student_stats(self, student_id: int) -> Dict:
        row = self.conn.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN btype='praise'   THEN points ELSE 0 END), 0) AS praise,
                COALESCE(SUM(CASE WHEN btype='sanction' THEN points ELSE 0 END), 0) AS sanctions,
                COUNT(*) AS total
            FROM behaviours WHERE student_id=?""",
            (student_id,),
        ).fetchone()
        return dict(row) if row else {"praise": 0, "sanctions": 0, "total": 0}

    def get_all_stats(self) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT s.id, s.name, s.year_group, s.form_class,
                COALESCE(SUM(CASE WHEN b.btype='praise'   THEN b.points ELSE 0 END), 0) AS praise,
                COALESCE(SUM(CASE WHEN b.btype='sanction' THEN b.points ELSE 0 END), 0) AS sanctions
            FROM students s
            LEFT JOIN behaviours b ON b.student_id = s.id
            GROUP BY s.id
            ORDER BY s.name"""
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Mappings ──────────────────────────────────────────────────────────

    def save_mapping(self, field: str, selector: str, url_pattern: str = "", sample: str = ""):
        self.conn.execute(
            """INSERT OR REPLACE INTO mappings(field,selector,url_pattern,sample_text,updated)
               VALUES(?,?,?,?,datetime('now'))""",
            (field, selector, url_pattern, sample),
        )
        self.conn.commit()

    def get_mappings(self) -> Dict[str, Dict]:
        rows = self.conn.execute("SELECT * FROM mappings").fetchall()
        return {r["field"]: dict(r) for r in rows}

    def delete_mapping(self, field: str):
        self.conn.execute("DELETE FROM mappings WHERE field=?", (field,))
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ── Timetables ────────────────────────────────────────────────────────

    def init_timetable_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS timetables (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            image_path  TEXT    NOT NULL,
            captured_at TEXT    DEFAULT (datetime('now')),
            week_label  TEXT    DEFAULT '',
            ocr_text    TEXT    DEFAULT '',
            teachers    TEXT    DEFAULT '[]'
        );
        """)
        self.conn.commit()

    def add_timetable(self, student_id: int, image_path: str,
                      ocr_text: str = "", teachers: list = None,
                      week_label: str = "") -> int:
        import json as _json
        c = self.conn.execute(
            "INSERT INTO timetables(student_id,image_path,week_label,ocr_text,teachers)"
            " VALUES(?,?,?,?,?)",
            (student_id, image_path, week_label, ocr_text,
             _json.dumps(teachers or []))
        )
        self.conn.commit()
        return c.lastrowid

    def get_timetables(self, student_id: int) -> list:
        import json as _json
        rows = self.conn.execute(
            "SELECT * FROM timetables WHERE student_id=? ORDER BY captured_at DESC",
            (student_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["teachers"] = _json.loads(d.get("teachers") or "[]")
            result.append(d)
        return result

    def get_all_timetables(self) -> list:
        import json as _json
        rows = self.conn.execute(
            """SELECT t.*, s.name as student_name, s.form_class, s.year_group
               FROM timetables t JOIN students s ON s.id = t.student_id
               ORDER BY t.captured_at DESC"""
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["teachers"] = _json.loads(d.get("teachers") or "[]")
            result.append(d)
        return result

    def delete_timetable(self, tid: int):
        row = self.conn.execute(
            "SELECT image_path FROM timetables WHERE id=?", (tid,)
        ).fetchone()
        if row:
            import os
            try:
                os.remove(row[0])
            except Exception:
                pass
        self.conn.execute("DELETE FROM timetables WHERE id=?", (tid,))
        self.conn.commit()

    def get_all_teachers_from_timetables(self) -> list:
        """Return sorted unique teacher names extracted across all timetables."""
        import json as _json
        rows = self.conn.execute(
            "SELECT teachers FROM timetables"
        ).fetchall()
        seen = set()
        for row in rows:
            for t in _json.loads(row[0] or "[]"):
                if t.strip():
                    seen.add(t.strip())
        return sorted(seen)
