import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

async def get_all_users(db_path: str) -> dict[str, dict[str, Any]]:
    """Retrieve all users from the standalone users table."""
    query = """
    SELECT id, data FROM users
    """
    users = {}
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(query) as cursor:
                async for row in cursor:
                    key = row[0]
                    value_str = row[1]
                    try:
                        users[key] = json.loads(value_str)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse user data for {key}")
    except Exception as e:
        logger.error(f"Database error while getting all users: {e}")
        raise
    return users


async def get_user(db_path: str, user_id: str) -> dict[str, Any] | None:
    """Retrieve a single user by ID."""
    query = """
    SELECT data FROM users WHERE id = ?
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(query, (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse user data for {user_id}")
                        return None
    except Exception as e:
        logger.error(f"Database error while getting user {user_id}: {e}")
        raise
    return None


async def save_user(db_path: str, user_id: str, user_data: dict[str, Any]) -> None:
    """Save or update a user."""
    query = """
    INSERT INTO users (id, data, updated_at) 
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(id) DO UPDATE SET 
        data=excluded.data,
        updated_at=excluded.updated_at
    """
    try:
        value_str = json.dumps(user_data)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(query, (user_id, value_str))
            await db.commit()
    except Exception as e:
        logger.error(f"Database error while saving user {user_id}: {e}")
        raise


async def get_all_prompts(db_path: str) -> list[dict[str, str]]:
    """Retrieve all prompts."""
    query = """
    SELECT name, content FROM prompts
    """
    prompts = []
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(query) as cursor:
                async for row in cursor:
                    prompts.append({"name": row[0], "content": row[1]})
    except Exception as e:
        logger.error(f"Database error while getting all prompts: {e}")
        raise
    return prompts


async def save_prompt(db_path: str, name: str, content: str) -> None:
    """Save or update a prompt."""
    query = """
    INSERT INTO prompts (name, content, updated_at) 
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(name) DO UPDATE SET 
        content=excluded.content,
        updated_at=excluded.updated_at
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(query, (name, content))
            await db.commit()
    except Exception as e:
        logger.error(f"Database error while saving prompt {name}: {e}")
        raise


async def get_all_experts(db_path: str) -> list[dict[str, str]]:
    """Retrieve all experts."""
    query = """
    SELECT name, description, load, prompt FROM experts
    """
    experts = []
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(query) as cursor:
                async for row in cursor:
                    experts.append({
                        "name": row[0],
                        "description": row[1],
                        "load": row[2],
                        "prompt": row[3]
                    })
    except Exception as e:
        logger.error(f"Database error while getting all experts: {e}")
        raise
    return experts


async def get_expert(db_path: str, name: str) -> dict[str, str] | None:
    """Retrieve a single expert by name."""
    query = """
    SELECT name, description, load, prompt FROM experts WHERE name = ?
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(query, (name,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "name": row[0],
                        "description": row[1],
                        "load": row[2],
                        "prompt": row[3]
                    }
    except Exception as e:
        logger.error(f"Database error while getting expert {name}: {e}")
        raise
    return None


async def save_expert(db_path: str, name: str, description: str, load: str, prompt: str) -> None:
    """Save or update an expert."""
    query = """
    INSERT INTO experts (name, description, load, prompt, updated_at) 
    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(name) DO UPDATE SET 
        description=excluded.description,
        load=excluded.load,
        prompt=excluded.prompt,
        updated_at=excluded.updated_at
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(query, (name, description, load, prompt))
            await db.commit()
    except Exception as e:
        logger.error(f"Database error while saving expert {name}: {e}")
        raise


async def delete_expert(db_path: str, name: str) -> None:
    """Delete an expert."""
    query = "DELETE FROM experts WHERE name = ?"
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(query, (name,))
            await db.commit()
    except Exception as e:
        logger.error(f"Database error while deleting expert {name}: {e}")
        raise
