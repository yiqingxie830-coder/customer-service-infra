# Kiri Lab Customer Service Project Guidelines

This file provides context about the Kiri Lab Customer Service project and will be automatically preloaded by Gemini/Antigravity.

## Project Structure

This project is a monorepo-style infrastructure workspace that orchestrates the following components:

- **`chat-board/`**: The frontend React/Vite application customized for Kiri Lab. Runs on port `3001`.
- **`app-backend/`**: A lightweight FastAPI translation layer that acts as a proxy between the frontend and the LangGraph APIs. Exposes `POST /chat`. Runs on port `8000`.
- **`customer-service-agent/`**: The LangGraph agent backend responsible for processing queries. It uses a dynamic router node to dispatch to experts stored in a local SQLite database (`db/store.sqlite`).

## Deployment Information

- **Server Stack Location**: The server stack is deployed at the SSH server `shared`.
- **Status**: The services are fully integrated and wired together end-to-end.

## Developing Guide

- **Frontend Submodule**: The `chat-board/` folder in this infra repository is a Git submodule mapping to the `Inherited/uni_board` repository.
  - **CRITICAL**: Do NOT modify files directly within the `chat-board` submodule in this workspace. 
  - Instead, always navigate to the original repository at `/Users/ben/Developer/projects/Inherited/uni_board` to make frontend modifications and run frontend commands.
  
- **Syncing API Spec**: When the `app-backend` FastAPI layer is updated, follow these steps to sync the API specification to the frontend:
  1. Generate the new `openapi.json` from the backend and save it directly to the original frontend repository:
     ```bash
     cd /Users/ben/Developer/projects/customer-service-infra/app-backend
     uv run python -c "import json; from app_backend.main import app; open('/Users/ben/Developer/projects/Inherited/uni_board/openapi.json', 'w').write(json.dumps(app.openapi(), indent=2))"
     ```
  2. Update the generated TypeScript API wrapper in the frontend repository:
     ```bash
     cd /Users/ben/Developer/projects/Inherited/uni_board
     npm run gen:api
     ```
  3. Commit and push the changes in the child repo:
     ```bash
     cd /Users/ben/Developer/projects/Inherited/uni_board
     git add openapi.json src/services/api.gen.ts
     git commit -m "chore: sync API spec from backend"
     git push
     ```
  4. Update the submodule pointer in the infra repository, then commit and push:
     ```bash
     cd /Users/ben/Developer/projects/customer-service-infra/chat-board
     git pull origin master
     cd ..
     git add chat-board
     git commit -m "chore: update chat-board submodule"
     git push
     ```

- **General Syncing and Deployment Routine**: The entire project is deployed on a remote server. To ensure the remote server picks up your changes, you **MUST ALWAYS** follow this synchronization routine after making changes to *any* repository or submodule:
  1. **Commit and Push Child Repositories**: Commit and push changes in the respective original child repositories (e.g., `/Users/ben/Developer/projects/Inherited/uni_board`).
  2. **Update Submodules in Infra**: Navigate to the corresponding submodule folder in the main infra repository (e.g., `/Users/ben/Developer/projects/customer-service-infra/chat-board`) and pull the latest changes (`git pull origin master` or `main`).
  3. **Commit and Push Main Infra Repo**: Navigate back to the infra root (`cd /Users/ben/Developer/projects/customer-service-infra`), add the updated submodule (`git add <submodule-folder>`), commit the submodule pointer update, and push the infra repository.
