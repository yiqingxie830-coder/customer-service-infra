# App Backend

Thin FastAPI translation layer between the frontend and the LangGraph customer service agent, with direct CRUD access to the shared SQLite database.

## Contract

### Chat Execution
`POST /chat` requires a user ID, session ID, and the full chat history (optionally takes `client_type`, which defaults to `"unknown"` if omitted):

```json
{
  "user_id": "u_001",
  "session_id": "session-123",
  "client_type": "web",
  "messages": [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello"},
    {"role": "user", "content": "Can you help?"}
  ]
}
```

The backend forwards the full history to the LangGraph server (`http://127.0.0.1:2024` by default) using the LangGraph SDK and returns:

```json
{
  "session_id": "session-123",
  "response": "Happy to help."
}
```

### Administrative CRUD Endpoints (SQLite Store)
The backend connects directly to `db/store.sqlite` to service management requests:

#### Users (`/users`)
- `GET /users` - Returns a list of all users (`id`, `name`, `email`).
- `GET /users/{user_id}` - Returns the full JSON configuration and data object for a specific user.
- `POST /users` - Creates or updates a user profile. Requires JSON body with `id` and `data` (dictionary).

#### Prompts (`/prompts`)
- `GET /prompts` - Returns a list of all system prompts (`name`, `content`).
- `PUT /prompts/{name}` - Updates prompt markdown content (`{"content": "..."}`).

#### Experts (`/experts`)
- `GET /experts` - Returns a list of all expert definitions (`name`, `description`, `load`, `prompt`).
- `GET /experts/{name}` - Returns a specific expert definition.
- `PUT /experts/{name}` - Updates an expert definition (`{"description": "...", "load": "...", "prompt": "..."}`).
- `DELETE /experts/{name}` - Deletes an expert definition.

## Configuration

Create `app-backend/.env` from `.env.example`:

```bash
cp .env.example .env
```

| variable | required | default | purpose |
|---|---:|---|---|
| `LANGGRAPH_BASE_URL` | yes | - | Base URL for the running LangGraph server. |
| `LANGGRAPH_ASSISTANT_ID` | no | `chat_agent` | LangGraph assistant/graph to invoke. |
| `LANGGRAPH_TIMEOUT_SECONDS` | no | `60` | HTTP timeout for the LangGraph request. |
| `DB_PATH` | no | `../db/store.sqlite` | Path to the shared SQLite database file. |
| `CLIENT_TYPE_MESSAGE_TEMPLATE` | no | `"\n\n[Client Type: {client_type}]"` | Template appended to the last chat message sent to the LangGraph agent. |

## Development

```bash
uv sync
uv run uvicorn app_backend.main:app --reload --port 8000
uv run pytest
```

## End-to-end Chain Check

With the app backend and LangGraph server both running, validate the full chat chain:

```bash
uv run python scripts/health_check.py --base-url http://localhost:8000
```

The script posts a real `POST /chat` request to the app backend. A passing result confirms that the database is readable, LangGraph is reachable, and the full multi-turn response flow succeeds.
