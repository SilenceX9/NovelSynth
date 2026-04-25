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
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
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


class LLMClient:
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
            return data["choices"][0]["message"]["content"]

    async def chat_json(self, messages: list[dict], temperature: float = 0.3, max_retries: int = 2) -> dict:
        """调 LLM 并强制返回 JSON。失败 retry。"""
        for attempt in range(max_retries + 1):
            text = await self.chat(messages, temperature)
            # strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            try:
                import json
                return json.loads(text)
            except json.JSONDecodeError:
                if attempt == max_retries:
                    raise ValueError(f"LLM 返回非 JSON（已重试 {max_retries} 次）: {text[:200]}")
        raise RuntimeError("unreachable")
