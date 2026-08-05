# Architecture Overview

This repository coordinates the Customer Service system components.

## Core Components

- **`chat-board/`**: A React/Vite/TypeScript frontend application providing the user interface for customer service.
- **`app-backend/`**: A FastAPI service that proxies chat execution requests (`POST /chat`) to the LangGraph backend. It connects directly to `db/store.sqlite` to provide REST CRUD endpoints for managing `users`, `prompts`, and `experts`.
- **`customer-service-agent/`**: A LangGraph multi-agent backend that routes and processes customer queries using specialist expert agents and review gates. It reads user configurations, system prompts, and expert definitions directly from `db/store.sqlite`.

## Data Persistence Strategy

The system uses a unified persistent SQLite database located at `db/store.sqlite`. This decouples configuration and business data from source code, prevents server hot-reload loops on data changes, and allows live updates to prompts and expert behaviors.

### Database Tables

The database schema (managed via `db/migrate_schema.py`) includes:
- `users`: Profiles and CRM attributes stored as JSON blobs.
- `prompts`: System prompts (`chat_agent.system.md`, `response_guidelines.md`, `fallback.md`).
- `experts`: Specialist agent definitions (`medical`, `sales`, `emotional`) along with their routing descriptions and load strategies (`always`, `optional`, `never`).
- `escalations`, `failed_replies`, `purchases`: Audit logs and extracted business intentions.

`app-backend` exposes CRUD endpoints for `users`, `prompts`, and `experts`, enabling frontend administrative management without relying on the LangGraph execution runtime.

### Deployment Information
- The server stack is deployed on the SSH server `shared`.
- All services integrate seamlessly with the shared `db/store.sqlite` database file.
