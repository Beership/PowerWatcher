"""SQLite persistence: one row per minute plus a per-day rollup."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .paths import db_path

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS minute (
    ts        INTEGER PRIMARY KEY,
    on_s      REAL NOT NULL DEFAULT 0,
    active_s  REAL NOT NULL DEFAULT 0,
    asleep_s  REAL NOT NULL DEFAULT 0,
    dc_w      REAL NOT NULL DEFAULT 0,
    wall_w    REAL NOT NULL DEFAULT 0,
    cpu_pct   REAL NOT NULL DEFAULT 0,
    gpu_pct   REAL NOT NULL DEFAULT 0,
    gpu_w     REAL NOT NULL DEFAULT 0,
    -- Raw signals so history can be re-modelled after a settings change.
    -- NULL marks rows written before these columns existed.
    cpu_busy_pct REAL,
    gpu_smi_w    REAL,
    screen_on_s  REAL,
    app          TEXT
);

CREATE INDEX IF NOT EXISTS idx_minute_ts ON minute(ts);

CREATE TABLE IF NOT EXISTS daily (
    day       TEXT PRIMARY KEY,
    on_s      REAL NOT NULL DEFAULT 0,
    active_s  REAL NOT NULL DEFAULT 0,
    asleep_s  REAL NOT NULL DEFAULT 0,
    kwh       REAL NOT NULL DEFAULT 0,
    cost      REAL NOT NULL DEFAULT 0,
    standby_kwh REAL NOT NULL DEFAULT 0,
    tariff_sig TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


@dataclass
class Minute:
    ts: int
    on_s: float
    active_s: float
    asleep_s: float
    dc_w: float
    wall_w: float
    cpu_pct: float
    gpu_pct: float
    gpu_w: float
    cpu_busy_pct: float | None = None
    gpu_smi_w: float | None = None
    screen_on_s: float | None = None
    app: str | None = None

    @property
    def kwh(self) -> float:
        """Grid energy for the powered-on part of this minute.

        watt * seconds / 3_600_000 = kWh.
        """
        return max(0.0, self.on_s) * max(0.0, self.wall_w) / 3_600_000.0


@dataclass
class Day:
    day: str
    on_s: float
    active_s: float
    asleep_s: float
    kwh: float
    cost: float
    standby_kwh: float = 0.0


def day_key(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def day_start_ts(day: str) -> int:
    d = datetime.strptime(day, "%Y-%m-%d")
    return int(d.timestamp())


class Store:
    """Thread-safe wrapper. The sampler writes, the UI reads."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a database was first created."""
        minute_cols = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(minute)")
        }
        for col, decl in (
            ("cpu_busy_pct", "REAL"),
            ("gpu_smi_w", "REAL"),
            ("screen_on_s", "REAL"),
            ("app", "TEXT"),
        ):
            if col not in minute_cols:
                self._conn.execute(f"ALTER TABLE minute ADD COLUMN {col} {decl}")
        daily_cols = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(daily)")
        }
        if "standby_kwh" not in daily_cols:
            self._conn.execute(
                "ALTER TABLE daily ADD COLUMN standby_kwh REAL NOT NULL DEFAULT 0"
            )

    # ---------------------------------------------------------------- writes
    def upsert_minute(self, row: Minute) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO minute (ts, on_s, active_s, asleep_s, dc_w, wall_w,
                                       cpu_pct, gpu_pct, gpu_w,
                                       cpu_busy_pct, gpu_smi_w, screen_on_s, app)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(ts) DO UPDATE SET
                       on_s=excluded.on_s, active_s=excluded.active_s,
                       asleep_s=excluded.asleep_s, dc_w=excluded.dc_w,
                       wall_w=excluded.wall_w, cpu_pct=excluded.cpu_pct,
                       gpu_pct=excluded.gpu_pct, gpu_w=excluded.gpu_w,
                       cpu_busy_pct=excluded.cpu_busy_pct,
                       gpu_smi_w=excluded.gpu_smi_w,
                       screen_on_s=excluded.screen_on_s,
                       app=excluded.app""",
                (
                    row.ts,
                    row.on_s,
                    row.active_s,
                    row.asleep_s,
                    row.dc_w,
                    row.wall_w,
                    row.cpu_pct,
                    row.gpu_pct,
                    row.gpu_w,
                    row.cpu_busy_pct,
                    row.gpu_smi_w,
                    row.screen_on_s,
                    row.app,
                ),
            )
            self._conn.commit()

    def update_power_many(self, updates: list[tuple[float, float, float, int]]) -> None:
        """Bulk re-model: (dc_w, wall_w, gpu_w, ts)."""
        if not updates:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE minute SET dc_w=?, wall_w=?, gpu_w=? WHERE ts=?", updates
            )
            self._conn.commit()

    def save_day(self, row: Day, tariff_sig: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO daily (day, on_s, active_s, asleep_s, kwh, cost,
                                      standby_kwh, tariff_sig)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(day) DO UPDATE SET
                       on_s=excluded.on_s, active_s=excluded.active_s,
                       asleep_s=excluded.asleep_s, kwh=excluded.kwh,
                       cost=excluded.cost, standby_kwh=excluded.standby_kwh,
                       tariff_sig=excluded.tariff_sig""",
                (
                    row.day,
                    row.on_s,
                    row.active_s,
                    row.asleep_s,
                    row.kwh,
                    row.cost,
                    row.standby_kwh,
                    tariff_sig,
                ),
            )
            self._conn.commit()

    def clear_daily(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM daily")
            self._conn.commit()

    def clear_all(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM minute")
            self._conn.execute("DELETE FROM daily")
            self._conn.commit()

    # ----------------------------------------------------------------- reads
    def _row_to_minute(self, r) -> Minute:
        return Minute(
            ts=r["ts"],
            on_s=r["on_s"],
            active_s=r["active_s"],
            asleep_s=r["asleep_s"],
            dc_w=r["dc_w"],
            wall_w=r["wall_w"],
            cpu_pct=r["cpu_pct"],
            gpu_pct=r["gpu_pct"],
            gpu_w=r["gpu_w"],
            cpu_busy_pct=r["cpu_busy_pct"],
            gpu_smi_w=r["gpu_smi_w"],
            screen_on_s=r["screen_on_s"],
            app=r["app"],
        )

    def minutes(self, start_ts: int, end_ts: int) -> list[Minute]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM minute WHERE ts >= ? AND ts < ? ORDER BY ts",
                (start_ts, end_ts),
            )
            return [self._row_to_minute(r) for r in cur.fetchall()]

    def all_minutes(self) -> list[Minute]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM minute ORDER BY ts")
            return [self._row_to_minute(r) for r in cur.fetchall()]

    def latest_minute(self) -> Minute | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM minute ORDER BY ts DESC LIMIT 1").fetchone()
        return self._row_to_minute(r) if r is not None else None

    def days(self, start_day: str, end_day: str) -> list[Day]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM daily WHERE day >= ? AND day <= ? ORDER BY day",
                (start_day, end_day),
            )
            return [self._row_to_day(r) for r in cur.fetchall()]

    def all_days(self) -> list[Day]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM daily ORDER BY day")
            return [self._row_to_day(r) for r in cur.fetchall()]

    @staticmethod
    def _row_to_day(r) -> Day:
        return Day(
            day=r["day"],
            on_s=r["on_s"],
            active_s=r["active_s"],
            asleep_s=r["asleep_s"],
            kwh=r["kwh"],
            cost=r["cost"],
            standby_kwh=r["standby_kwh"] or 0.0,
        )

    def distinct_days(self) -> list[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT DISTINCT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS d "
                "FROM minute ORDER BY d"
            )
            return [r["d"] for r in cur.fetchall() if r["d"]]

    def day_minutes(self, day: str) -> list[Minute]:
        start = day_start_ts(day)
        return self.minutes(start, start + 86400)

    def first_day(self) -> date | None:
        with self._lock:
            r = self._conn.execute("SELECT MIN(ts) AS t FROM minute").fetchone()
        if not r or r["t"] is None:
            return None
        return datetime.fromtimestamp(r["t"]).date()

    def month_kwh(self, year: int, month: int, upto_ts: int | None = None) -> float:
        start = datetime(year, month, 1).timestamp()
        end = datetime(year + (month == 12), month % 12 + 1, 1).timestamp()
        if upto_ts is not None:
            end = min(end, upto_ts)
        with self._lock:
            r = self._conn.execute(
                "SELECT SUM(on_s*wall_w) AS wh FROM minute WHERE ts >= ? AND ts < ?",
                (int(start), int(end)),
            ).fetchone()
        return float(r["wh"] or 0.0) / 3_600_000.0

    # ------------------------------------------------------------------ misc
    def vacuum(self) -> None:
        with self._lock:
            self._conn.execute("VACUUM")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
