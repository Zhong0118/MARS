# MARS 数据库架构

这份文档解释了本地 MARS MVP 目前使用的 SQLite 架构。

它侧重于：
- 每个数据表的用途
- 表与表之间的关联关系
- 存在哪些索引以及原因
- 当前 MVP 需要哪些部分
- 目前保留了哪些部分以减少未来的迁移痛苦

## 1. 设计原则

数据库遵循以下规则：

- `raw_events` 是作为单一事实来源 (source-of-truth) 的原始账本
- 外部数据载荷 (payloads) 必须在进入核心逻辑之前进行标准化
- `memory_objects` 存储结构化的记忆，而不是原始聊天文本的堆砌
- 溯源 (provenance) 必须通过 `memory_sources` 明确表达
- 状态的改变必须体现在数据中，而不是隐藏在提示词 (prompts) 中
- 数据库存储是首要的；Markdown、报告或未来的飞书 (Feishu) 视图都是派生的输出

## 2. 架构概览

当前架构分为五层：

### 2.1 协作上下文

- `tenants`
- `users`
- `chats`
- `projects`
- `project_chats`
- `chat_memberships`

这些是轻量级的元数据表，有助于未来与飞书/OpenClaw 的集成，而无需现在就强制进行完整的服务器设计。

### 2.2 原始账本

- `raw_events`

这是仅追加 (append-only) 的事件账本。

### 2.3 记忆层

- `memory_objects`
- `memory_sources`
- `memory_edges`

这些表存储结构化记忆、溯源信息以及记忆之间的关系（例如覆盖/取代）。

### 2.4 行为与审计层

- `policy_actions`
- `retrieval_logs`
- `push_logs`

这些表用于解释系统为何执行动作、进行搜索或推送。

### 2.5 评估层

- `benchmark_results`

用于存储基准测试结果以便后续出具报告。

## 3. 逐表详解

### `raw_events`

用途：
- 存储每个标准化后的外部事件
- 在 `raw_payload_json` 中保留原始载荷
- 支持重放 (replay)、审计和溯源

重要字段：
- `event_id`: 内部主键
- `event_type`: 标准化后的内部事件类型，例如 `message.created`
- `source_type`: 事件的来源，例如 `sample_chat`
- `source_id`: 来源侧的事件/消息 ID
- `tenant_id`, `project_id`, `chat_id`, `thread_id`
- `actor_id`, `actor_name`
- `content`, `content_type`
- `transaction_time`
- `valid_time_start`, `valid_time_end`
- `raw_payload_json`

重要行为：
- 插入操作使用 `INSERT OR IGNORE`
- 不允许重复的源事件覆盖历史记录

### `memory_objects`

用途：
- 存储从原始事件中提取的结构化记忆

重要字段：
- `memory_id`
- `version_group_id`: 将同一个长期记忆的多个版本分组
- `memory_type`: `decision`, `fact`, `procedure`, `risk`, `preference`, `episode`, `skill`
- `scope`: `user`, `team`, `project`, `org`
- `tenant_id`, `project_id`, `user_id`
- `topic`
- `title`, `content`
- `rationale_json`, `objections_json`, `tags_json`
- `status`
- `version`
- `confidence`
- `importance`
- `valid_time_start`, `valid_time_end`
- `transaction_time`
- `supersedes`, `superseded_by`
- `created_at`, `updated_at`

注意：
- `source_event_ids` 不直接存储在这里
- 溯源信息存储在 `memory_sources` 中

### `memory_sources`

用途：
- 将一个记忆与一个或多个原始事件连接起来

重要字段：
- `memory_id`
- `event_id`
- `evidence_type`
- `quote`
- `source_url`

存在原因：
- 一个记忆可能由多个事件支持
- 一个事件可能支持多个记忆

### `memory_edges`

用途：
- 存储记忆对象之间明确的关系

重要字段：
- `source_memory_id`
- `target_memory_id`
- `relation_type`
- `reason`
- `confidence`

示例：
- `mem_new` `supersedes` `mem_old`

### `policy_actions`

用途：
- 审计重要的系统决策

重要字段：
- `action_type`
- `tenant_id`, `project_id`, `chat_id`, `thread_id`, `actor_id`
- `memory_id`
- `input_json`
- `candidate_json`
- `decision`
- `reason`
- `confidence`

典型的未来用途：
- 提取被接受或拒绝
- 协调 (reconciliation) 决策
- 推送/不推送的策略结果

### `retrieval_logs`

用途：
- 记录记忆搜索行为

重要字段：
- `query`
- `tenant_id`, `project_id`, `chat_id`, `thread_id`
- `requester_id`
- `query_type`
- `time_scope`
- `top_k`
- `status_filter`
- `retrieval_method`
- `retrieved_memory_ids_json`
- `selected_memory_ids_json`
- `score_json`
- `latency_ms`

当前状态：
- 架构已准备就绪
- 完整的检索日志记录行为将在后续阶段实现

### `push_logs`

用途：
- 记录主动的记忆推送或提醒

重要字段：
- `trigger_type`
- `tenant_id`, `project_id`, `chat_id`, `user_id`
- `memory_id`
- `push_channel`
- `push_content`
- `should_push`
- `policy_action_id`
- `user_feedback`

重要性：
- 频率控制
- 推送审计
- 后续的有用性评估指标

### `tenants`

用途：
- 存储工作空间或组织的元数据

当前角色：
- 为未来真实集成提供轻量级元数据表

### `users`

用途：
- 存储参与者元数据

当前角色：
- 为未来的聊天成员关系、入职和权限提供轻量级用户身份层

### `chats`

用途：
- 存储群组或对话的元数据

当前角色：
- 将事件和推送附加到稳定的聊天记录上

### `projects`

用途：
- 存储项目级别的作用域

当前角色：
- 使记忆和检索流程具备项目感知能力

### `project_chats`

用途：
- 将一个项目映射到一个或多个聊天

重要性：
- 一个真实的项目通常跨越多个飞书群组

### `chat_memberships`

用途：
- 将用户映射到聊天

重要性：
- 未来的新人入职
- 未来的访问过滤
- 未来的推送目标定位

### `benchmark_results`

用途：
- 存储抗噪 (anti-noise)、冲突 (conflict)、效率 (efficiency) 及后续测试的基准测试结果

## 4. 关键关系

主要关系：

```text
tenants -> users
tenants -> chats
tenants -> projects

projects <-> chats via project_chats
users <-> chats via chat_memberships

raw_events -> memory_sources -> memory_objects
memory_objects -> memory_edges -> memory_objects
policy_actions -> memory_objects
push_logs -> memory_objects
retrieval_logs -> project/chat/user context
```

最重要的溯源路径：

```text
memory_objects
    ->
memory_sources
    ->
raw_events
```

这就是 MARS 证明记忆来源的方式。

## 5. 当前索引策略

架构包含了针对最可能的早期查询的索引。

### 原始事件索引 (Raw event indexes)

- `idx_raw_events_source_unique`
- `idx_raw_events_tenant_project_time`
- `idx_raw_events_chat_time`
- `idx_raw_events_actor_time`

这些有助于：
- 对传入事件进行去重
- 构建讨论窗口
- 按租户、项目、聊天或执行者 (actor) 进行过滤

### 记忆索引 (Memory indexes)

- `idx_memory_project_status`
- `idx_memory_project_topic`
- `idx_memory_type_status`
- `idx_memory_valid_time`
- `idx_memory_version_group`

这些有助于：
- 活跃记忆的检索
- 主题级别的比较
- 版本链查找

### 溯源与关系索引 (Provenance and relation indexes)

- `idx_memory_sources_memory`
- `idx_memory_sources_event`
- `idx_memory_sources_unique`
- `idx_memory_edges_source`
- `idx_memory_edges_target`

这些有助于：
- 追踪来源
- 查找关系链
- 避免重复的溯源数据行

### 审计与推送索引 (Audit and push indexes)

- `idx_policy_actions_project_time`
- `idx_retrieval_logs_project_time`
- `idx_push_logs_memory_chat_time`
- `idx_push_logs_project_time`

这些有助于：
- 项目范围的审计
- 检索检查
- 推送频率控制

### 映射表唯一索引 (Mapping table unique indexes)

- `idx_project_chats_unique`
- `idx_chat_memberships_unique`

这些可防止重复映射。

## 6. MVP 与面向未来的部分 (MVP vs Future-Ready Parts)

### 当前 MVP 必需项

- `raw_events`
- `memory_objects`
- `memory_sources`
- `memory_edges`
- `policy_actions`
- `retrieval_logs`
- `benchmark_results`

### 现在添加以减少后续重构工作的部分

- `push_logs`
- `tenants`
- `users`
- `chats`
- `projects`
- `project_chats`
- `chat_memberships`
- `version_group_id`
- 额外的审计元数据字段

这些附加内容仍然是轻量级的。 它们不需要真正的飞书集成，但使架构更容易演进。

## 7. 迁移策略

该项目目前在 `initialize_database()` 内部使用了简单的架构初始化加上轻量级的兼容性迁移。

现在的做法：
- 创建缺失的数据表
- 在需要时向较旧的本地数据库添加新引入的列
- 在表/列检查后创建索引

存在的原因：
- 本地开发已经产生了较旧的 `mars.db` 文件
- 仅靠 `CREATE TABLE IF NOT EXISTS` 无法添加新列

当前的迁移辅助工具：
- `migrate_legacy_schema()`

对于 MVP 来说，这是有意保持简单的。 如果该项目以后成为一个长期运行的服务，它应该转向一个更明确的迁移系统。

## 8. 存储边界规则

该架构是围绕以下边界设计的：

- connectors 了解外部数据载荷格式
- `RawEvent` 是规范化的边界对象
- core 逻辑基于内部模型运作
- `db.py` 是向 SQLite 序列化的边界

这种分离将使 MARS 能够从：

```text
local sample JSON + SQLite
```

演进为：

```text
Feishu events + OpenClaw + server deployment + larger databases
```

而无需重写整个系统。

## 9. 阶段 2 和阶段 3 如今的使用情况 (What Phase 2 and Phase 3 Use Today)

当 `scripts/run_extract.py` 运行时：

1. 加载示例 JSON
2. 将消息标准化为 `RawEvent`
3. 插入 `raw_events` 数据行
4. 执行轻量级 tenant/project/chat/user 元数据的 upsert（插入或更新）
5. `MockLLM` 生成确定性的记忆候选对象
6. 插入经过验证的 `MemoryObject` 数据行
7. 将溯源数据行写入 `memory_sources`

这意味着当前的 MVP 数据路径现在是：

```text
sample JSON
    ->
RawEvent
    ->
raw_events
    ->
MockLLM extraction
    ->
memory_objects + memory_sources
```