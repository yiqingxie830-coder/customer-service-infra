from functools import lru_cache
from collections.abc import Mapping
from pathlib import Path
import os

from pydantic import BaseModel, Field, field_validator


APP_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    langgraph_base_url: str = Field(min_length=1)
    langgraph_assistant_id: str = Field(default="chat_agent", min_length=1)
    langgraph_timeout_seconds: float = Field(default=60.0, gt=0)
    db_path: str = Field(default="../db/store.sqlite", min_length=1)
    client_type_message_template: str = Field(default="\n\n[Client Type: {client_type}]")

    @field_validator("langgraph_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


def read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_settings(env_file: Path | None = None, environ: Mapping[str, str] | None = None) -> Settings:
    dotenv_path = APP_BACKEND_DIR / ".env" if env_file is None else env_file
    source = read_dotenv(dotenv_path)
    runtime_env = os.environ if environ is None else environ

    def get(name: str) -> str | None:
        return runtime_env.get(name) or source.get(name)

    base_url = get("LANGGRAPH_BASE_URL")
    if base_url is None:
        raise RuntimeError("LANGGRAPH_BASE_URL must be set in the environment or app-backend/.env")

    timeout = get("LANGGRAPH_TIMEOUT_SECONDS")
    
    client_type_template = get("CLIENT_TYPE_MESSAGE_TEMPLATE")
    if client_type_template is not None:
        client_type_template = client_type_template.replace("\\n", "\n")
    else:
        client_type_template = "\n\n[Client Type: {client_type}]"

    return Settings(
        langgraph_base_url=base_url,
        langgraph_assistant_id=get("LANGGRAPH_ASSISTANT_ID") or "chat_agent",
        langgraph_timeout_seconds=float(timeout) if timeout is not None else 60.0,
        db_path=get("DB_PATH") or "../db/store.sqlite",
        client_type_message_template=client_type_template,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
