# MARS 六层演进路线

## 0. 当前系统状态

### 已完成

```
写入链: RawEvent -> WindowBuilder -> TopicTracker -> LLM Extractor
        -> PostProcessor -> Consolidator -> Reconciler -> Memory Store

查询链: User Query -> QueryPlanner -> Retriever -> Answerer -> Response
```

- WindowBuilder: 5 种分裂信号（时间/消息数/线程/shift marker/topic marker 偏移）
- TopicTracker: 5 级 cascade（marker -> LLM -> hint -> overlap -> fallback）
- Consolidator: 三级 prefilter + LLM pair judgment + trace 可观测性
- Reconciler: 逐候选 LLM judge_relation + 精确 supersede
- Retriever: 关键词评分 + 语义分 + 类型加权 + plan 优先级
- Answerer: LLM 合成答案 + select_primary fallback
- 14-case consolidation eval set，全部通过

### 核心瓶颈

1. **窗口切分靠规则堆叠，缺乏会话状态感知**
   - 无法识别"回到旧话题"
   - 无法区分"同一话题跨越了一个无关插播"和"真的换了话题"
   - max_messages_per_window=8 是硬限，不考虑语义边界

2. **LLM Extractor 只看当前窗口**
   - 不知道前面窗口提过什么
   - 不知道库里已有哪些 memory
   - 容易重复抽取或丢失跨窗口推理

3. **Reconciler 候选检索靠全量扫描**
   - `list_memories(project_id, status='active')` 拿全部 active memory
   - 再在 Python 按 version_group_id / topic 过滤
   - 无 embedding，无倒排索引

4. **缺少过程型记忆**
   - 只有 decision/fact/risk/procedure/preference/episode
   - 没有 workflow pattern / resolution path / onboarding sequence

5. **无主动召回能力**
   - 系统完全被动，只响应查询

6. **无反馈闭环**
   - 不知道哪些 memory 有用、哪些 merge 判断错误

---

## 1. 会话理解层（Session Understanding Layer）

### 优先级：P0 — 当前最该做的

### 为什么最优先

所有下游质量问题的根源是：**给 LLM 的窗口不对**。

窗口切错了，extraction 就歪；extraction 歪了，consolidation 和 reconciliation 都在补锅。
把窗口做对，后面的链条会自然改善。

### 当前问题

| 问题 | 现状 | 应该 |
|------|------|------|
| topic 被切碎 | 同一话题被时间间隔或消息数硬切成 2-3 个窗口 | 连续话题应在一个窗口 |
| 话题混在一起 | 两个不同话题在同一窗口内 | 话题切换处应分裂 |
| 无法识别话题回归 | A-B-A 模式只靠 bridge merge 兜底 | 应在窗口层直接识别 |
| shift marker 覆盖不全 | 依赖 12 个固定短语 | 中文群聊中话题切换方式远不止这些 |

### 要做的 3 个模块

#### 1.1 SessionTracker

**职责**：维护一个 chat 内的话题状态机。

```
输入: 一个 RawEvent stream（按时间排序）
输出: 每条 event 的 topic_state 标注
      - new_topic: 全新话题
      - continuation: 延续当前话题
      - resume: 回到之前讨论过的话题
      - drift: 话题逐渐偏移
```

**技术方案**：

- 维护一个 `active_topics: list[TopicState]`，每个包含 `label`, `last_seen_time`, `key_tokens`, `event_count`
- 每条新 event 到来时：
  1. 与当前 active topic 做 token overlap
  2. 与历史 topic 做 token overlap（检测 resume）
  3. 如果 overlap 都很低，标记为 new_topic
  4. 如果与当前 topic overlap 高，标记为 continuation
  5. 如果与某个历史 topic overlap 高但当前 topic overlap 低，标记为 resume
- 当 new_topic 或 resume 触发时，更新 active_topics 栈

**不用 LLM**：这层纯规则 + token overlap，速度快，可以处理每条 event。

**输出数据结构**：

```python
@dataclass
class TopicState:
    label: str
    key_tokens: set[str]
    last_seen_time: str
    event_count: int
    status: Literal["active", "paused", "closed"]

@dataclass
class EventTopicAnnotation:
    event_id: str
    topic_state: Literal["new_topic", "continuation", "resume", "drift"]
    matched_topic: str | None
    confidence: float
```

#### 1.2 WindowBuilder v2

**职责**：基于 SessionTracker 的标注，做更智能的窗口切分。

**与现有 WindowBuilder 的关系**：替换，不是并存。

**切分规则变化**：

| 信号 | 现在 | v2 |
|------|------|-----|
| 时间间隔 | 30 分钟硬切 | 保留，但 resume 场景下不切 |
| 消息数上限 | 8 条硬切 | 提高到 12，但遇到 new_topic 就切 |
| shift marker | 12 个短语触发切分 | 降级为辅助信号，不单独决定 |
| topic marker divergence | 需要 overlap < 0.2 且 marker 不一致 | 由 SessionTracker 直接提供 |
| **新增：topic_state** | 无 | new_topic → 切分；resume → 开新窗口或合并回旧窗口 |
| **新增：token 预算** | 无 | 窗口总 token 不超过 2000（给 LLM 留余量） |

**核心逻辑**：

```
for event in stream:
    annotation = session_tracker.annotate(event)
    if annotation.topic_state == "new_topic":
        close_current_window()
        start_new_window(event)
    elif annotation.topic_state == "resume":
        close_current_window()
        start_new_window(event, resumed_topic=annotation.matched_topic)
    elif annotation.topic_state == "continuation":
        if current_window.token_count + event_tokens > TOKEN_BUDGET:
            close_current_window()
            start_new_window(event)  # 同 topic 续窗口
        else:
            append_to_current_window(event)
    elif annotation.topic_state == "drift":
        append_to_current_window(event)  # drift 不切，让 LLM 判断
```

**bridge merge 的去留**：

v2 中 bridge merge 不再需要——因为 SessionTracker 的 resume 检测直接解决了 A-B-A 模式。如果 B 很短且 A 在 B 之后 resume，B 会单独成窗口或被丢弃，A 的两段会各自成为独立窗口但共享 topic。

#### 1.3 ContextAssembler

**职责**：决定给 LLM Extractor 送什么上下文。

**现在的问题**：Extractor 只看当前窗口的 events，完全没有跨窗口上下文。

**v2 的输入结构**：

```python
@dataclass
class ExtractionContext:
    current_window: DiscussionWindow      # 当前窗口
    bridge_events: list[RawEvent]          # 前一窗口最后 2-3 条消息（上下文过渡）
    topic_history: list[str]               # 最近 3 个 topic label
    recent_memory_titles: list[str]        # 同 topic 最近 3 条 active memory 的 title
```

**为什么需要 recent_memory_titles**：

让 LLM 知道"这个 topic 下已经有哪些 memory"，避免重复抽取。
例如：如果库里已有 "Use Streamlit for phase one"，LLM 看到后就不会再抽一条一模一样的。

**不传全量 memory content**——只传 title，控制 token 消耗。

### 预期结果

- 同一话题不再被切碎成多个窗口
- 不同话题不再被混入同一窗口
- A-B-A 话题回归能被正确识别
- LLM 提取时知道上下文，减少重复提取
- extraction 质量提升 → consolidation 压力下降

### 验证方式

1. 在 `project_mixed_topics.json` 上跑 WindowBuilder v2，对比 v1 的窗口数量和窗口内容
2. 在 `project_realistic_multiday.json` 上跑完整链，对比 extraction 结果
3. 新建 `window_eval_cases.json`：5-8 个手工标注的窗口切分 case，验证切分正确率

---

## 2. 记忆治理层（Memory Governance Layer）

### 优先级：P1 — 在会话理解层之后

### 现有基础

```
PostProcessor -> Consolidator -> Reconciler
```

已经覆盖了：
- topic normalization
- stable ID generation
- status adjustment / drop
- 三级 prefilter + LLM merge judgment
- 精确 supersede + duplicate skip + conflict mark

### 还缺什么

| 缺失 | 说明 |
|------|------|
| 记忆衰减 | 长期不被检索也不被引用的 memory 应该降低重要度，但不删除 |
| 过期管理 | `valid_time_end` 字段存在但从未被使用 |
| 主记忆 vs supporting 显式标记 | consolidation merge 后，哪条是主记忆、哪些是 supporting 没有持久化 |
| confidence 衰减 | 时间越久、没有新证据的 memory，confidence 应逐步降低 |
| 同 topic 主记忆唯一性 | 一个 topic 下可能有多条 active decision，但应该只有一条"当前有效决策" |

### 要做的事

#### 2.1 记忆生命周期管理

**freshness_score 计算**：

```python
days_since_last_use = (now - last_retrieved_at).days
freshness = max(0.3, 1.0 - days_since_last_use * 0.02)
effective_importance = importance * freshness
```

- 不删除，只降权
- `retrieval_logs` 表已有使用记录，可直接查

**valid_time_end 启用**：

- PostProcessor 中，如果 LLM 抽出的 memory 包含时间约束（如"下周五之前"），自动设 `valid_time_end`
- Retriever 中，过了 valid_time_end 的 memory 降权但不排除

#### 2.2 主记忆标记

在 MemoryObject 上新增字段（不加新表）：

```python
is_primary: bool = False          # 同 topic 下的主记忆
supporting_memory_ids: list[str]  # 被合并进来的 memory ID 列表
```

Consolidator merge 时自动设置。
Retriever 优先返回 `is_primary=True` 的记忆。

#### 2.3 同 topic 主记忆唯一性

规则：一个 `(project_id, topic, memory_type)` 组合下，`status=active` 且 `is_primary=True` 的记忆最多 1 条。

当新的 primary decision 入库时，旧的 primary decision 自动 supersede。
这比现在靠 Reconciler 全量扫描再 LLM 判断更可控。

### 技术方案

- 不加新数据库表
- MemoryObject 加 2 个字段
- 不引入新外部依赖
- freshness 计算在 Retriever 内完成，不改 DB 结构

### 预期结果

- 旧记忆自然退居次要位置，不需要手动清理
- 同 topic 下的主记忆清晰可辨
- 查询"当前技术路线"时，不会同时返回 3 条 active decision

---

## 3. 过程记忆层（Process Memory Layer）

### 优先级：P2 — 在治理层稳定之后

### 为什么需要

当前系统只存**结论型记忆**：

- "决策是 Streamlit"
- "风险是网络不稳"
- "事实是 Python 代码库"

但不存**过程型记忆**：

- "做技术选型时，先评估了 3 个方案，最终因为时间压力选了 Streamlit"
- "遇到部署问题时，先检查网络，再检查包依赖，最后走本地 fallback"
- "新同学入组时，先看架构文档，再跑一遍 demo，最后领一个 starter task"

### 新增的 memory_type

```python
MemoryType = Literal[
    # 现有
    "decision", "fact", "procedure", "risk", "preference", "episode", "skill",
    # 新增
    "workflow",      # 工作流程模式：A -> B -> C
    "resolution",    # 问题解决模式：遇到 X，做 Y，结果 Z
    "onboarding",    # 入职路径：新人应做 step1, step2, step3
]
```

### 提取方式

**不靠规则提取，靠 LLM 识别。**

在 extract_memories 的 prompt 中增加类型说明：

```
- workflow: A recurring sequence of steps the team follows for a specific activity.
  Example: "For code review, first run linter, then check test coverage, then request review."
- resolution: A problem-solving pattern: what problem was encountered, what was tried, what worked.
  Example: "When deployment failed, team checked network first, then found package version mismatch."
- onboarding: Steps or information a new team member should follow or know.
  Example: "New members should first read the architecture doc, then run the demo locally."
```

### 存储

- 复用现有 MemoryObject 结构，不加新表
- `memory_type` 字段已经是 Literal union，只需扩展
- `content` 中存具体步骤描述
- `rationale` 中存为什么这么做

### 检索适配

QueryPlanner 中新增关键词映射：

```python
elif any(kw in lowered for kw in ["how to", "steps", "process", "workflow"]):
    query_type = "process_lookup"
    primary_types = ["workflow", "procedure", "resolution"]
```

### 预期结果

- 系统不只记住"结论"，还记住"怎么得出结论的"
- 新人查 "how to do code review" 能直接得到团队的工作流
- 遇到类似问题时能召回过去的解决模式

### 风险

- 过程型记忆更长、更复杂，对 LLM 提取质量要求更高
- 需要更多 sample data 来验证
- **建议：先做 workflow 一种，验证可行后再加 resolution 和 onboarding**

---

## 4. 检索与回答层（Retrieval & Answer Layer）

### 优先级：P2 — 与过程记忆层并行

### 拆成两个子层

#### 4.1 检索层升级

**现状**：纯关键词评分 + 规则加权。

**演进路径**（分三步，不一步到位）：

**Step A — 结构化预过滤（当前即可做）**

在关键词评分之前，先用 SQL 精确过滤：

```sql
WHERE project_id = ? AND status = 'active'
  AND (topic = ? OR topic IS NULL)
  AND memory_type IN (?, ?, ?)
```

减少 Python 侧评分的候选集大小。

**Step B — 倒排索引（中期）**

用 SQLite FTS5 建立全文索引：

```sql
CREATE VIRTUAL TABLE memory_fts USING fts5(
    memory_id, title, content, tags,
    content='memory_objects'
);
```

查询时先用 FTS5 召回 top-50，再用现有评分逻辑 rerank。
不引入外部依赖，SQLite 原生支持。

**Step C — 向量检索（后期）**

- 选项 A：sqlite-vec 扩展（单机，无额外进程）
- 选项 B：Chroma / Qdrant（需要额外服务）
- **建议选 A**，与现有 SQLite 架构一致

向量不替代关键词，而是并行召回：

```
candidates = keyword_recall(top=30) ∪ vector_recall(top=30)
reranked = score_and_sort(candidates)
```

#### 4.2 回答层升级

**现状**：LLM 生成一段话 + select_primary fallback。

**目标结构**：

```python
@dataclass
class StructuredAnswer:
    conclusion: str              # 当前结论
    basis: list[str]             # 支撑依据（来自哪些 memory）
    risks: list[str]             # 相关风险
    unresolved: list[str]        # 未解决项
    citations: list[Citation]    # 出处引用
```

**Citation 结构**：

```python
@dataclass
class Citation:
    memory_id: str
    title: str
    memory_type: str
    confidence: float
```

这不需要改大架构——只需要改 answerer 的 prompt，让 LLM 按结构输出，然后解析。

### 预期结果

- 检索速度：从全量扫描 → FTS5 预过滤 → 评分候选集缩小 5-10x
- 回答质量：从一段模糊文本 → 结论 + 依据 + 风险 + 出处
- 可审计：每条结论都有明确的 memory 来源

---

## 5. 主动召回层（Summoning Layer）

### 优先级：P3 — 在检索回答层稳定之后

### 现状

系统完全被动。用户不查，就没有输出。

### 4 种召回场景

#### 5.1 时间触发

```
条件: 项目有 deadline memory，距 deadline <= 3 天
动作: 生成 "项目进度提醒" 推送
内容: 当前活跃的 decision + risk + 剩余时间
```

#### 5.2 事件触发

```
条件: 新 event 内容与某条 active risk 的 content overlap > 0.4
动作: 生成 "风险再次触发" 提醒
内容: 原始 risk + 本次触发事件
```

#### 5.3 人员触发

```
条件: 新成员加入群聊（通过 Feishu event 检测）
动作: 生成 onboarding pack
内容: 当前 active decisions + procedures + risks 的摘要
```

#### 5.4 重复讨论触发

```
条件: 当前 extraction 窗口讨论的话题与某条 superseded memory 高度重叠
动作: 提醒 "这个问题之前已经做过决策"
内容: 原始决策 + 被替代的旧决策
```

### 技术方案

```python
class Summoner:
    def check_triggers(self, events: list[RawEvent], memories: list[MemoryObject]) -> list[SummonCard]:
        cards = []
        cards.extend(self._check_deadline_triggers(memories))
        cards.extend(self._check_risk_triggers(events, memories))
        cards.extend(self._check_duplicate_discussion(events, memories))
        return cards

@dataclass
class SummonCard:
    trigger_type: str              # deadline / risk_echo / onboarding / duplicate_discussion
    title: str
    content: str
    related_memory_ids: list[str]
    urgency: Literal["low", "medium", "high"]
    created_at: str
```

### 推送渠道

MVP 阶段：只在 API response 中附带 `summon_cards`，不主动推 Feishu。

```python
class ExtractResponse(BaseModel):
    raw_event_count: int
    extracted_count: int
    memories: list[MemoryObject]
    summon_cards: list[SummonCard] = []  # 新增
```

后期再对接 Feishu webhook。

### 预期结果

- 系统从"被动数据库"变为"主动助手"
- 关键信息不被遗忘（deadline、风险、旧决策）
- 新人入职体验显著改善

---

## 6. 反馈与学习层（Feedback Adaptation Layer）

### 优先级：P4 — 最后做

### 为什么不做 RL

RL 需要：
- 明确的 reward signal
- 大量的 episode
- 参数更新机制

当前都不具备。

### 做什么

**轻量反馈收集 + 规则调优**。

#### 6.1 反馈信号

```python
class MemoryFeedback(BaseModel):
    feedback_id: str
    memory_id: str
    feedback_type: Literal["useful", "wrong", "outdated", "merge_error", "missing"]
    user_id: str | None
    comment: str | None
    created_at: str
```

**采集方式**：

- 查询结果中附带 "这条有用吗?" 反馈按钮（API 层面）
- 手动 CLI 反馈（`scripts/feedback.py`）

#### 6.2 反馈驱动的调优

不改模型参数，只调运行时配置：

| 反馈类型 | 调优动作 |
|----------|----------|
| 某类 memory 频繁被标 "useful" | 提高该类型在 Retriever 中的 value_score 权重 |
| 某条 merge 被标 "merge_error" | 收集错误 pair → 加入 consolidation eval set |
| 某个 topic normalization 经常错 | 修正 `config/topic_markers.json` 中的关键词映射 |
| 某类 memory 总是被标 "wrong" | 调高 PostProcessor 中该类型的 drop_confidence_threshold |

**本质是：人工反馈 → 配置文件调优 → 规则更新 → 效果提升**

不是 RL，是 human-in-the-loop config tuning。

#### 6.3 使用统计

已有 `retrieval_logs` 表，可直接分析：

```sql
-- 哪些 memory 被频繁检索
SELECT memory_id, COUNT(*) as hit_count
FROM retrieval_logs
GROUP BY memory_id
ORDER BY hit_count DESC;

-- 哪些 topic 最常被查询
SELECT json_extract(plan_json, '$.normalized_topic') as topic, COUNT(*)
FROM retrieval_logs
GROUP BY topic;
```

### 预期结果

- 系统质量随使用时间逐步提升
- 错误模式被系统性修复而非逐个补丁
- 不需要训练任何模型

---

## 执行顺序总览

```
Phase A: 会话理解层（P0）
├── A1: SessionTracker
├── A2: WindowBuilder v2
├── A3: ContextAssembler
└── A4: 窗口切分 eval set + 验证

Phase B: 记忆治理层（P1）
├── B1: freshness_score + valid_time_end
├── B2: is_primary + supporting_memory_ids
└── B3: 同 topic 主记忆唯一性

Phase C: 并行推进（P2）
├── C1: 过程记忆 — 先做 workflow 类型
├── C2: 检索层 — FTS5 预过滤
└── C3: 回答层 — 结构化输出

Phase D: 主动召回（P3）
├── D1: SummonCard + 触发器框架
├── D2: deadline 触发
└── D3: 重复讨论触发

Phase E: 反馈适应（P4）
├── E1: MemoryFeedback 表 + 采集
├── E2: 使用统计分析
└── E3: 配置调优闭环
```

### 关键依赖关系

```
A (会话理解) → 无前置依赖，立即可做
B (治理层)   → 依赖 A 稳定（窗口对了治理才有意义）
C1 (过程记忆) → 依赖 A（好的窗口才能抽出过程型记忆）
C2 (FTS5)    → 无依赖，可与 A 并行
C3 (结构化回答) → 无依赖，可与 A 并行
D (召回)     → 依赖 B（需要 freshness / primary 标记）
E (反馈)     → 依赖 C（需要有用户使用数据）
```

### 可并行的组合

```
Phase A + C2(FTS5) + C3(结构化回答)
```

这三件没有依赖关系，可以同时推进。

---

## 每一层的不做清单

| 层 | 不做 |
|-----|------|
| 会话理解 | 不做 LLM-based 窗口切分（太贵），不做跨 chat 会话追踪 |
| 治理 | 不做自动删除 memory，不做版本分支 |
| 过程记忆 | 不做知识图谱，不做因果推理 |
| 检索回答 | 不做多模态检索，不做外部搜索引擎集成 |
| 主动召回 | 不做真正的 Feishu push（MVP 只在 API response 里带），不做定时轮询 |
| 反馈 | 不做 RL，不做参数训练，不做 A/B 测试框架 |

---

## Phase A 细化：会话理解层的具体开发步骤

既然 Phase A 是立即要做的，这里给出更细的步骤：

### Step A1: SessionTracker（2-3 天）

1. 定义 `TopicState` 和 `EventTopicAnnotation` 数据结构
2. 实现 token overlap 比较逻辑（复用 `tokenize_text`）
3. 实现 topic stack 管理（new / continuation / resume / drift）
4. 写 5 个单元测试 case：
   - 单话题连续消息 → 全标 continuation
   - 两个话题交替 → 正确标 new_topic
   - A-B-A 模式 → 第三段标 resume
   - 长时间间隔后同话题 → resume
   - 完全无关消息插入 → drift 或 new_topic

### Step A2: WindowBuilder v2（2-3 天）

1. 基于 SessionTracker 输出重写窗口切分逻辑
2. 加入 token 预算控制
3. 去掉 bridge merge（由 SessionTracker 替代）
4. 写 3 个窗口切分 eval case（手工标注期望的窗口边界）
5. 在 `project_mixed_topics.json` 上对比 v1 vs v2 的窗口划分

### Step A3: ContextAssembler（1-2 天）

1. 定义 `ExtractionContext` 数据结构
2. 实现 bridge_events 截取（前窗口最后 2-3 条）
3. 实现 recent_memory_titles 查询（同 topic 最近 3 条 active memory）
4. 修改 `extractor.py` 接受 ExtractionContext 作为输入
5. 修改 LLM prompt 使用新的上下文结构

### Step A4: 验证（1 天）

1. 跑 `project_realistic_multiday.json`，对比 extraction 结果
2. 跑 consolidation eval set，确认不回归
3. 跑 `search_memory.py` 查询，确认查询质量不降
4. 记录对比数据：窗口数、memory 数、merge 率、LLM 调用数

### 总计：约 1 周

---

## CandidateRetriever：Reconciler 的内部检索器

这是一个穿插在 Phase A 和 Phase B 之间的改进。

### 现在的问题

Reconciler 调用 `list_memories(project_id, status='active')` 拿全部 active memory，再在 Python 按 topic/version_group 过滤。
当 memory 数量增长到几百条时，每次 reconcile 都扫全库是浪费。

### 改进方案

新增 `CandidateRetriever`（或者叫 `ReconcileCandidateFinder`）：

```python
class CandidateRetriever:
    def find_candidates(self, connection, memory: MemoryObject, top_k: int = 5) -> list[MemoryObject]:
        """找到与新 memory 最可能相关的旧 memory，给 reconciler 用。"""
        candidates = []

        # 1. 同 version_group 的 active memory（最强信号）
        if memory.version_group_id:
            candidates.extend(
                list_memories(connection,
                    project_id=memory.project_id,
                    version_group_id=memory.version_group_id,
                    status="active")
            )

        # 2. 同 topic + 同类型的 active memory
        if memory.topic:
            candidates.extend(
                list_memories(connection,
                    project_id=memory.project_id,
                    topic=memory.topic,
                    memory_type=memory.memory_type,
                    status="active")
            )

        # 3. 同 topic 的 primary memory（跨类型）
        if memory.topic:
            candidates.extend(
                list_memories(connection,
                    project_id=memory.project_id,
                    topic=memory.topic,
                    is_primary=True,
                    status="active")
            )

        # 去重 + 排除自身
        seen = set()
        unique = []
        for c in candidates:
            if c.memory_id != memory.memory_id and c.memory_id not in seen:
                seen.add(c.memory_id)
                unique.append(c)

        # 按相关度排序（token overlap + recency）
        return sorted(unique, key=lambda c: self._relevance(memory, c), reverse=True)[:top_k]
```

### 需要的 DB 变化

`list_memories()` 需要支持更多过滤参数（`version_group_id`, `memory_type`, `is_primary`）。
这只是加 WHERE 条件，不改 schema。

### 预期收益

- Reconciler 的候选集从"全部 active"缩减到 5-10 条
- LLM judge_relation 调用数显著减少
- 后期 memory 数量增长时不会成为瓶颈

---

## 性能控制策略

贯穿所有层的性能原则：

### 原则 1：LLM 调用集中在最值钱的节点

```
extraction   → 允许 LLM（核心价值创造）
reconcile    → 允许 LLM（关键语义判断）
consolidation → 尽量 prefilter，只对不确定的 pair 调 LLM
topic assign → heuristic 优先，LLM fallback
query plan   → heuristic 优先，LLM fallback
answer       → 允许 LLM（用户可见输出）
window split → 不用 LLM（纯规则 + token overlap）
```

### 原则 2：减少无意义的上下文传递

- 不把全部 event 传给 LLM，只传当前窗口 + bridge
- 不把全部 memory 传给 reconciler，只传精筛候选
- 不把全部 memory content 传给 extractor，只传 title

### 原则 3：批量优于逐条

- consolidation 已经是批量 pair 判断
- reconcile 目前是逐条的，暂时保持（因为每条都要写库）
- extraction 是逐窗口的，暂时保持

### 量化目标

| 指标 | 当前 | Phase A 后目标 |
|------|------|--------------|
| 7 条消息的 LLM 调用次数 | ~5-8 次 | ~3-5 次 |
| 平均窗口大小 | 2-4 条消息 | 4-8 条消息 |
| consolidation LLM pair 数 | 1-3 对 | 0-2 对（上游窗口更准 → 碎片更少） |
| reconcile 候选集大小 | 全部 active | top-5 |
