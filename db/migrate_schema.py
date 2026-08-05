import sys
import sqlite3
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    db_path = Path(__file__).parent / "store.sqlite"
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    # Force aiosqlite/sqlite3 to return TEXT columns as str, not bytes.
    # The legacy LangGraph store table kept 'value' as BLOB, so rows read
    # back as bytes objects even when the content is valid UTF-8 JSON.
    conn.text_factory = str
    cursor = conn.cursor()

    try:
        # Create new tables
        logger.info("Creating new tables...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                name TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experts (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                load TEXT NOT NULL DEFAULT 'optional' CHECK(load IN ('always', 'optional', 'never')),
                prompt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT,
                user_id TEXT,
                user_name TEXT,
                reason TEXT,
                flagged_rules TEXT,
                notes TEXT,
                draft_response TEXT,
                selected_experts TEXT,
                expert_advice TEXT,
                last_user_message TEXT,
                turn_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS failed_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT,
                user_id TEXT,
                fail_type TEXT,
                flagged_rules TEXT,
                notes TEXT,
                draft_response TEXT,
                last_user_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT,
                user_id TEXT,
                user_name TEXT,
                product TEXT,
                urgency TEXT,
                amount REAL,
                user_quote TEXT,
                status TEXT DEFAULT '待跟进',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migrate Users (if old store exists)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='store'")
        if cursor.fetchone():
            logger.info("Migrating users from legacy store...")
            cursor.execute("SELECT key, value FROM store WHERE prefix = 'users'")
            users = cursor.fetchall()
            for key, value in users:
                if isinstance(value, (bytes, bytearray)):
                    value = value.decode("utf-8")
                cursor.execute(
                    "INSERT INTO users (id, data) VALUES (?, CAST(? AS TEXT)) ON CONFLICT DO NOTHING",
                    (key, value)
                )
            logger.info(f"Migrated {len(users)} users from legacy store.")

            # Migrate Prompts from legacy store
            logger.info("Migrating prompts from legacy store...")
            cursor.execute("SELECT key, value FROM store WHERE prefix = 'prompts'")
            prompts = cursor.fetchall()
            for key, value in prompts:
                if isinstance(value, (bytes, bytearray)):
                    value = value.decode("utf-8")
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict) and "value" in parsed:
                        content = parsed["value"]
                    else:
                        content = value
                except json.JSONDecodeError:
                    content = value

                cursor.execute(
                    "INSERT INTO prompts (name, content) VALUES (?, CAST(? AS TEXT)) ON CONFLICT DO NOTHING",
                    (key, content)
                )
            logger.info(f"Migrated {len(prompts)} prompts from legacy store.")

            # Drop old tables
            logger.info("Dropping old store tables...")
            cursor.execute("DROP TABLE IF EXISTS store")
            cursor.execute("DROP TABLE IF EXISTS store_migrations")

        # Migrate experts from prompts table to experts table
        logger.info("Migrating expert prompts to experts table...")
        expert_mapping = {
            "medical_expert.system.md": {
                "name": "medical",
                "description": "医疗信息顾问 — 提供基于医学的背景信息，帮助客服代表给出安全、准确且谨慎的回复"
            },
            "sales_expert.system.md": {
                "name": "sales",
                "description": "销售顾问 — 提供基于商业的背景信息，帮助客服代表就产品、定价、账户变更等问题给出有帮助的回复"
            },
            "emotional_expert.system.md": {
                "name": "emotional",
                "description": "情感支持顾问 — 提供基于情感的背景信息，帮助客服代表以同理心、敏感度和恰当的语气做出回应"
            }
        }
        
        for old_name, expert_meta in expert_mapping.items():
            cursor.execute("SELECT content FROM prompts WHERE name = ?", (old_name,))
            row = cursor.fetchone()
            if row:
                content = row[0]
                cursor.execute(
                    "INSERT INTO experts (name, description, load, prompt) VALUES (?, ?, 'optional', ?) ON CONFLICT DO NOTHING",
                    (expert_meta["name"], expert_meta["description"], content)
                )
                cursor.execute("DELETE FROM prompts WHERE name = ?", (old_name,))
                logger.info(f"Migrated {old_name} to expert {expert_meta['name']}.")
        
        # Load default prompts from db/prompts folder
        prompts_dir = Path(__file__).parent / "prompts"
        overwrite = "--overwrite" in sys.argv
        if prompts_dir.exists():
            sql = (
                "INSERT INTO prompts (name, content) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET content=excluded.content"
                if overwrite
                else "INSERT INTO prompts (name, content) VALUES (?, ?) ON CONFLICT DO NOTHING"
            )
            for prompt_file in prompts_dir.glob("*.md"):
                prompt_name = prompt_file.name
                prompt_content = prompt_file.read_text(encoding="utf-8")
                cursor.execute(sql, (prompt_name, prompt_content))
            action = "Overwrote/seeded" if overwrite else "Seeded default"
            logger.info(f"{action} prompts from prompts folder.")

        conn.commit()
        logger.info("Migration completed successfully.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
