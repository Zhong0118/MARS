# IMPLEMENTATION_PLAN.md

# MARS MVP 实施计划

本文件定义了 Codex 的分阶段实施计划。

重要原则：

```text
首先构建本地 MVP。
在本地 MVP 跑通之前，不要实现真实的 Feishu/OpenClaw 集成。
```

## MVP 全局目标

MVP 必须证明以下五项能力：

1. 从示例聊天 JSON 中提取决策记忆。
2. 根据查询搜索记忆并返回来源。
3. 处理冲突更新：旧记忆状态变为 `superseded`，新记忆状态变为 `active`。
4. 在注入噪声后检索目标记忆。
5. 运行基准测试 (benchmark) 并输出指标。

## 阶段 0：项目脚手架

### 目标

创建一个可运行的 Python 项目骨架。

### 要求

1. 使用 Python。
2. 使用 FastAPI。
3. 使用 SQLite。
4. 使用 Pydantic。
5. 使用基于本地文件的示例数据。
6. 不要实现真实的 Feishu/OpenClaw 集成。
7. 不要调用真实的 LLM。
8. 使用 MockLLM 使流水线可运行。

### 待创建的文件

```text
app/main.py
app/api/__init__.py
app/connectors/__init__.py
app/connectors/sample_loader.py
app/core/__init__.py
app/core/extractor.py
app/core/retriever.py
app/core/reconciler.py
app/core/policy.py
app/llm/__init__.py
app/llm/provider.py
app/storage/__init__.py
app/storage/db.py
app/storage/models.py
scripts/init_db.py
scripts/run_extract.py
scripts/search_memory.py
scripts/run_benchmark.py
data/sample_chats/project_day1_decision.json
data/sample_chats/conflict_update.json
data/sample_chats/project_day7_noise.json
data/benchmark/anti_noise_cases.json
data/benchmark/conflict_cases.json
data/benchmark/efficiency_cases.json
memory_store/.gitkeep
reports/.gitkeep
```

### 验收标准

```powershell
python scripts/init_db.py
```

必须创建：

```text
memory_store/mars.db
```

项目必须成功导入：

```powershell
python -c "from app.storage.models import RawEvent, MemoryObject"
```

------

## 阶段 1：数据模型与 SQLite 存储

### 目标

实现核心的 Pydantic 模型和 SQLite 持久化。

### 模型

实现：

```text
RawEvent
MemoryObject
MemoryEdge
MemorySource
PolicyAction
EvidencePack
```

### 数据库表

为以下内容实现 SQLite 初始化：

```text
raw_events
memory_objects
memory_sources
memory_edges
policy_actions
retrieval_logs
benchmark_results
```

### 要求

1. 所有类似 JSON 的字段都应作为 JSON 字符串存储在 SQLite 中。
2. 每个 `MemoryObject` 必须至少拥有一个 `source_event_id`。
3. 不进行记忆的物理删除。
4. 状态更新必须通过更新 `status` 字段来完成。

### 验收标准

运行：

```powershell
python scripts/init_db.py
```

创建所有数据表。

------

## 阶段 2：示例加载器与 RawEvent 摄入

### 目标

加载示例聊天 JSON 并将其转换为 `RawEvent`。

### 输入示例格式

```json
[
  {
    "message_id": "msg_001",
    "project_id": "carbon_platform",
    "chat_id": "chat_demo",
    "user_id": "u_001",
    "user_name": "张三",
    "time": "2026-05-01T10:00:00",
    "content": "我们一期是不是直接 Vue + FastAPI？"
  }
]
```

### 输出

每条消息都变成一个 `RawEvent`。

### 要求

1. 在 `raw_payload` 中保留原始消息。
2. 将 `source_type` 填充为 `sample_chat`。
3. 将 `event_type` 填充为 `message.created`。
4. 用消息时间填充 `valid_time_start`。
5. 存储到 `raw_events` 数据表中。

### 验收标准

```powershell
python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json --ingest-only
```

必须将原始事件 (raw events) 插入 SQLite 中。

------

## 阶段 3：MockLLM 与记忆提取

### 目标

使用 MockLLM 从讨论窗口中提取 `MemoryObject`。

### 要求

1. 在 `app/llm/provider.py` 中实现 MockLLM。
2. MockLLM 应针对示例数据返回确定性的结构化 JSON。
3. 实现 `app/core/extractor.py`。
4. 提取器 (Extractor) 读取 `RawEvent` 并生成 `MemoryObject`。
5. 所有 LLM 输出必须通过 Pydantic 验证。
6. 如果解析失败，返回错误或将记忆标记为 `pending`。

### 记忆类型

MVP 支持：

```text
decision
fact
procedure
risk
preference
```

### 验收标准

```powershell
python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json
```

必须至少创建一条 `active` 状态的决策记忆：

```text
一期 Demo 采用 Streamlit
```

并将其存储在 `memory_objects` 中。

------

## 阶段 4：关键字检索

### 目标

实现基于本地关键字的记忆搜索。

### 要求

1. 实现 `app/core/retriever.py`。
2. 根据查询关键字搜索 `memory_objects`。
3. 默认 `status` 过滤器：仅限 `active`。
4. 支持 `project_id` 过滤器。
5. 返回 `EvidencePack`。
6. `EvidencePack` 必须包含 `memory_id`、`title`、`content`、`status`、`score`、`source_event_ids`。

### 脚本

实现：

```text
scripts/search_memory.py
```

### 验收标准

提取后，运行：

```powershell
python scripts/search_memory.py "之前为什么不用 Vue？" --project-id carbon_platform
```

返回：

```text
一期 Demo 采用 Streamlit
source_event_ids
```

------

## 阶段 5：协调与覆盖 (Reconciliation and Supersede)

### 目标

使用 MockLLM 的关系判断来实现语义冲突处理。

### 要求

1. 实现 `app/core/reconciler.py`。
2. 输入新记忆或新声明。
3. 检索同一项目 (project) 和同一主题 (topic) 下的旧记忆。
4. 使用 MockLLM 判断关系。
5. 关系：

```text
duplicate
support
update
conflict
supersede
unrelated
```

6. 如果关系为 `supersede`：
   - 旧记忆的 `status` 变为 `superseded`
   - 新记忆的 `status` 变为 `active`
   - 新记忆的 `version` = 旧版本 + 1
   - 插入 `memory_edges`，关系为 `supersedes`
   - 插入 `policy_actions`，动作 (action) 为 `UPDATE/SUPERSEDE`

### 验收标准

给定：

```text
old: 一期 Demo 采用 Streamlit
new: 不对，一期改成 Vue + FastAPI
```

系统必须产生：

```text
old.status = superseded
new.status = active
memory_edges contains supersedes
policy_actions contains SUPERSEDE
```

------

## 阶段 6：FastAPI 路由

### 目标

将 MVP 功能作为 HTTP API 暴露出来。

### 路由

实现：

```http
POST /api/ingest/messages
POST /api/memory/extract
POST /api/memory/search
POST /api/memory/reconcile
POST /api/benchmark/run
GET  /health
```

### 要求

1. 使用 Pydantic 的请求和响应模型。
2. 不要暴露内部 SQLite 连接的详细信息。
3. 返回清晰的错误信息。
4. 所有路由都应能在本地进行测试。

### 验收标准

```powershell
uvicorn app.main:app --reload --port 8000
```

然后：

```powershell
curl http://127.0.0.1:8000/health
```

返回：

```json
{"status":"ok"}
```

------

## 阶段 7：基准测试 (Benchmark)

### 目标

实现基准测试脚本。

### 基准测试类型

1. 抗噪 (anti_noise)
2. 冲突 (conflict)
3. 效率 (efficiency)

### 文件

```text
data/benchmark/anti_noise_cases.json
data/benchmark/conflict_cases.json
data/benchmark/efficiency_cases.json
```

### 输出

```text
reports/benchmark_report.md
reports/benchmark_results.csv
```

### 指标

抗噪：

```text
Recall@1
Recall@3
Source Accuracy
```

冲突：

```text
Conflict Detection Accuracy
Supersede Accuracy
Status Accuracy
```

效率：

```text
Time Reduction
Step Reduction
Input Character Reduction
```

### 验收标准

```powershell
python scripts/run_benchmark.py
```

必须输出基准测试结果并将文件写入 `reports/` 目录下。

------

## 阶段 8：向量存储占位符 (Vector Store Placeholder)

### 目标

准备向量检索接口，但暂不需要完整的向量搜索。

### 要求

创建：

```text
app/storage/vector_store.py
```

包含接口：

```python
class VectorStore:
    def add_memory(self, memory): ...
    def search(self, query: str, top_k: int = 5): ...
```

MVP 可以使用无操作 (no-op) 或简单的占位符。

### 验收标准

代码成功导入且不会破坏检索功能。

------

## 阶段 9：OpenClaw 与 Feishu 适配器占位符

### 目标

创建适配器占位符，无需真实集成。

### 文件

```text
app/connectors/openclaw_adapter.py
app/connectors/feishu_event_adapter.py
```

### 要求

1. 定义将外部载荷 (payloads) 转换为 `RawEvent` 的函数。
2. 保留 `raw_payload`。
3. 为真实字段添加 TODO 注释。

### 验收标准

可以导入适配器并使用假载荷进行单元测试。

------

## 阶段 10：可选的入职资料包 (Optional Onboarding Pack)

### 目标

使用现有记忆实现本地的新人入职资料包生成。

### 要求

1. 添加 API：

```http
POST /api/memory/onboarding
```

2. 输入：

```json
{
  "project_id": "carbon_platform",
  "query": "给新人生成项目上下文包"
}
```

3. 输出部分：

```text
项目背景
关键决策
历史争议
当前有效结论
风险提醒
推荐阅读
来源链接
```

### 验收标准

从现有的 `MemoryObject` 返回结构化的入职资料包。

------

# 最终 MVP 完成标准

只有在所有命令均通过时，MVP 才算完成：

```powershell
python scripts/init_db.py

python scripts/run_extract.py \
  --input data/sample_chats/project_day1_decision.json

python scripts/search_memory.py \
  "之前为什么不用 Vue？" \
  --project-id carbon_platform

python scripts/run_extract.py \
  --input data/sample_chats/conflict_update.json

python scripts/search_memory.py \
  "现在一期技术路线是什么？" \
  --project-id carbon_platform

python scripts/run_benchmark.py

uvicorn app.main:app --reload --port 8000
```

预期行为：

1. 提取 Streamlit 决策。
2. 搜索返回带有来源的 Streamlit 记忆。
3. 冲突更新覆盖 (supersedes) Streamlit 并激活 (activates) Vue + FastAPI。
4. 搜索返回当前处于 `active` 状态的 Vue + FastAPI 决策。
5. 基准测试写入报告。
6. FastAPI 成功启动。