import json
import os
import uuid
from pathlib import Path

import aiosqlite

from app.config import settings
from app.models.context import GlobalContext


class Storage:
    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir or settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "app.db"

    def _book_dir(self, book_id: str) -> Path:
        d = self.data_dir / book_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def create_book(self, title: str, original_text: str) -> str:
        book_id = uuid.uuid4().hex[:12]
        book_dir = self._book_dir(book_id)
        (book_dir / "original.txt").write_text(original_text, encoding="utf-8")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS books "
                "(book_id TEXT PRIMARY KEY, title TEXT, "
                "indexed INTEGER DEFAULT 0, dehydrated INTEGER DEFAULT 0)"
            )
            await db.execute(
                "INSERT INTO books (book_id, title) VALUES (?, ?)",
                (book_id, title),
            )
            await db.commit()
        return book_id

    async def create_book_epub(self, title: str, chapters: list[dict]) -> str:
        """Create a book entry for EPUB upload. Saves chapters.json and a minimal original.txt."""
        book_id = uuid.uuid4().hex[:12]
        book_dir = self._book_dir(book_id)

        # Save chapters as the primary data source
        import json
        (book_dir / "chapters.json").write_text(
            json.dumps(chapters, ensure_ascii=False), encoding="utf-8"
        )

        # Also save original.txt with combined chapter texts for compatibility
        combined = "\n\n".join(f"{ch['title']}\n{ch['text']}" for ch in chapters if not ch.get("is_noise"))
        (book_dir / "original.txt").write_text(combined, encoding="utf-8")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS books "
                "(book_id TEXT PRIMARY KEY, title TEXT, "
                "indexed INTEGER DEFAULT 0, dehydrated INTEGER DEFAULT 0)"
            )
            await db.execute(
                "INSERT INTO books (book_id, title) VALUES (?, ?)",
                (book_id, title),
            )
            await db.commit()
        return book_id

    async def save_original(self, book_id: str, text: str):
        self._book_dir(book_id)
        (self.data_dir / book_id / "original.txt").write_text(text, encoding="utf-8")

    async def load_original(self, book_id: str) -> str:
        return (self.data_dir / book_id / "original.txt").read_text(encoding="utf-8")

    async def save_chapters(self, book_id: str, chapters: list[dict]):
        """Save parsed chapters as JSON for efficient access and chapter selection."""
        import json
        path = self.data_dir / book_id / "chapters.json"
        path.write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")

    async def load_chapters(self, book_id: str) -> list[dict] | None:
        """Load parsed chapters. Returns None if not yet parsed."""
        import json
        path = self.data_dir / book_id / "chapters.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    async def load_original(self, book_id: str) -> str:
        return (self.data_dir / book_id / "original.txt").read_text(encoding="utf-8")

    async def save_context(self, book_id: str, ctx: GlobalContext):
        path = self.data_dir / book_id / "context.json"
        path.write_text(ctx.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    async def load_context(self, book_id: str) -> GlobalContext | None:
        path = self.data_dir / book_id / "context.json"
        if not path.exists():
            return None
        return GlobalContext.model_validate_json(path.read_text(encoding="utf-8"))

    async def save_dehydrated(self, book_id: str, text: str):
        path = self.data_dir / book_id / "dehydrated.txt"
        path.write_text(text, encoding="utf-8")

    async def load_dehydrated(self, book_id: str) -> str:
        path = self.data_dir / book_id / "dehydrated.txt"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    async def save_dehydrated_blocks(self, book_id: str, blocks: list[dict]):
        import json
        path = self.data_dir / book_id / "dehydrated_blocks.json"
        path.write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")

    async def load_dehydrated_blocks(self, book_id: str) -> list[dict]:
        import json
        path = self.data_dir / book_id / "dehydrated_blocks.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    async def save_chapter_dehydrated(self, book_id: str, chapters: list[dict]):
        """Save per-chapter dehydration results for EPUB export.
        Each dict: {"title": str, "text": str}.
        """
        import json
        path = self.data_dir / book_id / "dehydrated_chapters.json"
        path.write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")

    async def save_single_chapter_dehydrated(self, book_id: str, chapter_idx: int, title: str, text: str):
        """Save a single dehydrated chapter immediately as it completes, enabling progressive reading."""
        import json
        path = self.data_dir / book_id / "dehydrated_chapters.json"
        chapters: list[dict] = []
        if path.exists():
            chapters = json.loads(path.read_text(encoding="utf-8"))
        # Ensure list is long enough
        while len(chapters) <= chapter_idx:
            chapters.append({"title": "", "text": ""})
        chapters[chapter_idx] = {"title": title, "text": text}
        path.write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")

    async def load_chapter_dehydrated(self, book_id: str) -> list[dict]:
        import json
        path = self.data_dir / book_id / "dehydrated_chapters.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    async def get_status(self, book_id: str) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS books "
                "(book_id TEXT PRIMARY KEY, title TEXT, "
                "indexed INTEGER DEFAULT 0, dehydrated INTEGER DEFAULT 0)"
            )
            async with db.execute(
                "SELECT indexed, dehydrated FROM books WHERE book_id = ?",
                (book_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return {"indexed": False, "dehydrated": False}
        return {"indexed": bool(row[0]), "dehydrated": bool(row[1])}

    async def mark_indexed(self, book_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE books SET indexed = 1 WHERE book_id = ?", (book_id,)
            )
            await db.commit()

    async def mark_dehydrated(self, book_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE books SET dehydrated = 1 WHERE book_id = ?", (book_id,)
            )
            await db.commit()

    async def list_books(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS books "
                "(book_id TEXT PRIMARY KEY, title TEXT, "
                "indexed INTEGER DEFAULT 0, dehydrated INTEGER DEFAULT 0)"
            )
            async with db.execute(
                "SELECT book_id, title, indexed, dehydrated FROM books ORDER BY rowid DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {
                "book_id": r[0],
                "title": r[1],
                "indexed": bool(r[2]),
                "dehydrated": bool(r[3]),
            }
            for r in rows
        ]

    async def delete_book(self, book_id: str):
        import shutil
        book_dir = self.data_dir / book_id
        if book_dir.exists():
            shutil.rmtree(book_dir)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM books WHERE book_id = ?", (book_id,))
            await db.commit()
