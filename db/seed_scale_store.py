import argparse
import json
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXPERT_TEMPLATE = """# 角色

你是心理量表测评专家顾问。你的职责是全面分析访客的最新提问和对话记录，将其与系统中 33 个标准的心理量表信息进行精准匹配评估。

# 心理量表库清单（33个量表完整元数据）：

{scales_json}

# 工作任务

1. **多维度匹配**：根据访客描述的群体（儿童、青少年、成年人、学生等）、年龄段、情绪/行为表现（如注意力缺陷、多动、抑郁、失眠、焦虑、职业倦怠、人格性格测试等）以及测评目的，在上述量表库中筛选所有高度吻合的量表。
2. **识别缺失关键信息**：要做出准确的量表推荐，通常需要明确访客的【测评对象年龄或身份群体】、【核心困扰或症状表现】、【困扰持续时间及对生活的影响】。如果访客描述模糊或缺失这些核心信息，务必提出追问要点，让对话助手询问访客以便尽快补齐。

# 输出格式

严禁输出任何额外文字、解释或 Markdown 代码块包裹，只允许严格输出一个 JSON 对象，结构必须如下：
{{
  "confidence": 1.0,
  "summary": "针对当前访客信息的量表推荐与追问策略",
  "recommended_scales": [
    {{
      "name": "量表完整名称",
      "match_reason": "具体匹配原因说明"
    }}
  ],
  "missing_info_questions": [
    "需追问访客受测者的具体年龄或所属群体",
    "需追问核心情绪困扰具体表现和持续时长"
  ],
  "key_points": [
    "初步推荐相符的测评量表",
    "引导访客补充核心缺失评估信息"
  ]
}}

注意：
- `confidence` 务必设为 1.0。
- `recommended_scales` 和 `missing_info_questions` 可同时存在；如无缺失信息则 `missing_info_questions` 留空列表 []；如暂无确定匹配量表则 `recommended_scales` 留空列表 []。
"""

def seed(db_filename: str = "scale_store.sqlite"):
    base_dir = Path(__file__).resolve().parent
    db_path = base_dir / db_filename
    logger.info(f"Seeding database at: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.text_factory = str
    cursor = conn.cursor()

    try:
        # Create tables
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

        # Clear existing prompts & experts in this new db if re-seeding
        cursor.execute("DELETE FROM prompts")
        cursor.execute("DELETE FROM experts")

        # Load prompts from db/scale_prompts folder
        prompts_dir = base_dir / "scale_prompts"
        if prompts_dir.exists():
            for prompt_file in prompts_dir.glob("*.md"):
                name = prompt_file.name
                content = prompt_file.read_text(encoding="utf-8")
                cursor.execute(
                    "INSERT INTO prompts (name, content) VALUES (?, ?)",
                    (name, content),
                )
            logger.info(f"Loaded prompts from {prompts_dir}")
        else:
            logger.warning(f"Prompts directory {prompts_dir} not found!")

        # Load scale cards JSON & create expert
        scales_file = base_dir.parent / "data" / "scale_cards.seed.json"
        if scales_file.exists():
            raw_scales = json.loads(scales_file.read_text(encoding="utf-8"))
            clean_scales = []
            for s in raw_scales:
                clean_item = {
                    "name": s.get("name"),
                    "aliases": s.get("aliases"),
                    "subject": s.get("subject"),
                    "age_range": s.get("age_range"),
                    "domains": s.get("domains"),
                    "phenomena": s.get("phenomena"),
                    "purpose": s.get("purpose")
                }
                if s.get("contraindications"):
                    clean_item["contraindications"] = s["contraindications"]
                clean_scales.append(clean_item)
            scales_json = json.dumps(clean_scales, ensure_ascii=False, indent=2)
            expert_prompt = EXPERT_TEMPLATE.format(scales_json=scales_json)
            cursor.execute(
                """
                INSERT INTO experts (name, description, load, prompt)
                VALUES (?, ?, 'always', ?)
                """,
                (
                    "scale_recommender",
                    "心理测评量表推荐与信息评估专家",
                    expert_prompt,
                ),
            )
            logger.info(f"Created always-on expert 'scale_recommender' with {len(clean_scales)} cleaned scale cards.")
        else:
            logger.error(f"Scale cards file not found at {scales_file}")

        # Seed default user u_001
        default_user_data = {
            "name": "默认访客",
            "用户类型": "通用心理测评用户",
            "说明": "本系统为心理测评量表智能推荐工具。统一为所有访客使用此默认配置。",
            "交互策略": "主动、友好地倾听访客心理诉求，收集年龄、群体及核心表现等信息，精准推荐匹配的心理量表。"
        }
        cursor.execute(
            """
            INSERT INTO users (id, data)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data=excluded.data
            """,
            ("u_001", json.dumps(default_user_data, ensure_ascii=False)),
        )
        logger.info("Seeded default user 'u_001'.")

        conn.commit()
        logger.info("Successfully seeded scale recommender database.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to seed scale store: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed scale recommender SQLite database.")
    parser.add_argument("--db", default="scale_store.sqlite", help="Target SQLite filename inside db/ folder.")
    args = parser.parse_args()
    seed(args.db)
