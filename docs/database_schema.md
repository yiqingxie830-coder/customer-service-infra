# Database Schema

The standalone SQLite database (`db/store.sqlite`) serves as the primary data store for business data independent of the agent execution graph. It is accessed by both `app-backend` and `customer-service-agent`.

To initialize or migrate the database schema, run:
```bash
uv run python db/migrate_schema.py
```

---

## `users` Table
Stores arbitrary CRM profile data for each user.

- **`id`** (`TEXT PRIMARY KEY`): Unique identifier for the user (e.g., `u_001`).
- **`data`** (`TEXT NOT NULL`): JSON blob containing user details (e.g., `{"name": "Alice", "email": "alice@example.com"}`).
- **`created_at`** (`TIMESTAMP`): Creation timestamp.
- **`updated_at`** (`TIMESTAMP`): Last update timestamp.

---

## `prompts` Table
Stores raw Markdown system prompts used across agents and pipelines (e.g., `chat_agent.system.md`, `response_guidelines.md`, `fallback.md`).

- **`name`** (`TEXT PRIMARY KEY`): The name of the prompt file/identifier.
- **`content`** (`TEXT NOT NULL`): The Markdown instructions.
- **`created_at`** (`TIMESTAMP`): Creation timestamp.
- **`updated_at`** (`TIMESTAMP`): Last update timestamp.

---

## `experts` Table
Stores dynamic expert agent definitions and their loading strategies.

- **`name`** (`TEXT PRIMARY KEY`): Identifier of the expert (e.g., `medical`, `sales`, `emotional`).
- **`description`** (`TEXT NOT NULL`): Description of the expert's specialty used for routing decisions.
- **`load`** (`TEXT NOT NULL`): Execution loading strategy (`always`, `optional`, or `never`).
- **`prompt`** (`TEXT NOT NULL`): Dedicated Markdown system instructions for the expert.
- **`created_at`** (`TIMESTAMP`): Creation timestamp.
- **`updated_at`** (`TIMESTAMP`): Last update timestamp.

---

## `escalations` Table
Records conversation turns triggered for manual or review escalation.

- **`id`** (`INTEGER PRIMARY KEY AUTOINCREMENT`): Unique record ID.
- **`thread_id`** (`TEXT`): Conversation session/thread identifier.
- **`user_id`** (`TEXT`): Associated user ID.
- **`user_name`** (`TEXT`): Associated user display name.
- **`reason`** (`TEXT`): Reason given for escalation.
- **`flagged_rules`** (`TEXT`): Specific guideline rules flagged during review.
- **`notes`** (`TEXT`): Reviewer or system notes explaining the escalation.
- **`draft_response`** (`TEXT`): The draft response that was intercepted prior to escalation.
- **`selected_experts`** (`TEXT`): Summary of experts consulted during the turn.
- **`expert_advice`** (`TEXT`): Synthesized advice collected from experts.
- **`last_user_message`** (`TEXT`): The user message that triggered the turn.
- **`turn_count`** (`INTEGER`): Conversation turn index.
- **`created_at`** (`TIMESTAMP`): Creation timestamp.

---

## `failed_replies` Table
Audit log of replies that failed guideline verification or formatting checks.

- **`id`** (`INTEGER PRIMARY KEY AUTOINCREMENT`): Unique record ID.
- **`thread_id`** (`TEXT`): Conversation session/thread identifier.
- **`user_id`** (`TEXT`): Associated user ID.
- **`fail_type`** (`TEXT`): Classification of failure (e.g., policy violation).
- **`flagged_rules`** (`TEXT`): Specific guideline rules violated.
- **`notes`** (`TEXT`): Review audit explanation.
- **`draft_response`** (`TEXT`): Intercepted draft content.
- **`last_user_message`** (`TEXT`): The user message during the failure turn.
- **`created_at`** (`TIMESTAMP`): Creation timestamp.

---

## `purchases` Table
Tracks customer purchase intentions extracted during conversations.

- **`id`** (`INTEGER PRIMARY KEY AUTOINCREMENT`): Unique record ID.
- **`thread_id`** (`TEXT`): Conversation session/thread identifier.
- **`user_id`** (`TEXT`): Associated user ID.
- **`user_name`** (`TEXT`): Associated user display name.
- **`product`** (`TEXT`): Intended product or service name.
- **`urgency`** (`TEXT`): Urgency classification.
- **`amount`** (`REAL`): Estimated or stated transaction amount.
- **`user_quote`** (`TEXT`): Direct quote from the user indicating purchase intent.
- **`status`** (`TEXT`): Follow-up status (defaults to `待跟进`).
- **`created_at`** (`TIMESTAMP`): Creation timestamp.
