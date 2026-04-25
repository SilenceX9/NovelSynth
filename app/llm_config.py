import json
from pathlib import Path
from app.config import settings

_CONFIG_PATH = Path(settings.data_dir) / "llm_config.json"


def load_llm_config() -> dict:
    """读取 LLM 配置，优先从文件读取，不存在则返回默认值。"""
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {
        "provider": "openai",
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "api_key": "",
    }


def save_llm_config(data: dict):
    """保存 LLM 配置到文件。"""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
