import json
import re
import httpx
from app.config import settings

# 主流 LLM 平台预设
PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-coder-plus"],
    },
    "custom": {
        "base_url": "",
        "models": [],
    },
}


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON，支持 markdown 包裹、前后缀、尾随逗号。"""
    # 1. strip markdown code fences
    if "```" in text:
        pattern = r"```(?:json)?\s*\n?([\s\S]*?)```"
        match = re.search(pattern, text)
        if match:
            text = match.group(1).strip()
    # 2. find JSON object boundaries using brace counting
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no '{' found", text, 0)
    depth = 0
    end = start
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if depth != 0:
        raise json.JSONDecodeError("unbalanced braces", text, start)
    raw = text[start : end + 1]
    # try parse directly first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # fix trailing commas: [1, 2,] -> [1, 2]  and  {"a": 1,} -> {"a": 1}
        fixed = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(fixed)


class LLMClient:
    # Shared metrics accumulator
    _metrics = {"total_tokens": 0, "total_cost_input": 0.0, "total_cost_output": 0.0, "call_count": 0, "elapsed": 0.0, "_start": 0.0}

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

    async def chat(self, messages: list[dict], temperature: float = 0.3) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            # Track usage
            usage = data.get("usage", {})
            in_tokens = usage.get("prompt_tokens", 0)
            out_tokens = usage.get("completion_tokens", 0)
            LLMClient._metrics["total_tokens"] += in_tokens + out_tokens
            LLMClient._metrics["call_count"] += 1
            choices = data.get("choices", [])
            if not choices:
                raise ValueError(f"LLM 返回空响应: {json.dumps(data, ensure_ascii=False)[:300]}")
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError(f"LLM 返回无内容: {json.dumps(data, ensure_ascii=False)[:300]}")
            return content

    @classmethod
    def reset_metrics(cls):
        import time
        cls._metrics = {"total_tokens": 0, "total_cost_input": 0.0, "total_cost_output": 0.0, "call_count": 0, "elapsed": 0.0, "_start": time.time()}

    @classmethod
    def get_metrics(cls) -> dict:
        import time
        m = dict(cls._metrics)
        if cls._metrics.get("_start"):
            m["elapsed"] = round(time.time() - cls._metrics["_start"], 1)
        return m

    async def chat_json(self, messages: list[dict], temperature: float = 0.3, max_retries: int = 2) -> dict:
        """调 LLM 并强制返回 JSON。失败 retry。"""
        last_error = None
        for attempt in range(max_retries + 1):
            text = await self.chat(messages, temperature)
            try:
                return _extract_json(text)
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                if attempt == max_retries:
                    raise ValueError(f"LLM 返回非 JSON（已重试 {max_retries} 次）: {text[:500]}") from e
        raise RuntimeError("unreachable")
