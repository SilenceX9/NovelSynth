import asyncio
import json
import logging
import re
from pathlib import Path

from app.llm_client import LLMClient
from app.llm_config import load_llm_config
from app.models.context import GlobalContext
from app.models.dehydration import BlockResult, Layer
from app.task_manager import (
    TaskState, STATUS_PENDING, STATUS_RUNNING, STATUS_PAUSED, STATUS_DONE, STATUS_FAILED,
    get_task_manager, init_task_manager, TASK_DEHYDRATE,
)
from app.storage import Storage

logger = logging.getLogger(__name__)

MAX_DEHYDRATE_CONCURRENCY = 5
MAX_CHAPTER_RETRIES = 3


async def _dehydrate_with_retry(chapter_text: str, context: GlobalContext, chapter_number: int = 0, chapter_title: str = "") -> tuple[list[BlockResult], str | None]:
    """Wrap dehydrate_chapter with retries for transient failures."""
    last_exc = None
    for attempt in range(1, MAX_CHAPTER_RETRIES + 1):
        try:
            return await dehydrate_chapter(chapter_text, context, chapter_number, chapter_title), None
        except Exception as e:
            last_exc = e
            if attempt < MAX_CHAPTER_RETRIES:
                logger.warning(f"dehydrate_chapter failed (attempt {attempt}/{MAX_CHAPTER_RETRIES}): {e}")
                await asyncio.sleep(1 * attempt)
            else:
                logger.error(f"dehydrate_chapter failed after {MAX_CHAPTER_RETRIES} attempts: {e}")
    error_msg = str(last_exc)[:200] if last_exc else "Unknown error"
    return [BlockResult(text=chapter_text, layer=Layer.KEEP, output=chapter_text, original=None, paragraph=0)], error_msg


def _llm() -> LLMClient:
    cfg = load_llm_config()
    return LLMClient(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"])


def _parse_mixed_blocks(llm_output: str, chapter_text: str) -> list[BlockResult]:
    """Parse LLM output with 【保留】/【概括】 markers into mixed BlockResults.

    【概括】 blocks may contain <原>...</原> tags with the specific original text that was cut.
    This gives each SUMMARIZE block its own independent expandable original, instead of
    sharing the full chapter text across all blocks.
    """
    pattern = r'【(保留|概括)】\s*\n?'
    parts = re.split(pattern, llm_output)

    # parts[0] is any text before the first marker (usually empty); skip it
    blocks: list[BlockResult] = []
    paragraph = 0
    i = 1
    while i < len(parts) - 1:
        marker = parts[i]
        text = parts[i + 1].strip()
        i += 2

        if not text:
            continue

        if marker == '保留':
            blocks.append(BlockResult(
                text=text, layer=Layer.KEEP, output=text,
                original=None, paragraph=paragraph,
            ))
        elif marker == '概括':
            # Extract <原>...</原> for independent original text
            original_match = re.search(r'<原>\s*(.*?)\s*</原>', text, re.DOTALL)
            if original_match:
                original_text = original_match.group(1).strip()
                summary_text = re.sub(r'<原>.*?</原>', '', text, flags=re.DOTALL).strip()
            else:
                original_text = ''
                summary_text = text
            blocks.append(BlockResult(
                text=summary_text, layer=Layer.SUMMARIZE, output=summary_text,
                original=original_text, paragraph=paragraph,
            ))
        paragraph += 1

    # Fallback: no markers found → treat as single summarize block
    if not blocks:
        return [BlockResult(
            text=llm_output.strip(), layer=Layer.SUMMARIZE,
            output=llm_output.strip(), original=chapter_text, paragraph=0,
        )]

    return blocks


async def dehydrate_chapter(
    chapter_text: str,
    context: GlobalContext,
    chapter_number: int = 0,
    chapter_title: str = "",
) -> list[BlockResult]:
    """脱水单章。LLM 输出混合格式：【保留】摘取原文关键段落，【概括】简要总结注水部分（含 <原> 独立原文）。"""
    core_names = [c.name for c in context.characters if c.role in ("主角", "配角")]

    # Truncate chapter text to avoid excessive token usage (most chapters < 8000 chars)
    truncated = chapter_text[:8000] if len(chapter_text) > 8000 else chapter_text

    # Early chapters (world-building): keep 40-50%. Later chapters: keep 25-30%.
    if chapter_number <= 15:
        keep_target = "40-50%"
        keep_note = "（世界观铺设期，保留比例放宽）"
    else:
        keep_target = "25-30%"
        keep_note = ""

    prompt = f"""你是一位网文精编。对以下章节做脱水处理：从原文中摘出关键段落原封不动保留，注水部分用一两句话概括。概括时注意保持剧情起承转合，不要割裂叙事。

核心角色：{', '.join(core_names) if core_names else '无'}
当前章节：第{chapter_number}章 {chapter_title}

## 输出格式（严格遵循）
将章节拆成若干片段：

【保留】
<从原文逐字摘取的关键段落>

【概括】
<一两句话概括此处被删的内容，需承上启下、保持叙事连贯>
<原>
<此处被删的原文段落>
</原>

## 保留 vs 概括
【保留】只用于：
- 主角的关键对话（逐字保留）
- 重大决定、内心转折
- 战斗的胜负手（不是过程）
- 世界观/功法/能力的首次披露
- 人物关系的建立与变化

【概括】用于所有其他内容。每个【概括】块必须包含 <原>...</原>，里面放被删的原文。

## 篇幅硬指标
- 【保留】总字数占全章 {keep_target} {keep_note}
- 不确定时选【概括】

## 章节内容
{truncated}"""

    llm = _llm()
    try:
        output = await llm.chat([{"role": "user", "content": prompt}])
        output = output.strip()

        if not output or len(output) < 20:
            return [BlockResult(text=chapter_text[:500], layer=Layer.KEEP, output=chapter_text[:500], original=None, paragraph=0)]

        blocks = _parse_mixed_blocks(output, chapter_text)
        keep_chars = sum(len(b.text) for b in blocks if b.layer == Layer.KEEP)
        summary_chars = sum(len(b.text) for b in blocks if b.layer == Layer.SUMMARIZE)
        logger.info(f"dehydrate_chapter: keep={keep_chars} chars, summarize={summary_chars} chars, original={len(chapter_text)} chars, blocks={len(blocks)}")

        return blocks
    except Exception:
        logger.exception("dehydrate_chapter failed")
        return [BlockResult(text=chapter_text[:500], layer=Layer.KEEP, output=chapter_text[:500], original=None, paragraph=0)]


def assemble_dehydrated(blocks: list[BlockResult]) -> str:
    """把 block 结果拼接为脱水文本。每章一个脱水块，章之间空行分隔。"""
    parts = []
    for b in blocks:
        if not b.output:
            continue
        if parts:
            parts.append("\n\n")
        parts.append(b.output)
    return "".join(parts)


def assemble_structured(blocks: list[BlockResult]) -> list[dict]:
    """生成结构化输出。每章一个 block，原文保存在 original 字段用于展开。"""
    result = []
    for b in blocks:
        if not b.output:
            continue
        result.append({
            "layer": b.layer.value,
            "text": b.output,
            "original": b.original,
            "paragraph": b.paragraph,
        })
    return result


# ---- Checkpoint persistence ----

def _checkpoint_path(book_id: str) -> Path:
    return Path("data") / book_id / "dehydrate_checkpoint.json"


async def _save_checkpoint(book_id: str, completed: list[int], failed: list[dict] | None = None):
    p = _checkpoint_path(book_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"completed": sorted(completed)}
    if failed:
        data["failed"] = failed
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


async def _load_checkpoint(book_id: str) -> tuple[set[int], list[dict]]:
    p = _checkpoint_path(book_id)
    if not p.exists():
        return set(), []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("completed", [])), data.get("failed", [])
    except Exception:
        return set(), []


# ---- Parallel task execution ----

async def _run_dehydrate_task(task: TaskState, context: GlobalContext, chapters: list[dict]):
    """Execute dehydrate task with parallel chapters and checkpoint resume."""
    storage = Storage()
    tm = get_task_manager(storage)
    completed, failed_list = await _load_checkpoint(task.book_id)
    chapter_results: dict[int, dict] = {}

    # Calculate global offset so progressive saves don't overwrite earlier chapters
    old_chapters = await storage.load_chapter_dehydrated(task.book_id)
    chapter_offset = len(old_chapters)

    start_tokens = LLMClient.get_metrics()["total_tokens"]

    semaphore = asyncio.Semaphore(MAX_DEHYDRATE_CONCURRENCY)

    async def process_chapter(idx: int):
        async with semaphore:
            pause_event = tm.get_pause_event(task.book_id, TASK_DEHYDRATE)
            if pause_event.is_set():
                return None, idx, None

            ch = chapters[idx]
            global_idx = chapter_offset + idx
            step = f"脱水第 {global_idx + 1} 章: {ch['title']}"
            await tm.save(TaskState(**{
                **task.to_dict(), "status": STATUS_RUNNING,
                "step": step, "current": global_idx + 1,
            }))

            blocks, error_reason = await _dehydrate_with_retry(ch["text"], context, global_idx + 1, ch["title"])

            dehydrated_text = assemble_dehydrated(blocks)
            structured = assemble_structured(blocks)
            return {"title": ch["title"], "text": dehydrated_text, "blocks": structured}, idx, error_reason

    pending = [i for i in range(len(chapters)) if i not in completed]
    logger.info(f"[{task.book_id}] dehydrate: {len(pending)}/{len(chapters)} chapters remaining")

    for chunk_start in range(0, len(pending), MAX_DEHYDRATE_CONCURRENCY):
        chunk = pending[chunk_start:chunk_start + MAX_DEHYDRATE_CONCURRENCY]

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
                error_msg = str(result)[:200]
                logger.exception(f"[{task.book_id}] chapter failed unexpectedly: {error_msg}")
                failed_ch_idx = chunk[results.index(result)] if results.index(result) < len(chunk) else -1
                if failed_ch_idx >= 0:
                    failed_list.append({"index": failed_ch_idx, "title": chapters[failed_ch_idx]["title"], "error": error_msg})
                    await _save_checkpoint(task.book_id, list(completed), failed_list)
                continue

            ch_result, idx, error_reason = result
            if ch_result is not None:
                global_idx = chapter_offset + idx
                if error_reason:
                    failed_list.append({"index": idx, "title": ch_result["title"], "error": error_reason})
                    await storage.save_single_chapter_dehydrated(task.book_id, global_idx, ch_result["title"], ch_result["text"])
                else:
                    chapter_results[idx] = ch_result
                    completed.add(idx)
                    await storage.save_single_chapter_dehydrated(task.book_id, global_idx, ch_result["title"], ch_result["text"])

                await _save_checkpoint(task.book_id, list(completed), failed_list)

                current_tokens = LLMClient.get_metrics()["total_tokens"] - start_tokens
                step_text = f"完成第 {global_idx + 1}/{len(chapters) + chapter_offset} 章"
                if failed_list:
                    step_text += f"（{len(failed_list)} 章失败）"
                await tm.save(TaskState(**{
                    **task.to_dict(), "status": STATUS_RUNNING,
                    "completed": sorted(completed),
                    "current": global_idx + 1,
                    "tokens": current_tokens,
                    "step": step_text,
                }))

    step = "保存结果"
    if failed_list:
        step = f"保存结果（{len(failed_list)} 章失败）"
    await tm.save(TaskState(**{
        **task.to_dict(), "status": STATUS_RUNNING, "step": step,
        "current": len(chapters),
    }))

    old_chapters = await storage.load_chapter_dehydrated(task.book_id)
    existing_blocks = await storage.load_dehydrated_blocks(task.book_id)
    old_titles = {oc["title"] for oc in old_chapters}
    new_processed = {chapters[i]["title"]: i for i in chapter_results}

    ordered = []
    all_structured = []

    # Keep old chapters that aren't being re-processed (preserve order)
    for old_idx, old_ch in enumerate(old_chapters):
        if old_ch["title"] in new_processed:
            new_i = new_processed[old_ch["title"]]
            new_result = chapter_results[new_i]
            ordered.append(new_result)
            for b in new_result.get("blocks", []):
                b["chapter"] = len(ordered) - 1
                all_structured.append(b)
        else:
            ordered.append(old_ch)
            for b in existing_blocks:
                if b.get("chapter") == old_idx:
                    b_copy = dict(b)
                    b_copy["chapter"] = len(ordered) - 1
                    all_structured.append(b_copy)

    # Append new chapters not in old_chapters
    for i, ch in enumerate(chapters):
        if i in chapter_results and ch["title"] not in old_titles:
            ordered.append(chapter_results[i])
            for b in chapter_results[i].get("blocks", []):
                b["chapter"] = len(ordered) - 1
                all_structured.append(b)

    full_dehydrated = "\n\n".join(r["text"] for r in ordered)
    await storage.save_dehydrated(task.book_id, full_dehydrated)
    await storage.save_dehydrated_blocks(task.book_id, all_structured)
    await storage.save_chapter_dehydrated(task.book_id, [{"title": r["title"], "text": r["text"]} for r in ordered])
    await storage.mark_dehydrated(task.book_id)

    # Compute and save dehydration stats
    keep_count = sum(1 for b in all_structured if b.get("layer") == "keep")
    summarize_count = sum(1 for b in all_structured if b.get("layer") == "summarize")
    # Use all chapters' original length, not just current batch
    all_chapters = await storage.load_chapters(task.book_id) or []
    clean_all = [c for c in all_chapters if not c.get("is_noise")]
    title_to_chars = {c["title"]: len(c["text"]) for c in clean_all}
    original_chars = sum(title_to_chars.get(r["title"], 0) for r in ordered)
    dehydrated_chars = len(full_dehydrated)
    stats = {
        "total_blocks": len(all_structured),
        "keep_blocks": keep_count,
        "summarize_blocks": summarize_count,
        "original_chars": original_chars,
        "dehydrated_chars": dehydrated_chars,
        "compression_ratio": round(1 - dehydrated_chars / max(original_chars, 1), 3),
        "chapters_processed": len(ordered),
    }
    await storage.save_dehydrate_stats(task.book_id, stats)

    await _save_checkpoint(task.book_id, sorted(completed), failed_list)

    import time
    final_tokens = LLMClient.get_metrics()["total_tokens"] - start_tokens
    elapsed = time.time() - task.started_at if task.started_at else 0.0
    step_text = "完成"
    if failed_list:
        step_text = f"完成（{len(failed_list)} 章失败，可重试）"
    final_task = TaskState(**{
        **task.to_dict(), "status": STATUS_DONE, "step": step_text,
        "current": len(chapters), "tokens": final_tokens, "elapsed": elapsed,
    })
    await tm.save(final_task)


async def start_or_resume_dehydrate(book_id: str, context: GlobalContext, chapters: list[dict]) -> TaskState:
    """Start or resume a dehydrate task."""
    import time
    storage = Storage()
    tm = get_task_manager(storage)

    existing = await tm.load(book_id, TASK_DEHYDRATE)

    if existing and existing.status in (STATUS_DONE, STATUS_FAILED):
        # New run: clear old task/checkpoint; dehydrated data stays for merge
        await tm.delete(book_id, TASK_DEHYDRATE)
        p = _checkpoint_path(book_id)
        if p.exists():
            p.unlink()
        task = TaskState(book_id=book_id, task_type=TASK_DEHYDRATE, total=len(chapters))
        task.started_at = time.time()
        tm.clear_paused(book_id, TASK_DEHYDRATE)
    elif existing and existing.status in (STATUS_RUNNING, STATUS_PAUSED):
        # Resume: keep task and checkpoint
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
    """Wrapper that handles errors and saves final state to history."""
    storage = Storage()
    tm = get_task_manager(storage)
    try:
        await _run_dehydrate_task(task, context, chapters)
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


async def retry_failed_chapters(book_id: str, context: GlobalContext, chapters: list[dict]) -> TaskState | None:
    """Retry only the chapters that failed in a previous dehydrate run."""
    import time
    storage = Storage()
    tm = get_task_manager(storage)

    completed, failed_list = await _load_checkpoint(book_id)
    if not failed_list:
        return None

    task = TaskState(book_id=book_id, task_type=TASK_DEHYDRATE, total=len(chapters))
    task.started_at = time.time()
    task.step = f"重试 {len(failed_list)} 章"
    tm.clear_paused(book_id, TASK_DEHYDRATE)
    await tm.save(task)

    failed_indices = {f["index"] for f in failed_list}
    for idx in failed_indices:
        completed.discard(idx)

    await _save_checkpoint(book_id, list(completed), [])

    LLMClient.reset_metrics()
    asyncio.create_task(_run_dehydrate_task_wrapper(task, context, chapters))
    return task