import httpx
from app.config import settings


class LLMClient:
    def __init__(self):
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

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
