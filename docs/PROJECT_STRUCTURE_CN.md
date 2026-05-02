# MARS 项目结构

这份文档解释了每个文件夹的职责、目前包含的具体文件，以及这些文件如何契合 MVP（最小可行性产品）计划。

我们的目标是：随着项目从本地 MVP 逐步发展为更完整的记忆引擎，使代码库依然易于导航。

## 1. 顶层文件夹 (Top-level folders)

### `app/`

MARS 引擎的应用程序源代码。

当前职责：
- 保持外部适配器与核心逻辑的分离
- 存放内部模型和存储代码
- 暴露一个用于本地验证的极简 FastAPI 应用程序s

子文件夹：
- `api/`: 预留给 HTTP 路由模块
- `connectors/`: 将外部输入转换为 `RawEvent` 的适配器
- `core/`: 提取、检索、协调和策略逻辑
- `llm/`: 位于稳定接口背后的模拟或真实的 LLM 供应商
- `storage/`: Pydantic 模型和 SQLite 持久化辅助工具

### `data/`

MVP 使用的静态本地输入数据。

当前职责：
- 提供用于摄入的示例聊天数据载荷
- 为后续阶段提供简单的基准测试用例文件

子文件夹：
- `sample_chats/`: 用于驱动提取和冲突演示的聊天记录
- `benchmark/`: 抗噪、冲突和效率测试的用例定义

### `scripts/`

用于本地开发和 MVP 验证的命令行入口。

当前职责：
- 创建数据库
- 摄入示例聊天文件
- 为后续的搜索和基准测试逻辑定义稳定的脚本接口

### `memory_store/`

本地生成的存储。

当前职责：
- 存放 SQLite 数据库文件 `mars.db`

注意事项：
- 属于运行时状态，而非源代码
- 存在 `.gitkeep` 是为了确保该文件夹在代码库中被保留

### `reports/`

评估和报告所生成的输出。

当前职责：
- 预留用于未来的基准测试报告和导出

### `docs/`

项目文档和规划材料。

当前职责：
- 解释系统目标、架构、提案和实施阶段
- 现在也包含了这份代码库结构指南

## 2. 当前源文件 (Current source files)

### `app/main.py`

目的：
- FastAPI 应用程序入口
- 暴露 `GET /health` 用于本地活跃度检查

目前存在的原因：
- 在添加真正的 API 路由之前，阶段 0 需要一个可运行的应用程序骨架

### `app/api/__init__.py`

目的：
- 将 `app/api` 标记为 Python 包

目前存在的原因：
- 即使在添加具体的路由模块之前，也能保持包的布局与架构和计划保持一致

### `app/connectors/__init__.py`

目的：
- 将 `app/connectors` 标记为 Python 包

### `app/connectors/sample_loader.py`

目的：
- 读取本地示例 JSON 文件
- 将示例消息转换为内部的 `RawEvent` 对象

关键函数：
- `load_sample_messages`: 加载原始 JSON 消息
- `message_to_raw_event`: 将一条外部消息映射为内部结构
- `load_raw_events`: 加载并标准化整个文件

架构重要性：
- 这是 MVP 的适配器边界
- 示例 JSON 格式仅保留于此，不会泄露到核心模块中

### `app/core/__init__.py`

目的：
- 将 `app/core` 标记为 Python 包

### `app/core/extractor.py`

目的：
- 将 `RawEvent` 窗口转换为 `MemoryObject` 记录的占位符

当前状态：
- 仅有脚手架代码

后续阶段：
- 将使用 `MockLLM` 接管记忆提取工作流

### `app/core/retriever.py`

目的：
- 关键字记忆检索的占位符

当前状态：
- 仅有脚手架代码

后续阶段：
- 将实现返回 `EvidencePack` 的项目感知搜索

### `app/core/reconciler.py`

目的：
- 记忆关系判断和覆盖处理的占位符

当前状态：
- 仅有脚手架代码

后续阶段：
- 将新记忆与现有记忆进行比较，并更新状态、边缘关系和策略动作

### `app/core/policy.py`

目的：
- 策略层编排的占位符

当前状态：
- 返回一个无操作的 `PolicyAction`

后续阶段：
- 将协调写入/更新行为，并审计策略决策

### `app/llm/__init__.py`

目的：
- 将 `app/llm` 标记为 Python 包

### `app/llm/provider.py`

目的：
- 定义本地 `MockLLM` 供应商接口

当前状态：
- 仅有确定性的占位符方法

后续阶段：
- 将针对示例场景返回结构化的提取和关系判断输出

### `app/storage/__init__.py`

目的：
- 将 `app/storage` 标记为 Python 包

### `app/storage/models.py`

目的：
- 定义在整个系统中共享的内部 Pydantic 模型

当前模型：
- `RawEvent`
- `MemoryObject`
- `MemoryEdge`
- `MemorySource`
- `PolicyAction`
- `EvidencePack`

架构重要性：
- 此文件是 connectors、core 逻辑和 storage 之间的内部契约
- 溯源要求在此处被强制执行，例如 `MemoryObject` 必须包含至少一个 `source_event_id`

### `app/storage/db.py`

目的：
- 管理 SQLite 文件路径
- 初始化数据库架构
- 将 Pydantic 对象序列化为对 SQLite 友好的数据行
- 为早期阶段的脚本提供数据插入的辅助工具

关键函数：
- `ensure_storage_dirs`
- `get_connection`
- `initialize_database`
- `schema_statements`
- `insert_raw_events`
- `insert_memory_object`
- `insert_memory_sources`
- `insert_memory_edge`
- `insert_policy_action`

架构重要性：
- 这是 Python 模型转换为数据库数据行的边界
- 类似 JSON 的字段在此处被显式序列化为 SQLite 文本字段

## 3. 当前 CLI 脚本 (Current CLI scripts)

### `scripts/init_db.py`

目的：
- 创建 `memory_store/mars.db`
- 创建所有必需的 SQLite 数据表

阶段：
- 阶段 0 和阶段 1

### `scripts/run_extract.py`

目的：
- 将示例聊天文件摄入 `raw_events`

当前行为：
- 初始化数据库
- 加载本地示例 JSON
- 将消息转换为 `RawEvent`
- 将它们插入 SQLite

后续阶段：
- 也将触发记忆提取

### `scripts/search_memory.py`

目的：
- 为未来本地记忆检索提供稳定的 CLI 形态

当前行为：
- 仅作为占位符

### `scripts/run_benchmark.py`

目的：
- 为未来基准测试运行提供稳定的 CLI 形态

当前行为：
- 仅作为占位符
- 确保 `reports/` 目录存在

## 4. 当前数据文件 (Current data files)

### `data/sample_chats/project_day1_decision.json`

目的：
- 用于首次技术路线决策的基础讨论示例

后续使用：
- 提取演示
- 检索演示

### `data/sample_chats/conflict_update.json`

目的：
- 用于模拟覆盖决策的后续跟进示例

后续使用：
- 协调演示

### `data/sample_chats/project_day7_noise.json`

目的：
- 包含无关消息，用于测试抗噪检索行为

### `data/benchmark/anti_noise_cases.json`

目的：
- 针对嘈杂检索的基准测试用例定义

### `data/benchmark/conflict_cases.json`

目的：
- 针对冲突和覆盖行为的基准测试用例定义

### `data/benchmark/efficiency_cases.json`

目的：
- 针对节省时间/步骤比较的基准测试用例定义

## 5. 支持文件 (Supporting files)

### `requirements.txt`

目的：
- MVP 骨架的本地 Python 依赖项

当前包：
- `fastapi`
- `pydantic`
- `uvicorn`

### `AGENTS.md`

目的：
- 针对编程代理的代码库级别实施约束

要点：
- 本地 MVP 优先
- 目前没有真正的 Feishu/OpenClaw 集成
- 溯源是强制性的
- 不进行记忆的物理删除

### `README.md`

目的：
- 高层面的项目介绍和运行说明

### `docs/ARCHITECTURE.md`

目的：
- 系统架构和数据模型定义

### `docs/IMPLEMENTATION_PLAN.md`

目的：
- MVP 的分阶段实施清单

### `docs/PROJECT_PROPOSAL.md`

目的：
- 更广泛的项目叙述和定位

## 6. 已实现与占位符对比 (What is implemented vs placeholder)

在阶段 0/1 中实现的内容：
- 包结构
- 内部 Pydantic 模型
- SQLite 架构初始化
- 将示例 JSON 摄入 `raw_events`
- 带有 `/health` 的 FastAPI 应用程序骨架

后续阶段的占位符：
- 记忆提取
- 关键字检索
- 协调逻辑
- 基准测试执行
- 更丰富的 API 路由

## 7. 新工作应去向何处 (Where new work should go)

在继续开发 MVP 时，接下来的变更主要应落在以下位置：

- 阶段 2: `app/connectors/sample_loader.py`, `scripts/run_extract.py`, `app/storage/db.py`
- 阶段 3: `app/llm/provider.py`, `app/core/extractor.py`
- 阶段 4: `app/core/retriever.py`, `scripts/search_memory.py`
- 阶段 5: `app/core/reconciler.py`, `app/core/policy.py`, `app/storage/db.py`
- 阶段 6: `app/api/` 和 `app/main.py`
- 阶段 7: `scripts/run_benchmark.py`, `reports/`, `data/benchmark/`

## 8. 快速心智模型 (Quick mental model)

如果你只记住关于这个代码库结构的一件事，请记住以下几点：

- `connectors` 将外部数据转换为内部事件
- `storage` 定义并持久化这些内部对象
- `core` 决定如何提取、搜索和更新记忆
- `llm` 提供语义支持
- `scripts` 和 `api` 是人类或其他系统调用 MARS 的途径