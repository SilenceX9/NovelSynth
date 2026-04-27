import asyncio
import json
import logging
import re
from pathlib import Path

def _split_into_segments(text: str, min_chars: int = 50, max_chars: int = 200) -> list[tuple[str, int]]:
    """Split text into segments at natural boundaries.
    Each segment should be 50-200 chars for readability.
    Returns list of (segment_text, paragraph_index).
    """
    paragraphs = re.split(r'\n\s*\n', text)
    results = []

    for para_idx, para in enumerate(paragraphs):
        if not para.strip():
            continue

        para = para.strip()
        # Short paragraph: keep as one segment
        if len(para) <= max_chars:
            results.append((para, para_idx))
            continue

        # Long paragraph: split at sentence boundaries
        # Try to split around 150-200 chars
        sentences = re.split(r'([。！？]+)', para)
        current = ""
        for s in sentences:
            if not s.strip():
                continue
            if re.match(r'^[。！？]+$', s):
                current += s
                # Check if current reached target length
                if len(current) >= min_chars:
                    results.append((current.strip(), para_idx))
                    current = ""
            else:
                current += s
                # Split when exceeds max_chars
                if len(current) >= max_chars:
                    results.append((current.strip(), para_idx))
                    current = ""
        if current.strip():
            # Last piece: if short, append to previous or keep separate
            if len(current) < min_chars and results:
                # Append to previous segment
                last_seg, last_para = results[-1]
                results[-1] = (last_seg + current.strip(), last_para)
            else:
                results.append((current.strip(), para_idx))

    if len(results) <= 1:
        results = [(text, 0)]

    return [(seg, para) for seg, para in results if seg]

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


async def _dehydrate_with_retry(chapter_text: str, context: GlobalContext) -> tuple[list[BlockResult], str | None]:
    """Wrap dehydrate_chapter with retries for transient failures."""
    last_exc = None
    for attempt in range(1, MAX_CHAPTER_RETRIES + 1):
        try:
            return await dehydrate_chapter(chapter_text, context), None
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


async def dehydrate_chapter(
    chapter_text: str,
    context: GlobalContext,
) -> list[BlockResult]:
    """脱水单章。分段分类，保留原文用于摘要展开。"""
    core_names = [c.name for c in context.characters if c.role in ("主角", "配角")]

    # 1. 先分割原文成片段（每段50-150字）
    segments = _split_into_segments(chapter_text)
    if not segments:
        return [BlockResult(text=chapter_text, layer=Layer.KEEP, output=chapter_text, original=None, paragraph=0)]

    # 2. 构建分类 prompt
    segment_list = "\n".join(
        f"[{i}] {text[:120]}{'...' if len(text) > 120 else ''}"
        for i, (text, _) in enumerate(segments[:20])  # 最多20个片段
    )

    classify_prompt = f"""你是网文精简编辑。对以下片段分类。

角色：{', '.join(core_names) if core_names else '无'}

片段列表：
{segment_list}

**必须删除70%以上的片段**。网文大部分是注水内容。

分类规则：
- keep（约25%）：仅主角关键对话、生死转折、战斗高潮
- delete（约70%）：环境描写、路人反应、赶路吃饭、外貌衣着、心理独白、重复说明
- summarize（约5%）：次要情节，输出20-50字摘要

返回 JSON：
{{"results": [
  {{"index": 0, "layer": "delete"}},
  {{"index": 1, "layer": "keep"}},
  {{"index": 2, "layer": "summarize", "summary": "陈平安送信遇到卢家"}}
]}}

严格执行删除，不要全部标keep。"""

    llm = _llm()
    try:
        data = await llm.chat_json([{"role": "user", "content": classify_prompt}])
        results_data = data.get("results", [])

        # 3. 根据分类结果构建输出
        results = []
        for i, (orig_text, para_idx) in enumerate(segments):
            seg_result = next((r for r in results_data if r.get("index") == i), None)

            if seg_result:
                layer_str = seg_result.get("layer", "keep")
                try:
                    layer = Layer(layer_str)
                except ValueError:
                    layer = Layer.KEEP
            else:
                layer = Layer.KEEP

            if layer == Layer.DELETE:
                continue

            if layer == Layer.SUMMARIZE:
                summary = seg_result.get("summary", orig_text[:50])
                results.append(BlockResult(
                    text=summary,
                    layer=layer,
                    output=summary,
                    original=orig_text,  # 保存原文用于展开
                    paragraph=para_idx
                ))
            else:
                # KEEP：使用原文
                results.append(BlockResult(
                    text=orig_text,
                    layer=layer,
                    output=orig_text,
                    original=None,
                    paragraph=para_idx
                ))

        if not results:
            return [BlockResult(text=chapter_text[:500], layer=Layer.KEEP, output=chapter_text[:500], original=None, paragraph=0)]

        logger.info(f"dehydrate_chapter: segments={len(segments)}, kept={len(results)}")

        return results
    except Exception:
        logger.exception("dehydrate_chapter failed")
        return [BlockResult(text=chapter_text, layer=Layer.KEEP, output=chapter_text, original=None, paragraph=0)]


def assemble_dehydrated(blocks: list[BlockResult]) -> str:
    """把 block 结果拼接为脱水文本。"""
    parts = []
    for b in blocks:
        if b.output:
            parts.append(b.output)
    return "\n\n".join(parts)


def assemble_structured(blocks: list[BlockResult]) -> list[dict]:
    """生成结构化输出。"""
    result = []
    for b in blocks:
        if not b.output:
            continue
        result.append({
            "layer": b.layer.value,
            "text": b.output,
            "original": b.original,  # 保存原文用于展开
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

    start_tokens = LLMClient.get_metrics()["total_tokens"]

    semaphore = asyncio.Semaphore(MAX_DEHYDRATE_CONCURRENCY)

    async def process_chapter(idx: int):
        async with semaphore:
            pause_event = tm.get_pause_event(task.book_id, TASK_DEHYDRATE)
            if pause_event.is_set():
                return None, idx, None

            ch = chapters[idx]
            step = f"脱水第 {idx+1} 章: {ch['title']}"
            await tm.save(TaskState(**{
                **task.to_dict(), "status": STATUS_RUNNING,
                "step": step, "current": idx + 1,
            }))

            blocks, error_reason = await _dehydrate_with_retry(ch["text"], context)

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
                if error_reason:
                    failed_list.append({"index": idx, "title": ch_result["title"], "error": error_reason})
                    await storage.save_single_chapter_dehydrated(task.book_id, idx, ch_result["title"], ch_result["text"])
                else:
                    chapter_results[idx] = ch_result
                    completed.add(idx)
                    await storage.save_single_chapter_dehydrated(task.book_id, idx, ch_result["title"], ch_result["text"])

                await _save_checkpoint(task.book_id, list(completed), failed_list)

                current_tokens = LLMClient.get_metrics()["total_tokens"] - start_tokens
                step_text = f"完成第 {idx+1}/{len(chapters)} 章"
                if failed_list:
                    step_text += f"（{len(failed_list)} 章失败）"
                await tm.save(TaskState(**{
                    **task.to_dict(), "status": STATUS_RUNNING,
                    "completed": sorted(completed),
                    "current": idx + 1,
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
    old_map = {ch["title"]: ch for ch in old_chapters}

    ordered = []
    all_structured = []
    for i, ch in enumerate(chapters):
        title = ch["title"]
        if i in chapter_results:
            chapter_blocks = chapter_results[i].get("blocks", [])
            for b in chapter_blocks:
                b["chapter"] = i
            ordered.append(chapter_results[i])
            all_structured.extend(chapter_blocks)
        elif title in old_map:
            ordered.append(old_map[title])

    full_dehydrated = "\n\n".join(r["text"] for r in ordered)
    await storage.save_dehydrated(task.book_id, full_dehydrated)

    existing_blocks = await storage.load_dehydrated_blocks(task.book_id)
    kept_blocks = [b for b in existing_blocks if b.get("chapter") not in chapter_results]
    await storage.save_dehydrated_blocks(task.book_id, kept_blocks + all_structured)
    await storage.save_chapter_dehydrated(task.book_id, [{"title": r["title"], "text": r["text"]} for r in ordered])
    await storage.mark_dehydrated(task.book_id)

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
        old_total = existing.total
        new_total = len(chapters)
        is_incremental = old_total > 0 and new_total > old_total

        if is_incremental:
            task = existing
            task.status = STATUS_RUNNING
            task.total = new_total
            task.step = "增量脱水中"
            task.started_at = time.time()
            tm.clear_paused(book_id, TASK_DEHYDRATE)
        else:
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