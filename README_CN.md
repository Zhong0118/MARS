# MARS: 协调与召唤记忆代理 (Memory Agent for Reconciliation and Summoning)

MARS 是一个用于企业协作记忆的代理式记忆引擎 (Agentic Memory Engine)。

它旨在将来自飞书聊天、笔记、会议讨论和代理输入的碎片化项目历史，转化为结构化、可治理的记忆：决策、事实、程序、风险、偏好和入职背景信息。

MARS 不是：
- 一个简单的聊天搜索工具
- 一个普通的 RAG 流水线
- 一个内部的 OpenClaw 记忆文件夹

MARS 是：
- 一个独立的记忆管理引擎
- 一个具有溯源意识的原始账本 (raw ledger) 加记忆对象系统
- 一个稍后可以被 OpenClaw、飞书机器人、CLI 工具或其他代理调用的服务

## 项目状态

该代码库目前处于本地 MVP (最小可行性产品) 模式。

目前已完成：
- 阶段 0：项目脚手架
- 阶段 1：核心 Pydantic 模型和 SQLite 存储

目前正在进行：
- SQLite 数据库初始化
- 将本地示例聊天摄入 `raw_events`
- 带有 `/health` 的 FastAPI 应用程序骨架

尚未实现：
- 真实的记忆提取
- 关键字检索
- 协调和覆盖 (supersede) 流程
- 基准测试执行
- 真实的飞书或 OpenClaw 集成

## 核心理念

MARS 是围绕以下结构构建的：

```text
Raw Ledger + Derived Views + Policy + Reconciliation + Summoning
```

含义：
- `Raw Ledger` (原始账本)：具有溯源信息的仅追加源事件
- `Derived Views` (派生视图)：结构化的记忆对象以及后续的检索/导出视图
- `Policy` (策略)：何时读取、写入、更新和推送记忆的规则
- `Reconciliation` (协调)：处理重复、冲突、更新和覆盖的逻辑
- `Summoning` (召唤)：主动召回相关的历史决策

MVP 遵循一个严格的原则：

```text
首先构建本地版本。
在本地 MVP 跑通之前，不要实现真实的飞书/OpenClaw 集成。
```

## MVP 范围

本地 MVP 旨在逐步验证以下能力：

1. 加载示例聊天 JSON。
2. 将每条外部消息转换为 `RawEvent`。
3. 在 SQLite 中存储原始事件。
4. 使用 `MockLLM` 提取结构化的 `MemoryObject` 记录。
5. 本地搜索记忆。
6. 处理带有覆盖 (supersede) 关系的冲突更新。
7. 运行基准测试脚本并编写报告。
8. 通过 FastAPI 暴露本地 HTTP API。

在当前阶段，仅实现了这些流程的基础工作。

## 当前架构

高层流程：

```text
示例 JSON / CLI / 未来的适配器
        ->
connectors
        ->
RawEvent
        ->
SQLite 原始账本 (raw ledger)
        ->
未来的提取 / 检索 / 协调
```

关键架构规则：
- 所有外部数据必须首先成为 `RawEvent`
- 外部数据载荷格式必须保留在 connectors/adapters 内部
- 不进行记忆的物理删除
- 每个 `MemoryObject` 必须通过 `source_event_ids` 保持溯源
- 代码处理治理和状态变更；LLM 处理语义

## 代码库结构

```text
app/
  api/          HTTP 路由模块
  connectors/   外部输入适配器 -> RawEvent
  core/         提取、检索、协调、策略
  llm/          MockLLM 和未来的供应商集成
  storage/      Pydantic 模型和 SQLite 辅助工具
data/
  sample_chats/ 示例讨论输入
  benchmark/    基准测试用例定义
scripts/        本地 CLI 入口
memory_store/   生成的 SQLite 数据库
reports/        生成的基准测试/报告输出
docs/           架构、提案、计划、项目结构
```

有关每个文件夹和文件的更完整解释，请参见：

- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## 已实现的文件

已就位的重要文件：
- `app/main.py`: 带有 `/health` 的 FastAPI 应用程序入口
- `app/connectors/sample_loader.py`: 示例 JSON -> `RawEvent`
- `app/storage/models.py`: 核心内部 Pydantic 模型
- `app/storage/db.py`: SQLite 架构和持久化辅助工具
- `scripts/init_db.py`: 创建本地数据库和数据表
- `scripts/run_extract.py`: 将示例聊天摄入 `raw_events`
- `scripts/search_memory.py`: 用于未来检索的占位符 CLI
- `scripts/run_benchmark.py`: 用于未来基准测试流程的占位符 CLI

## 依赖要求

推荐环境：
- Python 3.11+ 或 3.12
- 一个专用的 conda 环境，或者一个现有的环境（如 `dl`）

安装依赖项：

```powershell
pip install -r requirements.txt
```

如果你使用 conda：

```powershell
conda run -n dl python -m pip install -r requirements.txt
```

当前依赖项：
- `fastapi`
- `pydantic`
- `uvicorn`

## 快速开始

### 1. 初始化数据库

```powershell
python scripts/init_db.py
```

预期结果：
- 创建 `memory_store/mars.db`
- 创建所有必需的 MVP 数据表

### 2. 将示例聊天 JSON 摄入 raw_events

```powershell
python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json --ingest-only
```

预期结果：
- 读取示例文件
- 将每条消息转换为 `RawEvent`
- 将这些数据行插入 SQLite

### 3. 验证导入

```powershell
python -c "from app.storage.models import RawEvent, MemoryObject"
```

### 4. 运行 FastAPI 应用程序

```powershell
uvicorn app.main:app --reload --port 8000
```

然后打开：

```text
http://127.0.0.1:8000/health
```

预期响应：

```json
{"status":"ok"}
```

## 当前命令

这些命令已在项目工作流中定义：

```powershell
python scripts/init_db.py

python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json --ingest-only

python scripts/search_memory.py "why did we avoid Vue earlier?" --project-id carbon_platform

python scripts/run_benchmark.py

uvicorn app.main:app --reload --port 8000
```

注意事项：
- `search_memory.py` 在阶段 0/1 中仍是占位符
- `run_benchmark.py` 在阶段 0/1 中仍是占位符
- 完整的提取逻辑将在后续阶段实现

## 数据模型快照

核心内部模型：
- `RawEvent`
- `MemoryObject`
- `MemoryEdge`
- `MemorySource`
- `PolicyAction`
- `EvidencePack`

当前 SQLite 数据表：
- `raw_events`
- `memory_objects`
- `memory_sources`
- `memory_edges`
- `policy_actions`
- `retrieval_logs`
- `benchmark_results`

## 示例数据

包含的示例聊天文件：
- `data/sample_chats/project_day1_decision.json`
- `data/sample_chats/conflict_update.json`
- `data/sample_chats/project_day7_noise.json`

包含的基准测试用例文件：
- `data/benchmark/anti_noise_cases.json`
- `data/benchmark/conflict_cases.json`
- `data/benchmark/efficiency_cases.json`

这些文件是本地 MVP 的固定装置 (fixtures)，用于驱动提取、检索、冲突和基准测试开发，而无需依赖真实的飞书数据。

## 路线图

近期的实施顺序：

1. 阶段 2：示例加载器和原始事件摄入优化
2. 阶段 3：`MockLLM` 和记忆提取
3. 阶段 4：关键字检索
4. 阶段 5：协调和覆盖处理
5. 阶段 6：FastAPI 路由
6. 阶段 7：基准测试输出

## MVP 的非目标

本地 MVP 不会实现：
- 真实的飞书事件订阅
- 真实的 OpenClaw 运行时集成
- 飞书多维表格同步
- 完整的向量检索
- 时态知识图谱
- 强化学习 (RL) 控制器
- 隐式记忆标记 (latent memory token)
- 逻辑调制 (logit modulation)
- 多模态记忆

## 相关文档

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
- [docs/PROJECT_PROPOSAL.md](docs/PROJECT_PROPOSAL.md)
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- [AGENTS.md](AGENTS.md)

## 设计总结
MARS 最简短的心智模型：

```text
LLM 处理语义。
代码处理治理。
数据库处理状态。
策略处理编排。
```