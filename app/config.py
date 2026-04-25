from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    data_dir: str = "data"
    batch_size: int = 10  # chapters per LLM batch in indexer

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
