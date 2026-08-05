# Running the Full Stack Locally

This document outlines the steps to run the complete Kiri Lab Customer Service infrastructure locally for development and testing.

The infrastructure consists of three main components plus a shared persistence store:
1. **Database Store (`db/store.sqlite`)**: Standalone SQLite database storing user profiles, dynamic system prompts, expert definitions, escalations, failed replies, and purchase records.
2. **LangGraph Agent (`customer-service-agent`)**: The multi-agent backend responsible for conversation routing, expert consultation, and review gating.
3. **App Backend (`app-backend`)**: A FastAPI service acting as a proxy between the frontend and LangGraph, while providing direct CRUD endpoints for user, prompt, and expert management.
4. **Frontend (`chat-board`)**: The React/Vite web user interface.

---

## 0. Initialize / Seed the Database (First Run Only)

The entire system shares a persistent SQLite database located at `db/store.sqlite`. Before running the stack for the first time—or if you need to reset the schema and seed default prompts—run the migration script:

1. Open a terminal and navigate to the repository root:
   ```bash
   cd /Users/ben/Developer/projects/customer-service-infra
   ```
2. Run the migration script to initialize tables and seed default prompts from `db/prompts/`:
   ```bash
   cd db
   uv run python migrate_schema.py --overwrite
   ```
   *Note: Using `--overwrite` re-seeds and overwrites prompts in the database with the files in `db/prompts/*.md`.*

---

## 1. Start the LangGraph Agent

The LangGraph Agent runs on local port `2024` and connects directly to `db/store.sqlite` for user data and dynamic system prompts.

1. Open a new terminal and navigate to the agent directory:
   ```bash
   cd /Users/ben/Developer/projects/customer-service-infra/customer-service-agent
   ```
2. Start the dev server using the custom wrapper script (silences WatchFiles log spam):
   ```bash
   uv run python scripts/dev.py dev --port 2024
   ```
   *Alternatively, standard `uv run langgraph dev --port 2024` also works.*
   *The server will start on `http://127.0.0.1:2024`.*

---

## 2. Start the App Backend (FastAPI)

The FastAPI service acts as a proxy (`POST /chat`) to LangGraph and provides REST APIs (`/users`, `/prompts`, `/experts`) backed directly by `db/store.sqlite`.

1. Open a new terminal and navigate to the backend directory:
   ```bash
   cd /Users/ben/Developer/projects/customer-service-infra/app-backend
   ```
2. Start the FastAPI server using `uvicorn`:
   ```bash
   uv run uvicorn app_backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   *The server will start on `http://127.0.0.1:8000`.*

---

## 3. Start the Frontend (React/Vite)

The `chat-board` folder is a Git submodule mapping to the customized React frontend.

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd /Users/ben/Developer/projects/customer-service-infra/chat-board
   ```
2. Install dependencies (if you haven't already):
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *The UI will start locally (typically at `http://localhost:3000` or `http://localhost:3001` depending on port configuration).*

---

## Verification & Troubleshooting

### Automated Health Check
To verify that the database is readable, the LangGraph server is responding, and the end-to-end chain through the app backend is working:
```bash
cd /Users/ben/Developer/projects/customer-service-infra
uv run python app-backend/scripts/health_check.py --base-url http://localhost:8000
```

### Common Issues
- **Missing Prompts or Users / Database Errors:** If an agent fails to load a prompt at runtime or `app-backend` returns database errors, run `cd db && uv run python migrate_schema.py --overwrite` to re-initialize `db/store.sqlite`.
- **API Spec Synchronization:** When modifying endpoints or schemas in `app-backend/app_backend/main.py`, always sync `openapi.json` and regenerate TypeScript API types for the frontend following the steps in `AGENTS.md`.
