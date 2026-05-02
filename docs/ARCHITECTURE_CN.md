# MARS 架构

## 1. 系统定位

MARS 是一个独立的代理式记忆引擎 (Agentic Memory Engine)。

它不是：

- 一个飞书聊天搜索工具
- 一个简单的 RAG 系统
- 一个 OpenClaw 内部的记忆文件夹
- 一个纯粹的提示词工程工作流

它是：

- 一个外部的记忆基础设施
- 一个有状态的记忆治理系统
- 一个与代理无关 (Agent-agnostic) 的服务，可以被 OpenClaw、飞书机器人 (Feishu Bot)、CLI 或其他代理调用

``` text
Feishu = 数据源和交互界面
OpenClaw = 代理入口和工具调用方
MARS = 记忆管理引擎
```


## 2. 高层数据流

```text
Feishu 聊天 / 文档 / 会议 / 本地示例 JSON
        ↓
Connectors (连接器) / Adapters (适配器)
        ↓
RawEvent
        ↓
Raw Ledger (原始账本)
        ↓
Window Builder (窗口构建器)
        ↓
Memory Extraction (记忆提取)
        ↓
MemoryObject
        ↓
Views (视图): SQLite / 关键字索引 / 向量索引 / Markdown / 多维表格 (Bitable)
        ↓
Retrieval (检索) / Reconciliation (协调) / Summoning (召唤) / Benchmark (基准测试)
```


## 3. 核心层

### 3.1 接口层 (Interface Layer)

负责将外部数据转换为内部的 `RawEvent` 模式。

适配器：

```text
sample_loader.py
cli_adapter.py
openclaw_adapter.py
feishu_event_adapter.py
```


MVP 仅需要：

```text
sample_loader.py
cli_adapter.py
```


后续阶段添加：

```text
openclaw_adapter.py
feishu_event_adapter.py
```


### 3.2 原始账本层 (Raw Ledger Layer)

原始账本是唯一的事实来源 (source of truth)。

原则：

- 仅追加 (append-only)
- 可审计 (auditable)
- 可重放 (replayable)
- 保留溯源 (provenance-preserving)
- 双时态 (bitemporal)
- 在 MVP 中不进行物理删除

### 3.3 记忆提取层 (Memory Extraction Layer)

将讨论窗口转化为结构化的记忆对象。

LLM 用于：

- 候选记忆提取
- 记忆标准化
- 冲突关系判断
- 推送卡片生成
- 入职资料包生成

代码用于：

- 事件摄入
- 持久化
- 状态流转
- 版本控制
- 检索
- 基准测试
- 溯源追踪

### 3.4 视图层 (View Layer)

派生视图是由原始账本和记忆对象生成的。

MVP 视图：

```text
SQLite memory_objects
关键字搜索
Markdown 导出（可选）
```


后续视图：

```text
向量索引
飞书多维表格 (Feishu Bitable)
时间线视图
版本链视图
```


### 3.5 检索层 (Retrieval Layer)

MVP 检索：

```text
关键字搜索 + project 过滤器 + status 过滤器
```


后续检索：

```text
混合检索 = 关键字 + 向量 + status + 时间 + 重排 (rerank)
```


### 3.6 策略层 (Policy Layer)

控制何时读取、写入、更新、遗忘和推送。

MVP 使用基于规则的策略加上 LLM 的语义判断。

MVP 中没有强化学习 (RL) 控制器。

### 3.7 协调层 (Reconciliation Layer)

处理语义记忆的版本治理。

关系：

```text
duplicate (重复)
support (支持)
update (更新)
conflict (冲突)
supersede (覆盖/取代)
unrelated (无关)
```


如果关系是 `supersede`：

```text
old_memory.status = superseded
new_memory.status = active
写入 memory_edges
写入 policy_actions
```


### 3.8 召唤层 (Summoning Layer)

MVP 仅模拟主动推送。

后续支持：

```text
历史决策提醒
遗忘提醒
冲突审查提醒
新人入职记忆包
```


## 4. 类 Git 的记忆治理

MARS 借鉴了类似 Git 的版本治理理念，但管理的是语义记忆对象而非文本文件。

| Git 概念 | MARS 概念 |
| ----------- | ---------------------------------- |
| commit      | raw_event / policy_action          |
| diff        | 语义记忆差异 (semantic memory diff) |
| merge       | 记忆合并 (memory merge)             |
| conflict    | 冲突的记忆 (conflicted memory)      |
| revert      | 纠正 / 覆盖事件 (correction / supersede event) |
| blame       | 溯源追踪 (provenance trace)         |
| log         | 记忆时间线 (memory timeline)        |
| branch      | 项目 / 阶段 / 备选方案 (project / phase / alternative plan) |


重要提示：

```text
MARS 的 diff 不是文本 diff。它是语义记忆 diff。
```


## 5. 内部数据模式 (Internal Data Schema)

### 5.1 RawEvent

```json
{  
  "event_id": "evt_001",  
  "event_type": "message.created",  
  "source_type": "sample_chat",  
  "source_id": "msg_001",  
  "tenant_id": "tenant_demo",  
  "project_id": "carbon_platform",  
  "chat_id": "chat_001",  
  "thread_id": null,  
  "actor_id": "user_001",  
  "actor_name": "张三",  
  "content": "一期先用 Streamlit 吧",  
  "content_type": "text",  
  "mentions": [],  
  "reply_to": null,  
  "raw_payload": {},  
  "transaction_time": "2026-05-01T10:00:00",  
  "valid_time_start": "2026-05-01T10:00:00",  
  "valid_time_end": null,  
  "source_url": null
}
```

### 5.2 MemoryObject

```json
{  
  "memory_id": "mem_001",  
  "memory_type": "decision",  
  "scope": "project",  
  "tenant_id": "tenant_demo",  
  "project_id": "carbon_platform",  
  "user_id": null,  
  "topic": "技术路线",  
  "title": "一期 Demo 采用 Streamlit",  
  "content": "一期 Demo 先采用 Streamlit，正式版再考虑 Vue + FastAPI。",  
  "rationale": ["比赛周期短", "已有 Python 数据处理代码"],  
  "objections": ["Streamlit 工程化程度弱于 Vue + FastAPI"],  
  "status": "active",  
  "version": 1,  
  "confidence": 0.86,  
  "importance": 4,  
  "valid_time_start": "2026-05-01T10:00:00",  
  "valid_time_end": null,  
  "transaction_time": "2026-05-01T10:30:00",  
  "source_event_ids": ["evt_001", "evt_002"],  
  "supersedes": null,  
  "superseded_by": null
}
```

### 5.3 MemoryEdge

```json
{
  "edge_id": "edge_001",
  "source_memory_id": "mem_002",
  "target_memory_id": "mem_001",
  "relation_type": "supersedes",
  "reason": "新消息明确表示“不对，一期改为 Vue + FastAPI”，覆盖旧技术路线。",
  "confidence": 0.91
}
```

### 5.4 PolicyAction

```json
{
  "action_id": "act_001",
  "action_type": "UPDATE",
  "project_id": "carbon_platform",
  "decision": "SUPERSEDE",
  "reason": "同项目同主题且存在明确覆盖语义",
  "confidence": 0.91
}
```

## 6. 数据库架构 (Database Schema)

### 6.1 raw_events

```sqlite
CREATE TABLE IF NOT EXISTS raw_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    tenant_id TEXT,
    project_id TEXT,
    chat_id TEXT,
    thread_id TEXT,
    actor_id TEXT,
    actor_name TEXT,
    content TEXT,
    content_type TEXT,
    mentions_json TEXT,
    reply_to TEXT,
    raw_payload_json TEXT,
    transaction_time TEXT,
    valid_time_start TEXT,
    valid_time_end TEXT,
    source_url TEXT,
    created_at TEXT
);
```

### 6.2 memory_objects

```sqlite
CREATE TABLE IF NOT EXISTS memory_objects (
    memory_id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    tenant_id TEXT,
    project_id TEXT,
    user_id TEXT,
    topic TEXT,
    title TEXT,
    content TEXT,
    rationale_json TEXT,
    objections_json TEXT,
    tags_json TEXT,
    status TEXT,
    version INTEGER,
    confidence REAL,
    importance INTEGER,
    valid_time_start TEXT,
    valid_time_end TEXT,
    transaction_time TEXT,
    supersedes TEXT,
    superseded_by TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

### 6.3 memory_sources

```sqlite
CREATE TABLE IF NOT EXISTS memory_sources (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    evidence_type TEXT,
    quote TEXT,
    source_url TEXT,
    created_at TEXT
);
```

### 6.4 memory_edges

```sqlite
CREATE TABLE IF NOT EXISTS memory_edges (
    edge_id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    reason TEXT,
    confidence REAL,
    created_at TEXT
);
```

### 6.5 policy_actions

```sqlite
CREATE TABLE IF NOT EXISTS policy_actions (
    action_id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    project_id TEXT,
    input_json TEXT,
    candidate_json TEXT,
    decision TEXT,
    reason TEXT,
    confidence REAL,
    created_at TEXT
);
```

### 6.6 retrieval_logs

```sqlite
CREATE TABLE IF NOT EXISTS retrieval_logs (
    log_id TEXT PRIMARY KEY,
    query TEXT,
    project_id TEXT,
    time_scope TEXT,
    retrieved_memory_ids_json TEXT,
    selected_memory_ids_json TEXT,
    latency_ms INTEGER,
    created_at TEXT
);
```

### 6.7 benchmark_results

```sqlite
CREATE TABLE IF NOT EXISTS benchmark_results (
    result_id TEXT PRIMARY KEY,
    benchmark_type TEXT,
    case_id TEXT,
    metric_json TEXT,
    passed INTEGER,
    created_at TEXT
);
```

## 7. 记忆状态机 (Memory Status Machine)

有效状态：

```text
pending (待处理)
active (活跃)
superseded (已覆盖/被取代)
expired (已过期)
archived (已归档)
conflicted (冲突)
rejected (已拒绝)
```


规则：

```text
pending -> active
pending -> rejected
active -> superseded
active -> expired
active -> archived
active -> conflicted
conflicted -> active
conflicted -> superseded
conflicted -> rejected
```


MVP 必须实现：

```text
pending
active
superseded
conflicted
rejected
```


## 8. MVP API 路由

### POST /api/ingest/messages

摄入示例消息或标准化消息。

### POST /api/memory/extract

根据事件 ID 提取 `MemoryObject`。

### POST /api/memory/search

通过查询语句搜索记忆。

### POST /api/memory/reconcile

针对现有记忆创建或协调新记忆。

### POST /api/benchmark/run

运行基准测试。

## 9. 文件结构

```text
mars-memory-engine/
├── app/
│   ├── api/
│   ├── connectors/
│   ├── core/
│   ├── llm/
│   └── storage/
├── data/
│   ├── sample_chats/
│   └── benchmark/
├── scripts/
├── memory_store/
├── reports/
├── docs/
├── README.md
├── ARCHITECTURE.md
├── IMPLEMENTATION_PLAN.md
├── AGENTS.md
└── requirements.txt
```


## 10. MVP 的非目标 (Non-goals for MVP)

MVP 不会实现：

- 真实的飞书事件订阅
- 真实的 OpenClaw 运行时集成
- 飞书多维表格 (Feishu Bitable) 同步
- 生产环境级别的权限系统
- 向量重排器 (Vector reranker)
- 时态知识图谱 (TKG)
- 强化学习 (RL) 控制器
- 隐式记忆标记 (latent memory token)
- 逻辑调制 (logit modulation)
- 多模态记忆 (multimodal memory)