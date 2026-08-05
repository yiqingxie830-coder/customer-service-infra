from typing import Annotated, Literal, Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fastapi.middleware.cors import CORSMiddleware
from langgraph_sdk import get_sync_client, get_client
from langgraph_sdk.client import LangGraphClient

from app_backend.config import Settings, get_settings
from app_backend import database


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    client_type: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str


class UserListItem(BaseModel):
    id: str
    name: str | None = None
    email: str | None = None


class UserSaveRequest(BaseModel):
    id: str = Field(min_length=1)
    data: dict[str, Any]


class PromptItem(BaseModel):
    name: str
    content: str


class PromptUpdateRequest(BaseModel):
    content: str = Field(min_length=1)


class ExpertItem(BaseModel):
    name: str
    description: str
    load: str
    prompt: str


class ExpertUpdateRequest(BaseModel):
    description: str
    load: str
    prompt: str


app = FastAPI(title="Customer Service App Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_langgraph_client(settings: Annotated[Settings, Depends(get_settings)]) -> LangGraphClient:
    return get_client(url=settings.langgraph_base_url)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client: Annotated[LangGraphClient, Depends(get_langgraph_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResponse:
    try:
        client_type = request.client_type or "unknown"
        messages_payload = [message.model_dump() for message in request.messages]
        if messages_payload:
            try:
                formatted_msg = settings.client_type_message_template.format(
                    client_type, client_type=client_type
                )
            except Exception:
                formatted_msg = settings.client_type_message_template
            messages_payload[-1]["content"] += formatted_msg

        metadata = {
            "user_id": request.user_id,
            "session_id": request.session_id,
            "langfuse_user_id": request.user_id,
            "langfuse_session_id": request.session_id,
            "client_type": client_type,
        }

        final_state = await client.runs.wait(
            thread_id=None,
            assistant_id=settings.langgraph_assistant_id,
            input={
                "messages": messages_payload,
                "user_id": request.user_id,
            },
            metadata=metadata,
            config={
                "metadata": metadata,
            },
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    if not isinstance(final_state, dict):
        raise HTTPException(status_code=502, detail="LangGraph response was not a dictionary")
    
    final_response = final_state.get("final_response")
    if not isinstance(final_response, str) or not final_response:
        raise HTTPException(status_code=502, detail="LangGraph response did not include final_response")

    return ChatResponse(session_id=request.session_id, response=final_response)


@app.get("/users")
async def list_users(settings: Annotated[Settings, Depends(get_settings)]) -> list[UserListItem]:
    users_dict = await database.get_all_users(settings.db_path)
    result = []
    for user_id, user_data in users_dict.items():
        result.append(UserListItem(
            id=user_id,
            name=user_data.get("name"),
            email=user_data.get("email"),
        ))
    return result


@app.get("/users/{user_id}")
async def get_user_detail(
    user_id: str, 
    settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    user_data = await database.get_user(settings.db_path, user_id)
    if user_data is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user_id, "data": user_data}


@app.post("/users")
async def save_user(
    request: UserSaveRequest,
    settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    await database.save_user(settings.db_path, request.id, request.data)
    return {"status": "success", "id": request.id}


@app.get("/prompts")
async def list_prompts(settings: Annotated[Settings, Depends(get_settings)]) -> list[PromptItem]:
    prompts_list = await database.get_all_prompts(settings.db_path)
    return [PromptItem(**p) for p in prompts_list]


@app.put("/prompts/{name}")
async def update_prompt(
    name: str,
    request: PromptUpdateRequest,
    settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    await database.save_prompt(settings.db_path, name, request.content)
    return {"status": "success", "name": name}


@app.get("/experts")
async def list_experts(settings: Annotated[Settings, Depends(get_settings)]) -> list[ExpertItem]:
    experts_list = await database.get_all_experts(settings.db_path)
    return [ExpertItem(**e) for e in experts_list]


@app.get("/experts/{name}")
async def get_expert_detail(name: str, settings: Annotated[Settings, Depends(get_settings)]) -> ExpertItem:
    expert = await database.get_expert(settings.db_path, name)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")
    return ExpertItem(**expert)


@app.put("/experts/{name}")
async def update_expert(
    name: str,
    request: ExpertUpdateRequest,
    settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    await database.save_expert(settings.db_path, name, request.description, request.load, request.prompt)
    return {"status": "success", "name": name}


@app.delete("/experts/{name}")
async def delete_expert_endpoint(
    name: str,
    settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    await database.delete_expert(settings.db_path, name)
    return {"status": "success", "name": name}
