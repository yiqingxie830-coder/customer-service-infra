# 客服 Agent 项目全面报告

> 基于 `customer-service-infra` 代码库与 `销售Agent` 项目文档的综合分析
>
> 报告范围:架构设计、实现细节、运行机制、运维约束、演进路径

## 目录

1. [项目概述](#1-项目概述)
2. [产品定位与业务流程](#2-产品定位与业务流程)
3. [系统架构](#3-系统架构)
4. [核心设计决策](#4-核心设计决策)
5. [仓库与服务结构](#5-仓库与服务结构)
6. [LangGraph Agent 实现细节](#6-langgraph-agent-实现细节)
7. [状态模型与数据契约](#7-状态模型与数据契约)
8. [数据持久层(SQLite)](#8-数据持久层sqlite)
9. [飞书集成与事件日志](#9-飞书集成与事件日志)
10. [可观测性(Langfuse)](#10-可观测性langfuse)
11. [配置与运维](#11-配置与运维)
12. [失败模式与容错策略](#12-失败模式与容错策略)
13. [测试策略](#13-测试策略)
14. [部署现状](#14-部署现状)
15. [演进路线与遗留问题](#15-演进路线与遗留问题)
16. [总结](#16-总结)

---

## 1. 项目概述

`customer-service-infra` 是一套围绕 LangGraph 多智能体后端构建的客服基础设施,由三个独立但协同的服务组成,通过共享 SQLite 数据存储和 HTTP 契约联接。

### 1.1 项目身份

- **代码库**: 阿里云 Codeup,组织 `dongzhimen` / `CRM`,仓库 `customer-service-infra`
- **本地路径**: `/Users/ben/Developer/projects/customer-service-infra`
- **业务归属**: 东直门 / Builder_al / 骆保佳
- **当前状态**: v1 已部署到 ICCUBUNTU,全链路调通

### 1.2 服务清单

| 服务 | 角色 | 技术栈 |
|---|---|---|
| `customer-service-agent/` | 多智能体核心,LangGraph 流水线 | Python 3.12, LangGraph 1.2, langchain-openai 1.3, aiosqlite |
| `app-backend/` | 前后端翻译层,FastAPI 代理 | FastAPI, langgraph-sdk, Pydantic |
| `chat-board/` | 用户界面 | React + Vite + TypeScript, openapi-fetch |

三者通过 `db/store.sqlite` 共享业务数据(用户档案、prompt、专家定义、事件日志)。

### 1.3 设计哲学(贯穿全栈)

1. **每个 agent 都是独立可运行的 graph** — 任何专家、审核器都可以脱离主流水线在 Studio 中独立调试、独立评估、独立优化。
2. **配置即行为** — Prompt、专家名册、合规规则、模型参数都不在代码里。改 prompt = 改 SQLite 表 + 重启,无需 git commit。
3. **优雅降级** — 即使所有专家失效,流水线依然产出一条连贯的回复。审核失败则降级到静态兜底消息,绝不发出不合规内容。
4. **API 边界严格收窄** — 对外只暴露 `final_response`,所有中间状态(专家建议、草稿、审核裁决)留在 LangGraph 内部供调试与监控。

---

## 2. 产品定位与业务流程

### 2.1 业务场景

面向 SaaS 类客服场景,处理三类典型消息:

- **服务咨询** — 套餐、账单、退款、产品功能
- **健康相关** — 与产品挂钩的健康问题(谨慎、非处方表达)
- **情绪化沟通** — 抱怨、投诉、压力表达

系统需要同时具备**业务准确性**、**合规安全性**、**情感敏感度**,且不允许暴露任何内部决策过程。

### 2.2 单轮对话流程

```
   用户消息 + user_id
            │
            ▼
   ┌─────────────────────┐
   │  1. 加载用户档案     │  data_access.read_user(user_id)
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │  2. 路由选择专家     │  router LLM 调用,返回选中的专家列表
   └─────────┬───────────┘
             ▼ (按 selected_experts 并行 Send)
   ┌─────────────────────┐
   │  3. 并行咨询专家     │  expert_executor × N(LangGraph Send API)
   └─────────┬───────────┘
             ▼ 经 operator.add reducer 合并 expert_advice
   ┌─────────────────────┐
   │  4. 起草回复 +       │  synthesize 节点
   │     购买意向识别     │  purchase_classifier 节点(并行)
   └─────────┬───────────┘
             ▼ 草稿文本
   ┌─────────────────────┐
   │  5. 合规审核         │  review_agent,返回 pass / fail / escalate
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │  6. 下发或兜底       │  pass → 草稿原样下发
   │                     │  fail / escalate → 静态兜底消息
   └─────────────────────┘
```

每一阶段的副作用(失败原因、升级工单、购买意向)同时写入本地 SQLite 与飞书多维表格,供运营查阅。

### 2.3 对外契约

```jsonc
// 请求
{
  "messages": [{ "role": "user", "content": "..." }],
  "user_id": "u_001"
}

// 响应
{ "final_response": "..." }
```

`extra="forbid"` 拒绝任何额外字段;`user_id` 缺省时回落到 `configs/default.json -> defaults.user_id`。

---

## 3. 系统架构

### 3.1 三层服务拓扑

```
                ┌───────────────────────────┐
                │   chat-board (前端)        │
                │   React + Vite + TS       │
                │   通过 openapi-fetch 调用  │
                └────────────┬──────────────┘
                             │ POST /chat
                             ▼
                ┌───────────────────────────┐
                │   app-backend (FastAPI)   │
                │   /chat → 转发到 LangGraph │
                │   /users, /prompts,        │
                │   /experts → 直接读写 DB   │
                └──────┬───────────┬────────┘
                       │           │
            runs.wait()│           │ aiosqlite
                       ▼           ▼
                ┌──────────┐  ┌─────────────────┐
                │ LangGraph│  │ db/store.sqlite │
                │ Server   │◄─┤ users           │
                │ (agent)  │  │ prompts         │
                │  :2024   │  │ experts         │
                └──────────┘  │ escalations     │
                              │ failed_replies  │
                              │ purchases       │
                              └─────────────────┘
                                     ▲
                                     │ 同步写入
                                     │
                              ┌──────┴───────┐
                              │ 飞书多维表格  │
                              │ Bitable      │
                              └──────────────┘
```

### 3.2 关键解耦点

- **前端 ↔ 后端**: 通过 `openapi.json` 生成的 TypeScript 客户端,契约强类型,后端契约改了重跑 codegen 即可。
- **后端 ↔ Agent**: 通过 `langgraph_sdk.get_client(url=...)` 调用 LangGraph Server。app-backend 不持有任何 agent 业务逻辑,仅做参数转发与响应整形。
- **Agent ↔ 持久化**: SQLite 是事实标准。Prompt 通过 `db.get_prompt(name)` 在每次节点执行时按需读取(无模块级缓存),改完即热生效。
- **Agent ↔ 飞书**: 通过 `csa.feishu.log_event()` 异步非阻塞写入。token 自动缓存,失败不影响主流水线。

### 3.3 内部 Graph 拓扑(chat_agent)

```
START
  │
  ▼
entry         ── 解析 user_id,加载 user_data
  │
  ▼
router        ── LLM 选择需要咨询的专家
  │ Conditional Edge: fan_out_experts
  ├──Send(expert_executor, expert_name="sales")──┐
  ├──Send(expert_executor, expert_name="medical")┤  (并行)
  └──Send(expert_executor, expert_name="...")    ┘
                                                  │
                ┌─────────────────────────────────┘
                │ 经 operator.add 合并 expert_advice
                ▼
        ┌──synthesize───────┐
        │   起草回复         │
        └──┬────────────────┘
           │ (与 purchase_classifier 并行)
        ┌──┴────────────────┐
        │ purchase_classifier│
        │   识别购买意向     │
        │   写飞书 purchases │
        └──┬────────────────┘
           ▼
         review            ── 子图,review_agent.graph
           │
           ▼
         final             ── pass: 草稿;fail/escalate: 兜底
           │
           ▼
          END
```

**注意一个细节**: `purchase_classifier` 也作为 `synthesize` 的并行节点,二者都收敛到 `review`。这意味着每轮对话中,如果命中销售场景,购买意向识别与起草是同时进行的,不增加用户感知延迟。

### 3.4 `langgraph.json` 注册

```json
{
  "graphs": {
    "chat_agent": "./src/csa/agents/chat_agent.py:graph",
    "review_agent": "./src/csa/agents/review_agent.py:graph"
  }
}
```

**演进观察**: 早期版本注册了 5 个 graph(三个专家 + chat_agent + review_agent),v2 改造为动态专家路由后,专家不再是独立 graph,只剩 `chat_agent` 与 `review_agent` 作为可独立调试的 graph 入口。

---

## 4. 核心设计决策

项目文档(`销售Agent/Multiagent system/`)系统性比较了多种架构选择,这里把决策与代码现状串起来。

### 4.1 Pattern: Expert Subagent vs Direct Ingestion

文档 `Pattern choice.md` 比较了两种 Pattern:

| 维度 | Expert Subagent (分层) | Direct Ingestion (RAG 注入) |
|---|---|---|
| Context 优化 | ✅ Subagent 提炼后再回主 agent | ❌ 原始数据直入主 prompt |
| 延迟 | ❌ 多次 LLM 调用串行 | ✅ 单次 LLM 推理 |
| 跨域关联 | ❌ 信息有损 | ✅ 全局上下文 |
| 噪声过滤 | ✅ 显式过滤层 | ❌ 依赖检索质量 |

**项目选择**: Expert Subagent 模式 + 软路由(置信度)。理由:
- 客服场景需要**多维度三角化** — 一条"我的套餐太贵我压力好大"消息同时涉及销售、情绪、可能涉及健康(如焦虑相关),硬路由只挑一个专家会丢失信号。
- 专家可以**独立 dataset 评估** — 单独评估"医疗建议质量"无需运行整条流水线。
- 通过 `confidence` 软过滤(< 0.3 视为弱信号)实现"专家自觉退场",而不是预先决定哪个专家该说话。

### 4.2 Architecture: In-Process vs Distributed

文档 `Pattern choice.md` 也比较了 In-Process Object 与 Distributed Process:

**项目选择**: Local Subgraph Composition(in-process)。直接引用 LangGraph 官方警告:

> "Do not use RemoteGraph to call itself or another graph on the same deployment, as this can lead to deadlocks and resource exhaustion."

实现上 `chat_agent.build_graph()` 直接 `add_node("review", review_agent.graph)`,所有 graph 在同一个 Python 进程内通过 reducer 合并状态,零序列化开销。RemoteGraph 仅保留为未来跨进程隔离场景的备用选项(配置里的 `mode: "remote"` 占位,v1 未启用)。

### 4.3 Framework: LangGraph vs AutoGen vs OpenAI SDK

文档 `Framework choice.md` 进行了完整对比:

| 维度 | LangGraph | AutoGen | OpenAI Agents SDK |
|---|---|---|---|
| 心智模型 | 状态机/有向图 | 对话式/Actor 模型 | 轻量级 Handoff |
| 跨进程支持 | DB 同步 + REST | 原生 gRPC + CloudEvents | 仅客户端 + Cloud Threads |
| 持久化 | Checkpointer(SQLite/Postgres) | Session 快照 | OpenAI Thread |
| 时间旅行 | ✅ 原生 | ❌ | ❌ |

**项目选择**: LangGraph。决定性因素:
- 客服流水线要求**确定性的业务逻辑**(必须经过审核才能下发),状态机比涌现式对话更可控。
- 需要**模型无关性** — 通过 `ChatOpenAI(base_url=..., api_key=...)` 接入阿里云通义千问(`qwen3.5-plus`),不被 OpenAI / Azure 生态绑定。
- 内置 `Checkpointer` 支持线程持久化,多轮对话天然可用。

### 4.4 Review-as-Separate-Agent 的取舍

不让 synthesizer 一个 prompt 同时优化"有帮助 + 合规",而是拆成两次 LLM 调用:

| 维度 | 合并 prompt | 分离 review |
|---|---|---|
| 延迟 | 1× LLM | 2× LLM(+ 一倍) |
| 成本 | 1× tokens | ~1.5× tokens |
| 鲁棒性 | 易被越狱(单 prompt 同时优化两个相反目标) | 显著更稳健 |
| 可审计性 | 难以归因失败 | `review.notes` + `flagged_rules` 清晰可查 |

项目接受额外延迟与成本,换取**审核链路的可解释性**与**抗越狱能力**。Review agent 只看到草稿与对话,看不到专家建议,这是有意为之 — review 检查**输出**,不审视**推理过程**。

---

## 5. 仓库与服务结构

### 5.1 顶层布局

```
customer-service-infra/
├── customer-service-agent/    # LangGraph 多智能体后端(git submodule)
├── app-backend/               # FastAPI 翻译层
├── chat-board/                # 前端(git submodule)
├── db/
│   ├── store.sqlite           # 共享数据库(用户、prompt、专家、事件日志)
│   ├── migrate_schema.py      # schema 初始化与迁移脚本
│   └── prompts/               # 默认 prompt 种子文件(初始化时灌入 DB)
├── docs/
│   ├── architecture.md        # 服务级架构
│   └── database_schema.md     # DB 表结构说明
├── RUNNING.md                 # 全栈本地启动指南
├── CLAUDE.md                  # AI 协作规则
└── README.md
```

`customer-service-agent` 与 `chat-board` 是 git submodule,独立演进。这样 agent 仓库可单独被 LangGraph CLI 部署到 LangGraph Cloud,前端可单独被构建到 CDN,而 infra 仓库只追踪集成层与 DB schema。

### 5.2 customer-service-agent 内部结构

```
customer-service-agent/
├── pyproject.toml             # uv 管理,Python 3.12+
├── langgraph.json             # 注册 chat_agent 与 review_agent
├── .env.example               # OPENAI_BASE_URL, FEISHU_*, LANGFUSE_*
├── configs/
│   ├── default.json           # 默认配置(review/expert_call/logging)
│   ├── llm.json               # ChatOpenAI 参数(model, temperature 等)
│   └── feishu_tables.json     # 飞书多维表 schema 定义
├── guidelines/
│   └── response_guidelines.md # 12 条编号合规规则
├── src/csa/
│   ├── config.py              # 配置加载与校验
│   ├── llm.py                 # ChatOpenAI 工厂
│   ├── state.py               # TypedDict + Pydantic schema
│   ├── data_access.py         # read_user(user_id)
│   ├── prompts.py             # load_prompt / load_guidelines
│   ├── db.py                  # aiosqlite CRUD
│   ├── feishu.py              # 异步 Bitable 写入
│   ├── tracing.py             # Langfuse callback
│   ├── expert_registry.py     # ExpertDef + load_expert_registry
│   ├── logging_config.py      # 按 run_id 切分日志
│   ├── cli.py                 # 命令行入口(csa)
│   └── agents/
│       ├── chat_agent.py      # 主流水线 graph
│       ├── router.py          # 动态路由节点
│       ├── expert_executor.py # 通用专家执行器
│       └── review_agent.py    # 合规审核 graph
├── docs/
│   ├── architecture.md
│   ├── api.md
│   └── operations.{md,zh-CN.md}
└── tests/
    ├── test_chat_agent_pipeline.py
    ├── test_sales_expert.py / test_medical_expert.py / test_emotional_expert.py
    ├── test_feishu_integration.py
    └── test_tracing.py
```

注意:`tests/test_*_expert.py` 是 v2 改造前的遗留(对应被删除的独立专家模块),保留作为历史回归测试基线。

### 5.3 app-backend 结构

```
app-backend/
├── app_backend/
│   ├── main.py                # FastAPI app, /chat /users /prompts /experts
│   ├── config.py              # Settings(LANGGRAPH_BASE_URL 等)
│   └── database.py            # aiosqlite CRUD
├── scripts/health_check.py    # 端到端健康检查
└── README.md
```

后端职责被刻意收窄:
- `/chat` — 唯一调用 LangGraph 的端点,通过 `client.runs.wait()` 同步等待结果
- `/users`, `/prompts`, `/experts` — 直接读写 `db/store.sqlite`,不经过 LangGraph

这种分割让前端可以独立管理 CMS 类操作(改 prompt、维护用户、增删专家),不会因为 agent 进程重启而影响。

---

## 6. LangGraph Agent 实现细节

### 6.1 entry 节点

```python
async def entry(state: ChatState) -> dict:
    user_id = state.get("user_id") or get_config().defaults.user_id
    user_data = await read_user(user_id)
    return {"user_id": user_id, "user_data": user_data}
```

职责单一:落 `user_id` 缺省值,把用户档案塞进 state。整条流水线后续节点都能从 `state["user_data"]` 读出 persona、偏好、过往标签等,无需再次查库。

### 6.2 router 节点

```python
async def route(state: ChatState) -> dict:
    experts = await load_expert_registry()
    prompt = await load_prompt("router")
    llm = build_llm("router").with_structured_output(RouterDecision)
    decision = await llm.ainvoke([
        SystemMessage(prompt.format(experts=experts_summary)),
        *state["messages"],
    ])
    return {"router_decision": decision}
```

关键点:
- **结构化输出**: `with_structured_output(RouterDecision)` 让 LLM 直接产出 Pydantic 对象,失败时 LangChain 自动重试一次。
- **专家清单从 DB 动态拉取**: 加专家无需改代码,只需 `INSERT INTO experts ...` 然后写 prompt。
- **router 自身的 prompt 也在 DB**: 通过 `load_prompt("router")` 取出,可热更新。

`RouterDecision` schema(`state.py`):

```python
class RouterDecision(BaseModel):
    selected_experts: list[str]  # 专家 name 列表
    reasoning: str                # 思考过程(写入 trace)
```

### 6.3 fan_out_experts 条件边

```python
def fan_out_experts(state: ChatState):
    return [
        Send("expert_executor", {**state, "current_expert": name})
        for name in state["router_decision"].selected_experts
    ]
}
```

LangGraph 的 `Send` API 是这套系统并行能力的核心:它返回一个 Send 列表,运行时会**并发**调度每一个 `expert_executor`,每个节点收到带 `current_expert` 的私有 state 拷贝。

### 6.4 expert_executor 节点

```python
async def execute(state: dict) -> dict:
    expert_name = state["current_expert"]
    expert = await get_expert(expert_name)
    prompt = await load_prompt(f"expert.{expert_name}")
    llm = build_llm("expert").with_structured_output(ExpertAdvice)
    advice = await llm.ainvoke([
        SystemMessage(prompt.format(user=state["user_data"])),
        *state["messages"],
    ])
    return {"expert_advice": [advice]}  # 注意:列表
```

返回 `expert_advice: list[ExpertAdvice]` 是为了配合 `state.py` 里的 reducer:

```python
expert_advice: Annotated[list[ExpertAdvice], operator.add]
```

`operator.add` 把多个并行节点的列表 `+` 起来,形成所有专家建议的合集。这是 LangGraph 处理并行写入同一 key 的标准模式。

### 6.5 synthesize 节点

```python
async def synthesize(state: ChatState) -> dict:
    advices = [a for a in state["expert_advice"] if a.confidence >= 0.3]
    prompt = await load_prompt("chat_agent")
    guidelines = await load_guidelines()
    llm = build_llm("chat_agent")
    draft = await llm.ainvoke([
        SystemMessage(prompt.format(
            user=state["user_data"],
            guidelines=guidelines,
            expert_advice=advices,
        )),
        *state["messages"],
    ])
    return {"draft_response": draft.content}
```

软过滤在这里发生 — `confidence < 0.3` 的建议被丢弃,既避免噪声又给专家"自我退出"的能力。`guidelines` 在 synthesize 时注入而非 review 时,意图是让起草阶段就尽量合规,review 只兜底。

### 6.6 review 子图

`review_agent.graph` 作为 `chat_agent` 的子节点直接 `add_node("review", review_agent.graph)`,共享同一个 ChatState。

```python
class ReviewVerdict(BaseModel):
    verdict: Literal["pass", "fail", "escalate"]
    flagged_rules: list[str]  # 违反的规则编号,如 ["R3", "R7"]
    notes: str
```

三态返回值映射到三种处理路径:
- `pass` — 草稿原样下发
- `fail` — 走 fallback,记录 `failed_replies` 表
- `escalate` — 走 fallback + 写飞书 `升级工单`,标记升级原因

### 6.7 final 节点

```python
async def finalize(state: ChatState) -> dict:
    verdict = state["review_verdict"]
    if verdict.verdict == "pass":
        return {"final_response": state["draft_response"]}
    fallback = await load_prompt("fallback")
    if verdict.verdict == "escalate":
        await log_escalation(state, verdict)
    else:
        await log_failed_reply(state, verdict)
    return {"final_response": fallback}
```

兜底文案也存在 DB 的 `prompts` 表(name=`fallback`),可以按业务调性微调,无需改代码发版。

---

## 7. 状态模型与数据契约

### 7.1 ChatState

`state.py` 的核心 TypedDict:

```python
class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    user_data: dict
    router_decision: RouterDecision
    expert_advice: Annotated[list[ExpertAdvice], operator.add]
    draft_response: str
    purchase_intent: PurchaseIntent | None
    review_verdict: ReviewVerdict
    final_response: str
```

两个 reducer:
- `add_messages` — LangChain 标准 reducer,按 id 去重合并消息
- `operator.add` — 列表拼接,支撑专家并行扇出

### 7.2 ExpertAdvice schema

```python
class ExpertAdvice(BaseModel):
    expert_name: str
    advice: str              # 给 synthesizer 的建议文本
    confidence: float        # 0.0 - 1.0
    rationale: str           # 写入 trace,不进 synthesize
```

`rationale` 字段刻意从 synthesize prompt 中排除 — 防止专家的推理链路污染主回复风格,只暴露**结论**。

### 7.3 Pydantic forbid 配置

所有对外 schema 都使用 `model_config = ConfigDict(extra="forbid")`:

```python
class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[Message]
    user_id: str | None = None

class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    final_response: str
```

意图很明确:**对外契约最小化**,客户端拿不到 router_decision、expert_advice、review_verdict,审计与脱敏在服务端完成。所有内部状态通过 Langfuse trace 与飞书事件日志暴露,不进入客户端响应。

---

## 8. 数据持久层

### 8.1 表结构总览

`db/migrate_schema.py` 定义了 6 张核心表:

| 表 | 用途 | 关键字段 |
|---|---|---|
| `users` | 用户档案 | `user_id`, `persona`, `preferences (JSON)`, `tags (JSON)` |
| `prompts` | Prompt 仓库 | `name (UNIQUE)`, `content`, `version`, `updated_at` |
| `experts` | 专家注册表 | `name (UNIQUE)`, `display_name`, `description`, `enabled` |
| `escalations` | 升级工单 | `run_id`, `user_id`, `reason`, `original_message`, `flagged_rules` |
| `failed_replies` | 失败回复 | `run_id`, `draft`, `verdict`, `flagged_rules`, `notes` |
| `purchases` | 购买意向 | `run_id`, `user_id`, `intent`, `product_tags`, `confidence` |

### 8.2 Prompt 表 — 项目的运营杠杆

```sql
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

为什么把 prompt 入库而不是放代码?
- **运营友好**: 通过 `/prompts` API,运营可以在 chat-board 后台直接改文案,不需要 PR + 发版
- **版本可追溯**: `version` 字段单调递增,事后可回滚
- **A/B 实验铺垫**: 后续可扩展为 `prompts(name, variant, content)`,根据 user_id hash 分流

### 8.3 共享 DB 的并发安全

三个进程(LangGraph、app-backend、迁移脚本)共用 `db/store.sqlite`。SQLite 默认 WAL 模式 + `PRAGMA journal_mode=WAL` 已足够支撑当前并发(预期 < 10 QPS)。但这是项目演进的早期瓶颈点 — 当真实流量上来,需要切换到 Postgres,迁移路径在 §15 列出。

### 8.4 db.py 的访问模式

```python
async def get_prompt(name: str) -> str:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT content FROM prompts WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        return row[0] if row else ""
```

每次节点执行都打开新连接,不做模块级缓存。代价是每轮对话约 5~7 次 DB 读,带宽极低(prompt 文本几 KB),收益是**无状态、热更新、易测试**。

---

## 9. 飞书集成

### 9.1 配置驱动的字段映射

`configs/feishu_tables.json` 声明三张多维表的 schema:

```json
{
  "app_token": "${FEISHU_APP_TOKEN}",
  "tables": {
    "escalations": {
      "table_id": "tbl_xxx",
      "fields": {
        "run_id": "运行ID",
        "user_id": "用户ID",
        "reason": "升级原因",
        "original_message": "原始消息",
        "flagged_rules": "违反规则"
      }
    },
    "failed_replies": { ... },
    "purchases": { ... }
  }
}
```

代码侧字段名(snake_case)与飞书列名(中文)解耦,运营改列名不破坏代码,代码改字段名不破坏飞书工作流。

### 9.2 写入路径

`csa/feishu.py` 的核心:

```python
async def log_event(table: str, record: dict):
    token = await _get_tenant_token()  # 带 50min TTL 缓存
    mapped = _map_fields(table, record)
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                headers={"Authorization": f"Bearer {token}"},
                json={"fields": mapped},
            )
        except Exception as e:
            logger.warning("feishu_log_failed", table=table, error=str(e))
```

关键设计:
- **非阻塞**: 异常被吞掉只记日志,飞书故障不应阻塞客服响应
- **超时短**: 5 秒上限,避免飞书 API 慢响应拖垮流水线
- **token 缓存**: 减少 `tenant_access_token` 接口调用,降低被限流风险

### 9.3 升级工单的字段语义

`升级工单` 表的 `reason` 字段是单选枚举:
- 违反合规规则 — review verdict=`fail` 且 flagged_rules 非空
- 用户要求转人工 — review verdict=`escalate` 由 keyword 或 LLM 判定
- 涉及敏感话题 — 命中医疗/法律等强敏感主题
- 多次生成失败 — `max_review_retries` 用尽后兜底
- 其他

这套枚举是与业务方约定的,便于飞书侧建仪表盘按原因统计转人工率。

---

## 10. 可观测性 — Langfuse 集成

### 10.1 Trace 注入

`csa/tracing.py`:

```python
def get_langfuse_callback() -> CallbackHandler | None:
    if not (host := os.getenv("LANGFUSE_HOST")):
        return None
    return CallbackHandler(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=host,
    )
```

Callback 注入是 LangChain 标准模式:

```python
config = {"callbacks": [get_langfuse_callback()]} if cb else {}
await graph.ainvoke(state, config=config)
```

整条 graph 的每个节点、每次 LLM 调用、每个工具调用都自动出现在 Langfuse trace 树里,带耗时、token 用量、输入输出。

### 10.2 Trace 的运营价值

观察哪些可以从 trace 直接答出来:
- 哪些专家最常被路由命中?(router 节点的 `selected_experts` 分布)
- 平均每条对话调用了几个专家?(`expert_executor` 节点数)
- 哪些专家的 `confidence` 长期偏低?(可能 prompt 需要重写,或者该专家职能与场景错配)
- review 平均耗时多少?是否成为瓶颈?
- `fail` / `escalate` 的占比与原因分布?

### 10.3 Trace 之外的事件日志

Langfuse 主要看**单次会话的细节**,飞书表则负责**业务侧的聚合分析**。两者互补 — Langfuse 给工程师调试用,飞书给运营/产品看趋势用。

---

## 11. 配置与运维

### 11.1 三件套配置

| 文件 | 作用 | 热更新? |
|---|---|---|
| `configs/default.json` | 业务参数(review/expert/兜底/默认值) | 重启生效 |
| `configs/llm.json` | LLM 客户端参数(model/temperature/base_url) | 重启生效 |
| `configs/feishu_tables.json` | 飞书表 schema 映射 | 重启生效 |

`default.json` 关键字段:

```json
{
  "defaults": { "user_id": "u_001" },
  "review": {
    "max_review_retries": 0,
    "escalate_on_fail": true
  },
  "expert_call": {
    "min_confidence": 0.3,
    "timeout_seconds": 30
  }
}
```

注意 `max_review_retries: 0` — 当前版本审核失败**不重试**,直接走 fallback。这是 v1 的保守选择,避免重试链路放大 LLM 故障。

### 11.2 环境变量

`.env.example` 声明的必需变量:

```
# LLM(阿里云 DashScope 兼容模式)
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=sk-xxx

# 飞书
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_APP_TOKEN=xxx  # bitable app token

# Langfuse(可选,空则跳过 trace)
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
```

设计上,**只有 LLM 凭据是硬性必需**,其余服务降级为可选。飞书 token 缺失只是日志不上报,Langfuse 缺失只是没有 trace,服务仍能跑。

### 11.3 日志策略

`logging_config.py` 按 `run_id` 切分日志文件:

```python
logger = structlog.get_logger().bind(run_id=run_id)
```

每次 graph 启动绑定一个 run_id(由 LangGraph 注入),整条流水线的日志都带这个 id。出问题时通过 run_id 即可关联 LangFuse trace + 飞书事件 + 本地日志,形成完整链路。

### 11.4 启动命令

`RUNNING.md` 总结的本地启动顺序:

```bash
# 1. 初始化 DB(只需一次)
cd db && uv run python migrate_schema.py

# 2. 启动 LangGraph Server
cd customer-service-agent
uv run langgraph dev --port 2024

# 3. 启动 app-backend
cd app-backend
uv run uvicorn app_backend.main:app --port 8000 --reload

# 4. 启动前端
cd chat-board
pnpm dev
```

健康检查脚本:

```bash
uv run python app-backend/scripts/health_check.py
```

会依次验证:DB 可读、LangGraph Server 200、端到端 `/chat` 调用返回 final_response。

---

## 12. 失败模式与容错

### 12.1 失败矩阵

| 失败点 | 检测方式 | 处理 |
|---|---|---|
| LLM API 超时 | httpx 超时 30s | LangChain 自动重试 1 次,仍失败抛异常 |
| 结构化输出解析失败 | Pydantic ValidationError | LangChain 内部重试 |
| 专家执行异常 | Send 节点 try/except | 该专家建议缺失,其他专家正常合并 |
| review 解析失败 | ValidationError | 当作 `fail` 处理,走 fallback |
| 飞书 API 失败 | httpx 异常 | 吞异常 + warn 日志,不阻塞 |
| DB 锁冲突 | aiosqlite OperationalError | 不重试,抛给上游 |
| Langfuse 不可达 | callback 内部静默 | 不影响主流程 |

### 12.2 三种失败语义的区分

代码里有意区分:
- **应该重试** — LLM 临时故障(LangChain 自动处理)
- **应该兜底** — review verdict=fail(直接 fallback,记 failed_replies)
- **应该升级** — review verdict=escalate(fallback + 写飞书升级工单)

这三类对应用户的不同感知:
- 重试:对用户透明,只是延迟略增
- 兜底:用户看到通用安抚文案,事件入库供事后回放
- 升级:用户看到引导转人工的话术,飞书工单触发人工接管

### 12.3 fallback 文案

存在 DB `prompts` 表的 `fallback` 记录中,典型内容(项目可改):

> "非常抱歉,刚才我没有完全理解您的问题。如果您方便的话,可以再描述得更具体一些吗?或者您可以直接联系我们的人工客服 [转人工]。"

文案设计兼顾:
- 不暴露技术故障细节
- 给用户一个继续对话的台阶
- 提供升级到人工的明确出口

### 12.4 v1 已知缺口

- `max_review_retries: 0` — 没有重试,LLM 一次抖动直接兜底,体验偏保守
- 专家超时机制依赖 LangGraph 默认超时,未在 expert_executor 内显式 `asyncio.wait_for`
- 飞书写入失败只记日志,无补偿队列(故障期数据丢失)
- 无熔断机制 — 上游 LLM 持续慢响应时无法快速失败

这些都列入 §15 演进路线。

---

## 13. 测试策略

### 13.1 测试金字塔

| 层级 | 文件 | 关注点 |
|---|---|---|
| 单元 | `test_state.py`, `test_db.py` | Pydantic schema、reducer、DB CRUD |
| 节点 | `test_router.py`, `test_review_agent.py` | 单节点输入输出 |
| 集成 | `test_chat_agent_pipeline.py` | 整条 graph 端到端 |
| 外部 | `test_feishu_integration.py`, `test_tracing.py` | 第三方集成,mock 或 skip |

### 13.2 节点级隔离测试

`langgraph.json` 注册 `review_agent` 为独立 graph 的另一个好处:可以单独喂 review dataset 评估,不必跑完整流水线。

```python
async def test_review_pass_safe_response():
    state = {
        "messages": [HumanMessage("怎么退货?")],
        "draft_response": "您好,请提供订单号,我帮您查询退货流程。",
    }
    result = await review_agent.graph.ainvoke(state)
    assert result["review_verdict"].verdict == "pass"
```

### 13.3 Mock 策略

- **LLM 调用**: 通过 `monkeypatch` 替换 `build_llm` 工厂,返回固定响应
- **DB**: 用 in-memory SQLite(`:memory:`)+ 每个测试 fixture 重建 schema
- **飞书**: 用 `respx` mock httpx 请求,断言请求 payload
- **Langfuse**: 测试环境不设 `LANGFUSE_HOST`,callback 自动跳过

### 13.4 v1 测试覆盖盲区

- 并行专家扇出的竞态(多专家同时返回,reducer 顺序)未覆盖
- `Send` API 在测试环境与生产环境行为差异未验证
- 飞书 token 过期场景未模拟
- 长对话(>20 轮)的 state 增长未做压测

---

## 14. 部署现状

### 14.1 部署目标:ICCUBUNTU

文档 `ICCUBUNTU部署/implementation_plan.md` 是部署手册,v1 已经完成全链路验证。

### 14.2 拓扑

```
ICCUBUNTU 服务器
├── systemd: customer-service-langgraph (端口 2024)
├── systemd: customer-service-backend (端口 8000)
├── nginx: 反向代理 + 静态资源
│   ├── /api/   → :8000
│   └── /       → /var/www/chat-board/dist
└── /var/lib/customer-service/store.sqlite
```

### 14.3 部署步骤(摘要)

1. 安装 `uv`、Python 3.12、Node 20、pnpm、nginx
2. 拉代码到 `/opt/customer-service-infra` 并 `git submodule update --init`
3. 初始化 DB 到固定路径,迁移脚本灌入种子 prompt
4. `uv sync` 安装两个 Python 服务依赖
5. 写两个 systemd unit 文件,启动 + 设置 `WantedBy=multi-user.target`
6. 前端 `pnpm build`,产物拷到 nginx web 根
7. nginx 配置 `/api/` 反代 + `try_files $uri /index.html` 支持 SPA
8. 配 `.env` + Langfuse + 飞书凭据

### 14.4 升级流程

```bash
cd /opt/customer-service-infra
git pull && git submodule update --remote
uv sync --upgrade
sudo systemctl restart customer-service-langgraph
sudo systemctl restart customer-service-backend
cd chat-board && pnpm install && pnpm build
sudo cp -r dist/* /var/www/chat-board/
```

零停机要求未上日程,v1 接受秒级中断。

---

## 15. 演进路线与遗留问题

### 15.1 短期(v1.1,1-2 周)

- **审核重试**: `max_review_retries: 1`,允许一次 LLM 抖动后重试
- **专家超时显式化**: 在 `expert_executor` 内用 `asyncio.wait_for`,超时返回低 confidence advice
- **飞书写入补偿**: 失败入本地队列(SQLite 表),后台 worker 定时重试
- **purchase_intent 真实落库**: 当前 v1 已写飞书,但 SQLite 的 `purchases` 表写入路径尚未串通,需要补一次 commit

### 15.2 中期(v1.5,1-2 月)

- **专家热插拔**: 不重启 LangGraph Server 加新专家(目前需重启)
- **Prompt A/B**: 同名 prompt 支持多变体,按 user_id hash 分流
- **多模型路由**: router 选择不同专家时用不同模型(快模型路由 + 强模型起草)
- **会话长期记忆**: 利用 LangGraph Checkpointer 跨会话维护用户偏好

### 15.3 长期(v2.0,3-6 月)

- **DB 迁移到 Postgres**: SQLite 在 > 50 QPS 下出现写锁瓶颈
- **LangGraph Cloud**: 把 agent 推到托管平台,本地只留 app-backend
- **真正的人工 takeover**: 飞书工单触发 → 客服坐席接管同一对话 thread
- **细粒度授权**: 不同用户的 prompt/expert 可见性分级(B2B 多租户场景)

### 15.4 遗留问题清单

- `feishu_tables.json` 中 table_id 是硬编码,不利于多环境(dev/staging/prod)切换
- `RemoteGraph` 配置在 default.json 占位但未启用,代码路径未验证
- v1 文档双语版本(`operations.md` 与 `operations.zh-CN.md`)存在内容轻微漂移
- `test_*_expert.py` 是 v1 改造前的遗留,删除还是迁移到新结构未决
- chat-board 的 `openapi-fetch` 客户端需要后端 schema 改动后手动重新生成

---

## 16. 总结

`customer-service-infra` 是一个**为业务正确性而设计**的多智能体客服系统,而不是技术炫技。几个关键的设计取舍清晰可辨:

**第一**,选择 LangGraph 而非更"对话式"的 AutoGen,因为客服流水线需要**确定性的业务逻辑**(必须经过审核才能下发回复)。状态机的可控性比涌现式对话更适合这种场景。

**第二**,选择 Expert Subagent + 软路由(confidence)而非硬路由或 RAG 直接注入,因为客服消息往往**多维度耦合**(销售+情绪+健康),硬路由会丢失信号,RAG 会污染主回复。

**第三**,选择 Review 独立子图而非合并到 synthesizer prompt,接受 2× LLM 延迟与 ~1.5× 成本,换取**抗越狱能力**与**审计可解释性**。

**第四**,选择把 prompt 入库而非放代码,把字段映射放配置而非硬编码,目的是让**运营成为一等公民** — 改文案、改字段、加专家都不需要 PR + 发版。

**第五**,选择 in-process subgraph composition 而非 RemoteGraph,遵循 LangGraph 官方"不要在同一 deployment 内 RemoteGraph 调用自己"的警告,零序列化开销。

代码体量不大(核心 agent < 2000 行 Python),但每一行的取舍都能在 Obsidian 文档里追溯到设计原因,这是这个项目最值得学习的地方 — **决策链路完整**,而不是"先写后说"。

v1 已经在 ICCUBUNTU 完成全链路部署验证,具备生产可用性。短期补齐审核重试、专家超时、飞书补偿等容错缺口后,可以承接真实流量。长期演进路线明确:DB 升级到 Postgres、agent 推到 LangGraph Cloud、引入真正的人工 takeover,实现"AI 优先 + 人工兜底"的完整客服闭环。

