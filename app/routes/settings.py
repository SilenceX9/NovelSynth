from fastapi import APIRouter
from pydantic import BaseModel

from app.llm_client import PROVIDERS
from app.llm_config import load_llm_config, save_llm_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LLMConfigRequest(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key: str


class LLMConfigResponse(BaseModel):
    providers: dict
    current: dict


@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_config():
    return LLMConfigResponse(providers=PROVIDERS, current=load_llm_config())


@router.post("/llm")
async def save_config(req: LLMConfigRequest):
    save_llm_config({
        "provider": req.provider,
        "base_url": req.base_url,
        "model": req.model,
        "api_key": req.api_key,
    })
    return {"status": "ok"}
