"""Task state manager with SQLite persistence."""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict

import aiosqlite

from app.storage import Storage

logger = logging.getLogger(__name__)

TASK_INDEX = "index"
TASK_DEHYDRATE = "dehydrate"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


@dataclass
class TaskState:
    book_id: str
    task_type: str
    status: str = STATUS_PENDING
    total: int = 0
    current: int = 0
    step: str = ""
    tokens: int = 0
    started_at: float = 0.0
    elapsed: float = 0.0
    error: str = ""
    # checkpoint: list of completed batch indices (for index) or chapter indices (for dehydrate)
    completed: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["completed"] = self.completed
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TaskState":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


class TaskManager:
    """Manages task state persistence in SQLite. Thread-safe for single-process use."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # In-memory pause events for fast signal propagation
        self._pause_events: dict[str, asyncio.Event] = {}

    def _task_key(self, book_id: str, task_type: str) -> str:
        return f"{book_id}:{task_type}"

    def get_pause_event(self, book_id: str, task_type: str) -> asyncio.Event:
        """Return (or create) the pause event for a task. Set = paused."""
        key = self._task_key(book_id, task_type)
        if key not in self._pause_events:
            self._pause_events[key] = asyncio.Event()
        return self._pause_events[key]

    def set_paused(self, book_id: str, task_type: str):
        """Signal pause immediately via in-memory event."""
        key = self._task_key(book_id, task_type)
        if key not in self._pause_events:
            self._pause_events[key] = asyncio.Event()
        self._pause_events[key].set()

    def clear_paused(self, book_id: str, task_type: str):
        """Clear the pause signal (for resume)."""
        key = self._task_key(book_id, task_type)
        if key in self._pause_events:
            self._pause_events[key].clear()

    async def _init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS task_state ("
                "book_id TEXT, task_type TEXT, state_json TEXT, "
                "PRIMARY KEY (book_id, task_type))"
            )
            await db.execute(
                "CREATE TABLE IF NOT EXISTS task_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "book_id TEXT, task_type TEXT, status TEXT, "
                "total INTEGER, tokens INTEGER, elapsed REAL, "
                "created_at TEXT)"
            )
            await db.commit()

    async def save(self, state: TaskState):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO task_state VALUES (?, ?, ?)",
                             (state.book_id, state.task_type, json.dumps(state.to_dict(), ensure_ascii=False)))
            await db.commit()

    async def load(self, book_id: str, task_type: str) -> TaskState | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT state_json FROM task_state WHERE book_id = ? AND task_type = ?",
                (book_id, task_type)
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return TaskState.from_dict(json.loads(row[0]))

    async def delete(self, book_id: str, task_type: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM task_state WHERE book_id = ? AND task_type = ?",
                             (book_id, task_type))
            await db.commit()

    async def list_active(self) -> list[dict]:
        """Return all tasks that are not done or failed."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT state_json FROM task_state") as cursor:
                rows = await cursor.fetchall()
        result = []
        for row in rows:
            state = TaskState.from_dict(json.loads(row[0]))
            if state.status in (STATUS_DONE, STATUS_FAILED):
                continue
            result.append(state.to_dict())
        return result

    async def save_history(self, book_id: str, task_type: str, state: TaskState):
        """Archive a completed task's final metrics to history."""
        import datetime
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO task_history (book_id, task_type, status, total, tokens, elapsed, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (book_id, task_type, state.status, state.total, state.tokens, state.elapsed,
                 datetime.datetime.now().isoformat()),
            )
            await db.commit()

    async def list_history(self, book_id: str, task_type: str) -> list[dict]:
        """Return task history for a book."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, status, total, tokens, elapsed, created_at FROM task_history "
                "WHERE book_id = ? AND task_type = ? ORDER BY id DESC",
                (book_id, task_type),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {"id": r[0], "status": r[1], "total": r[2], "tokens": r[3],
             "elapsed": r[4], "created_at": r[5]}
            for r in rows
        ]

    async def clear_completed(self, book_id: str, task_type: str):
        """Delete completed task state (called when starting a fresh run on same book)."""
        await self.delete(book_id, task_type)
        # Also delete checkpoint files for dehydrate
        if task_type == TASK_DEHYDRATE:
            from pathlib import Path
            p = Path("data") / book_id / "dehydrate_checkpoint.json"
            if p.exists():
                p.unlink()


# Global singleton, lazy-init
_task_mgr: TaskManager | None = None


def get_task_manager(storage: Storage | None = None) -> TaskManager:
    global _task_mgr
    if _task_mgr is None:
        db_path = str((storage.data_dir / "app.db") if storage else Storage().db_path)
        _task_mgr = TaskManager(db_path)
    return _task_mgr


async def init_task_manager(storage: Storage):
    """Initialize task manager with correct DB path."""
    global _task_mgr
    _task_mgr = TaskManager(str(storage.db_path))
    await _task_mgr._init()
    return _task_mgr
