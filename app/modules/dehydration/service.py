import asyncio
import json
import logging
from pathlib import Path

from app.llm_client import LLMClient
from app.llm_config import load_llm_config
from app.models.context import GlobalContext
from app.models.dehydration import BlockResult, Layer
from app.modules.dehydration.prompt import DEHYDRATE_PROMPT
from app.task_manager import (
    TaskState, STATUS_PENDING, STATUS_RUNNING, STATUS_PAUSED, STATUS_DONE, STATUS_FAILED,
    get_task_manager, init_task_manager, TASK_DEHYDRATE,
)
from app.storage import Storage

logger = logging.getLogger(__name__)

BLOCK_MAX_CHARS = 300
MAX_DEHYDRATE_CONCURRENCY = 5


def _llm() -> LLMClient:
    cfg = load_llm_config()
    return LLMClient(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"])


def split_into_blocks(text: str) -> list[str]:
    """按段落切分，每块不超过 BLOCK_MAX_CHARS，段落边界对齐。"""
    paragraphs = text.split("\n\n")
    blocks = []
    current = []
    current_len = 0

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if current_len + len(p) > BLOCK_MAX_CHARS and current:
            blocks.append("\n\n".join(current))
            current = [p]
            current_len = len(p)
        else:
            current.append(p)
            current_len += len(p)

    if current:
        blocks.append("\n\n".join(current))
    return blocks


async def dehydrate_chapter(
    chapter_text: str,
    context: GlobalContext,
) -> list[BlockResult]:
    """脱水单章。返回每个 block 的判定结果。"""
    blocks = split_into_blocks(chapter_text)
    results = []

    core_names = [c.name for c in context.characters if c.role in ("主角", "配角")]
    foreshadow_descs = [f.description for f in context.foreshadows]

    prompt = DEHYDRATE_PROMPT.format(
        core_characters="、".join(core_names) if core_names else "无",
        main_plot_keywords="、".join(context.main_plot[:10]),
        foreshadows="、".join(foreshadow_descs) if foreshadow_descs else "无",
        key_items="、".join(context.key_items) if context.key_items else "无",
    )

    llm = _llm()
    for block in blocks:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": block},
        ]
        try:
            data = await llm.chat_json(messages)
            layer = Layer(data["layer"])
            output = data["output"]
        except Exception:
            # fallback: keep on error
            layer = Layer.KEEP
            output = block
        results.append(BlockResult(text=block, layer=layer, output=output))

    return results


def assemble_dehydrated(blocks: list[BlockResult]) -> str:
    """把 block 结果拼接为脱水文本。DELETE 的块跳过。"""
    parts = []
    for b in blocks:
        if b.layer == Layer.DELETE:
            continue
        parts.append(b.output)
    return "\n\n".join(parts)


def assemble_structured(blocks: list[BlockResult]) -> list[dict]:
    """生成结构化输出：保留每个非 DELETE 块的原文和脱水文本，用于前端展开。"""
    result = []
    for b in blocks:
        if b.layer == Layer.DELETE:
            continue
        result.append({
            "layer": b.layer.value,
            "text": b.output,
            "original": b.text if b.layer == Layer.SUMMARIZE else None,
        })
    return result


# ---- Checkpoint persistence ----

def _checkpoint_path(book_id: str) -> Path:
    return Path("data") / book_id / "dehydrate_checkpoint.json"


async def _save_checkpoint(book_id: str, completed: list[int]):
    p = _checkpoint_path(book_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"completed": sorted(completed)}, ensure_ascii=False), encoding="utf-8")


async def _load_checkpoint(book_id: str) -> set[int]:
    p = _checkpoint_path(book_id)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("completed", []))
    except Exception:
        return set()


# ---- Parallel task execution ----

async def _run_dehydrate_task(task: TaskState, context: GlobalContext, chapters: list[dict]):
    """Execute dehydrate task with parallel chapters and checkpoint resume."""
    storage = Storage()
    tm = get_task_manager(storage)
    completed = await _load_checkpoint(task.book_id)
    chapter_results: dict[int, dict] = {}

    # Per-task token tracking (not shared global)
    start_tokens = LLMClient.get_metrics()["total_tokens"]

    semaphore = asyncio.Semaphore(MAX_DEHYDRATE_CONCURRENCY)

    async def process_chapter(idx: int):
        async with semaphore:
            # Check pause state via in-memory event
            pause_event = tm.get_pause_event(task.book_id, TASK_DEHYDRATE)
            if pause_event.is_set():
                return None, idx

            ch = chapters[idx]
            step = f"脱水第 {idx+1} 章: {ch['title']}"
            await tm.save(TaskState(**{
                **task.to_dict(), "status": STATUS_RUNNING,
                "step": step, "current": idx + 1,
            }))

            try:
                blocks = await dehydrate_chapter(ch["text"], context)
            except Exception as e:
                logger.exception(f"[{task.book_id}] chapter {idx} failed: {e}")
                raise

            dehydrated_text = assemble_dehydrated(blocks)
            structured = assemble_structured(blocks)
            return {"title": ch["title"], "text": dehydrated_text, "blocks": structured}, idx

    # Build list of chapters to process
    pending = [i for i in range(len(chapters)) if i not in completed]
    logger.info(f"[{task.book_id}] dehydrate: {len(pending)}/{len(chapters)} chapters remaining")

    # Process chapters in parallel chunks
    for chunk_start in range(0, len(pending), MAX_DEHYDRATE_CONCURRENCY):
        chunk = pending[chunk_start:chunk_start + MAX_DEHYDRATE_CONCURRENCY]

        # Check if paused before starting chunk
        current = await tm.load(task.book_id, TASK_DEHYDRATE)
        if current and current.status == STATUS_PAUSED:
            await tm.save(TaskState(**{
                **task.to_dict(), "status": STATUS_PAUSED,
                "step": "已暂停",
            }))
            return

        results = await asyncio.gather(*[process_chapter(i) for i in chunk], return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                await tm.save(TaskState(**{
                    **task.to_dict(), "status": STATUS_FAILED,
                    "error": str(result), "step": "脱水失败",
                }))
                raise result

            ch_result, idx = result
            if ch_result is not None:
                chapter_results[idx] = ch_result
                completed.add(idx)
                await _save_checkpoint(task.book_id, list(completed))

                # Update task state with per-task tokens
                current_tokens = LLMClient.get_metrics()["total_tokens"] - start_tokens
                await tm.save(TaskState(**{
                    **task.to_dict(), "status": STATUS_RUNNING,
                    "completed": sorted(completed),
                    "current": idx + 1,
                    "tokens": current_tokens,
                    "step": f"完成第 {idx+1}/{len(chapters)} 章",
                }))

    # All chapters done - assemble final output
    step = "保存结果"
    await tm.save(TaskState(**{
        **task.to_dict(), "status": STATUS_RUNNING, "step": step,
        "current": len(chapters),
    }))

    # Load previously saved chapters to merge with new results
    old_chapters = await storage.load_chapter_dehydrated(task.book_id)
    old_map = {ch["title"]: ch for ch in old_chapters}

    # Merge: old chapters keep their dehydrated text, new chapters use new results
    ordered = []
    all_structured = []
    for i, ch in enumerate(chapters):
        title = ch["title"]
        if i in chapter_results:
            # New chapter from this run — add chapter_index to blocks
            chapter_blocks = chapter_results[i].get("blocks", [])
            for b in chapter_blocks:
                b["chapter"] = i
            ordered.append(chapter_results[i])
            all_structured.extend(chapter_blocks)
        elif title in old_map:
            # Existing chapter from previous run — preserve dehydrated text
            ordered.append(old_map[title])

    full_dehydrated = "\n\n".join(r["text"] for r in ordered)
    await storage.save_dehydrated(task.book_id, full_dehydrated)

    # Merge with existing blocks: old blocks keep their chapter index, new blocks get theirs
    existing_blocks = await storage.load_dehydrated_blocks(task.book_id)
    # Keep old blocks whose chapter isn't being re-processed
    kept_blocks = [b for b in existing_blocks if b.get("chapter") not in chapter_results]
    await storage.save_dehydrated_blocks(task.book_id, kept_blocks + all_structured)
    await storage.save_chapter_dehydrated(task.book_id, [{"title": r["title"], "text": r["text"]} for r in ordered])
    await storage.mark_dehydrated(task.book_id)

    # Keep checkpoint for future incremental runs (don't delete)
    await _save_checkpoint(task.book_id, sorted(completed))

    # Final token count and elapsed time
    import time
    final_tokens = LLMClient.get_metrics()["total_tokens"] - start_tokens
    elapsed = time.time() - task.started_at if task.started_at else 0.0
    final_task = TaskState(**{
        **task.to_dict(), "status": STATUS_DONE, "step": "完成",
        "current": len(chapters), "tokens": final_tokens, "elapsed": elapsed,
    })
    await tm.save(final_task)


async def start_or_resume_dehydrate(book_id: str, context: GlobalContext, chapters: list[dict]) -> TaskState:
    """Start or resume a dehydrate task. Incremental: keeps checkpoint, only processes new chapters."""
    import time
    storage = Storage()
    tm = get_task_manager(storage)

    existing = await tm.load(book_id, TASK_DEHYDRATE)

    if existing and existing.status in (STATUS_DONE, STATUS_FAILED):
        old_total = existing.total
        new_total = len(chapters)
        is_incremental = old_total > 0 and new_total > old_total

        if is_incremental:
            # Incremental: keep task state and checkpoint, only add new chapters
            task = existing
            task.status = STATUS_RUNNING
            task.total = new_total
            task.step = "增量脱水中"
            task.started_at = time.time()
            tm.clear_paused(book_id, TASK_DEHYDRATE)
        else:
            # Fresh start: clear old task and checkpoint for new run
            await tm.delete(book_id, TASK_DEHYDRATE)
            p = _checkpoint_path(book_id)
            if p.exists():
                p.unlink()
            task = TaskState(book_id=book_id, task_type=TASK_DEHYDRATE, total=new_total)
            task.started_at = time.time()
            tm.clear_paused(book_id, TASK_DEHYDRATE)
    elif existing and existing.status in (STATUS_RUNNING, STATUS_PAUSED):
        task = existing
        task.status = STATUS_RUNNING
        tm.clear_paused(book_id, TASK_DEHYDRATE)
    else:
        task = TaskState(book_id=book_id, task_type=TASK_DEHYDRATE, total=len(chapters))
        task.started_at = time.time()
        tm.clear_paused(book_id, TASK_DEHYDRATE)

    await tm.save(task)

    LLMClient.reset_metrics()
    asyncio.create_task(_run_dehydrate_task_wrapper(task, context, chapters))

    return task


async def _run_dehydrate_task_wrapper(task: TaskState, context: GlobalContext, chapters: list[dict], save_history: bool = True):
    """Wrapper that handles errors and saves final state to history.

    Args:
        save_history: Set False to skip history save (e.g. when caller handles it).
    """
    storage = Storage()
    tm = get_task_manager(storage)
    try:
        await _run_dehydrate_task(task, context, chapters)
        # Reload final task state from DB (includes elapsed time, tokens, completed)
        final_task = await tm.load(task.book_id, TASK_DEHYDRATE)
        if final_task and final_task.status == STATUS_DONE and save_history:
            await tm.save_history(task.book_id, TASK_DEHYDRATE, final_task)
    except Exception as e:
        logger.exception(f"[{task.book_id}] dehydrate task failed")
        await tm.save(TaskState(**{
            **task.to_dict(), "status": STATUS_FAILED,
            "error": str(e), "step": "脱水失败",
        }))


async def pause_dehydrate(book_id: str) -> TaskState | None:
    storage = Storage()
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_DEHYDRATE)
    if task and task.status == STATUS_RUNNING:
        task.status = STATUS_PAUSED
        task.step = "暂停中..."
        await tm.save(task)
        tm.set_paused(book_id, TASK_DEHYDRATE)
    return task


async def resume_dehydrate(book_id: str, context: GlobalContext, chapters: list[dict]) -> TaskState | None:
    storage = Storage()
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_DEHYDRATE)
    if task and task.status == STATUS_PAUSED:
        task.status = STATUS_RUNNING
        await tm.save(task)
        tm.clear_paused(book_id, TASK_DEHYDRATE)
        asyncio.create_task(_run_dehydrate_task_wrapper(task, context, chapters))
    return task
