import asyncio
import json
import logging
from pathlib import Path

from app.config import settings
from app.llm_client import LLMClient
from app.models.context import GlobalContext, PartialContext
from app.modules.indexer.chapter_parser import parse_chapters
from app.modules.indexer.extractor import extract_batch
from app.modules.indexer.merger import merge_contexts
from app.task_manager import (
    TaskState, STATUS_PENDING, STATUS_RUNNING, STATUS_PAUSED, STATUS_DONE, STATUS_FAILED,
    get_task_manager, init_task_manager, TASK_INDEX,
)
from app.storage import Storage

logger = logging.getLogger(__name__)

# Max concurrent LLM calls during indexing
MAX_INDEX_CONCURRENCY = 2


def _partials_dir(book_id: str) -> Path:
    return Path("data") / book_id / "partials"


def _partial_path(book_id: str, batch_idx: int) -> Path:
    return _partials_dir(book_id) / f"batch_{batch_idx}.json"


async def _save_partial(book_id: str, batch_idx: int, partial: PartialContext):
    p = _partials_dir(book_id)
    p.mkdir(parents=True, exist_ok=True)
    _partial_path(book_id, batch_idx).write_text(
        partial.model_dump_json(), encoding="utf-8"
    )


async def _load_partials(book_id: str) -> dict[int, PartialContext]:
    d = _partials_dir(book_id)
    if not d.exists():
        return {}
    result = {}
    for f in d.glob("batch_*.json"):
        idx = int(f.stem.split("_")[1])
        result[idx] = PartialContext.model_validate_json(f.read_text(encoding="utf-8"))
    return result


async def _clear_partials(book_id: str):
    d = _partials_dir(book_id)
    if d.exists():
        for f in d.glob("batch_*.json"):
            f.unlink()


async def _run_index_task(task: TaskState, original_text: str, chapters: list[dict], book_title: str, incremental: bool = False):
    """Execute index task with parallel batches and checkpoint resume.

    Args:
        incremental: if True, load existing partials and only process new batches.
    """
    tm = get_task_manager()
    batch_size = settings.batch_size
    partials_map: dict[int, PartialContext] = {}

    if incremental:
        # Load existing partials from disk (only for incremental runs)
        partials_map = await _load_partials(task.book_id)
        completed = set(partials_map.keys())
    else:
        completed = set(task.completed)

    # Per-task token tracking
    start_tokens = LLMClient.get_metrics()["total_tokens"]

    semaphore = asyncio.Semaphore(MAX_INDEX_CONCURRENCY)

    async def process_batch(batch_idx: int):
        async with semaphore:
            # Check pause state via in-memory event
            pause_event = tm.get_pause_event(task.book_id, TASK_INDEX)
            if pause_event.is_set():
                return None, batch_idx

            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(chapters))
            step = f"提取第 {batch_start+1}-{batch_end} 章"
            await tm.save(TaskState(**{
                **task.to_dict(), "status": STATUS_RUNNING,
                "step": step, "current": batch_idx + 1,
            }))

            import asyncio

            retries = 2
            partial = None
            for attempt in range(retries):
                try:
                    partial = await extract_batch(chapters, batch_start, batch_end, task.book_id)
                    break
                except Exception as e:
                    if attempt == 0:
                        logger.warning(f"[{task.book_id}] batch {batch_idx} attempt {attempt+1} failed, retrying: {e}")
                    else:
                        logger.exception(f"[{task.book_id}] batch {batch_idx} failed after {retries} attempts")
                        raise
                    await asyncio.sleep(5 * (attempt + 1))

            # Persist partial to disk
            await _save_partial(task.book_id, batch_idx, partial)
            return partial, batch_idx

    # Build list of batches to process
    total_batches = (len(chapters) + batch_size - 1) // batch_size
    pending = [i for i in range(total_batches) if i not in completed]

    logger.info(f"[{task.book_id}] indexing: {len(pending)}/{total_batches} batches remaining"
                + (f" (incremental, {len(completed)} loaded)" if incremental else ""))

    # Process batches in parallel
    for chunk_start in range(0, len(pending), MAX_INDEX_CONCURRENCY):
        chunk = pending[chunk_start:chunk_start + MAX_INDEX_CONCURRENCY]

        # Check if paused before starting chunk
        current = await tm.load(task.book_id, TASK_INDEX)
        if current and current.status == STATUS_PAUSED:
            await tm.save(TaskState(**{
                **task.to_dict(), "status": STATUS_PAUSED,
                "step": "已暂停",
            }))
            return

        results = await asyncio.gather(*[process_batch(i) for i in chunk], return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                await tm.save(TaskState(**{
                    **task.to_dict(), "status": STATUS_FAILED,
                    "error": str(result), "step": "索引失败",
                }))
                raise result

            partial, batch_idx = result
            if partial is not None:
                partials_map[batch_idx] = partial
                completed.add(batch_idx)
                # Calculate per-task tokens
                current_tokens = LLMClient.get_metrics()["total_tokens"] - start_tokens
                await tm.save(TaskState(**{
                    **task.to_dict(), "status": STATUS_RUNNING,
                    "completed": sorted(completed),
                    "current": batch_idx + 1,
                    "tokens": current_tokens,
                    "step": f"完成第 {batch_idx+1}/{total_batches} 批",
                }))

    # All batches done - merge all partials
    step = "合并上下文"
    await tm.save(TaskState(**{
        **task.to_dict(), "status": STATUS_RUNNING, "step": step,
        "current": len(chapters),
    }))

    # Build ordered partials list (old + new)
    ordered_partials = [partials_map[i] for i in sorted(partials_map.keys())]
    ctx = merge_contexts(ordered_partials, book_title or f"book_{task.book_id}")

    # Final token count and elapsed time
    import time
    final_tokens = LLMClient.get_metrics()["total_tokens"] - start_tokens
    elapsed = time.time() - task.started_at if task.started_at else 0.0
    final_task = TaskState(**{
        **task.to_dict(), "status": STATUS_DONE, "step": "完成",
        "current": len(chapters), "tokens": final_tokens, "elapsed": elapsed,
        "completed": sorted(completed),
    })
    await tm.save(final_task)

    return ctx


async def start_or_resume_index(book_id: str, original_text: str, chapters: list[dict], book_title: str) -> TaskState:
    """Start or resume an indexing task."""
    import time
    storage = Storage()
    tm = get_task_manager(storage)

    existing = await tm.load(book_id, TASK_INDEX)
    incremental = False

    if existing and existing.status in (STATUS_DONE, STATUS_FAILED):
        # Determine if this is an incremental run (chapters grew but partials exist)
        old_total = existing.total
        new_total = len(chapters)
        incremental = old_total > 0 and new_total > old_total and (_partials_dir(book_id)).exists()

        if incremental:
            # Incremental: keep task state, only add new batches
            task = existing
            task.status = STATUS_RUNNING
            task.total = new_total
            task.step = "增量索引中"
            task.started_at = time.time()
            tm.clear_paused(book_id, TASK_INDEX)
        else:
            # Fresh start: clear old task and partials for new run
            await tm.delete(book_id, TASK_INDEX)
            await _clear_partials(book_id)
            task = TaskState(book_id=book_id, task_type=TASK_INDEX, total=new_total)
            task.started_at = time.time()
            tm.clear_paused(book_id, TASK_INDEX)
    elif existing and existing.status in (STATUS_RUNNING, STATUS_PAUSED):
        task = existing
        task.status = STATUS_RUNNING
        tm.clear_paused(book_id, TASK_INDEX)
    else:
        task = TaskState(book_id=book_id, task_type=TASK_INDEX, total=len(chapters))
        task.started_at = time.time()
        tm.clear_paused(book_id, TASK_INDEX)

    await tm.save(task)

    # Run the task
    asyncio.create_task(_run_index_task_wrapper(task, original_text, chapters, book_title, incremental))

    return task


async def _run_index_task_wrapper(task: TaskState, original_text: str, chapters: list[dict], book_title: str, incremental: bool = False):
    """Wrapper that saves final result."""
    storage = Storage()
    tm = get_task_manager(storage)
    try:
        ctx = await _run_index_task(task, original_text, chapters, book_title, incremental)
        if ctx is not None:
            await storage.save_context(book_id=task.book_id, ctx=ctx)
            await storage.mark_indexed(book_id=task.book_id)
        # Reload final task state from DB (includes elapsed time, tokens, completed)
        final_task = await tm.load(task.book_id, TASK_INDEX)
        if final_task and final_task.status == STATUS_DONE:
            await tm.save_history(task.book_id, TASK_INDEX, final_task)
    except Exception as e:
        logger.exception(f"[{task.book_id}] index task failed")
        await tm.save(TaskState(**{
            **task.to_dict(), "status": STATUS_FAILED,
            "error": str(e), "step": "索引失败",
        }))


async def pause_index(book_id: str) -> TaskState | None:
    storage = Storage()
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_INDEX)
    if task and task.status == STATUS_RUNNING:
        task.status = STATUS_PAUSED
        task.step = "暂停中..."
        await tm.save(task)
        tm.set_paused(book_id, TASK_INDEX)
    return task


async def resume_index(book_id: str, original_text: str, chapters: list[dict], book_title: str) -> TaskState | None:
    storage = Storage()
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_INDEX)
    if task and task.status == STATUS_PAUSED:
        task.status = STATUS_RUNNING
        await tm.save(task)
        tm.clear_paused(book_id, TASK_INDEX)
        asyncio.create_task(_run_index_task_wrapper(task, original_text, chapters, book_title))
    return task
