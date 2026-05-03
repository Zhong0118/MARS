# MARS 压缩重设计

## 1. 现状判断

当前项目已经不是“从零开始的空壳”，但也还远没到“可交付的记忆引擎”。

现在真实成立的部分：

- `RawEvent -> MemoryObject -> Reconcile -> Search` 这条主链已经存在
- SQLite 状态层、provenance、supersede 日志基本成形
- 真实 LLM provider 已接进来，不再只是 `MockLLM`
- 查询已经从“只吐数据库记录”升级到了“有回答层”

现在最不成立的部分：

- 语义抽取质量还不稳定
- memory 粒度偏碎
- topic 命名和 topic 归并过于依赖 heuristic
- query planning 之前主要靠关键词模板
- 周边调试脚本和 phase 文档偏多，核心语义能力反而偏弱

一句话总结：

```text
工程骨架已经搭好，
但“真正像记忆系统”的那一层还不够强。
```

## 2. 当前的主要冗余

当前最大的冗余，不在数据库表，而在 `core` 层里“太多 heuristic 辅助层叠加，LLM 真正负责的事情太少”。

具体表现：

- `window_builder`、`topic_tracker`、`post_processor`、`query_planner` 都有各自的规则
- 这些规则在 MVP 早期合理，但现在已经开始互相重叠
- `inspect_*` 脚本是辅助工具，不该再继续扩成主工作流
- 很多 phase 文档描述了“做了什么”，但没有集中回答“现在什么是主路径”

所以接下来不应该继续：

- 再加新的 inspect 脚本
- 再加新的 phase 文档
- 再加新的 demo 层 wrapper

而应该开始收缩：

- 把更多“判断类工作”交还给 LLM
- 把 code 的职责收回到治理、状态、落库、过滤、去重

## 3. 压缩后的目标结构

保留这两条主链，其他一律视为辅助。

### 写入链

```text
RawEvent Ledger
-> Window Builder
-> Topic Tracker
-> LLM Extractor
-> Post Processor
-> Consolidator
-> Reconciler
-> Memory Store
```

### 查询链

```text
User Query
-> Query Planner
-> Retriever
-> Answerer
-> Final Response
```

## 4. 哪些层该保留

### 必须保留

- `connectors/sample_loader.py`
- `storage/models.py`
- `storage/db.py`
- `core/extractor.py`
- `core/reconciler.py`
- `core/retriever.py`
- `core/answerer.py`
- `llm/provider.py`

### 应保留但要继续收缩职责

- `core/window_builder.py`
- `core/topic_tracker.py`
- `core/post_processor.py`
- `core/query_planner.py`
- `core/consolidator.py`

它们还需要存在，但未来不应该越来越“规则化膨胀”，而应该越来越像：

- rule baseline
- LLM fallback
- governance boundary

## 5. 哪些层不该再继续膨胀

### 不该再投入太多时间

- `inspect_*` 系列脚本
- 过多 phase 说明文档
- 只靠关键词扩词表的 topic/query 逻辑

这些东西可以保留，但不该成为后续主要开发方向。

## 6. 下一步最该强化的 LLM 能力

后续 LLM 应该重点负责四类事情：

### 6.1 Topic 语义归类

不是只靠：

- `risk`
- `tech`
- `timeline`
- `onboarding`

这些固定词，而是允许：

- 先由规则快速命中
- 规则不稳时由 LLM 判断“这段讨论本质在说什么”

### 6.2 Query 语义规划

用户不会永远问：

- `what risks do we have`
- `what is the current tech route`

真实问题会更自然：

- “现在技术路线到底是不是还按之前那个来？”
- “如果现场挂了我们怎么兜底？”
- “新同学先应该知道哪些背景？”

所以 query planning 不能长期只靠关键词。

### 6.3 Consolidation 语义归并

当前碎片化的根本问题是：

- 小窗口
- 小 memory
- 多条 supporting fact 平铺成独立 memory

下一步要让 LLM 参与判断：

- 哪些 memory 只是 supporting fact
- 哪些 memory 应并入主 decision
- 哪些 memory 应该单独保留

### 6.4 Answer Synthesis

查询结果不能停留在“数据库记录列表”。

最终目标应该是：

- 当前结论
- 依据
- 风险
- 未确定项

这已经开始做了，但还需要从模板式进一步变成“更稳的结构化生成”。

## 7. 下一阶段不做什么

短期内不做：

- RL
- 参数化记忆训练
- test-time learning
- 复杂 multi-agent self-play
- 真正的大规模向量库

原因不是它们没价值，而是当前项目还没到那一步。

如果现在强行上这些，会掩盖真正的问题：

- 抽取质量不稳
- 归并粒度不稳
- topic/query 过于依赖 heuristic

## 8. 接下来的优先级

### P1

- LLM-assisted topic normalization
- LLM-assisted query planning

### P2

- LLM-assisted consolidation
- 更少但更强的 memory 输出

### P3

- 更稳的 answer synthesis
- 检索中的 value / freshness / usage 联合排序

### P4

- 更真实的数据集
- 再做 benchmark 调整

## 9. 当前项目的诚实评价

如果把项目拆成两个维度看：

### 工程结构

```text
7/10
```

### 记忆质量

```text
4.5/10
```

所以当前真正的问题不是“完全没做事”，而是：

```text
工程层完成得比语义层快得多。
```

接下来必须把开发重心从：

- 周边工具
- 脚本展示
- heuristic 微调

转向：

- LLM 语义判断
- 语义归并
- 高质量回答

## 10. 新窗口续接建议

如果后续上下文满了，新窗口优先喂这几份：

- `docs/COMPRESSED_REDESIGN_CN.md`
- `docs/CURRENT_STATUS.md`
- `docs/DB_SCHEMA_CN.md`

并补一句：

```text
当前主任务是继续增强 LLM 在 topic、query planning、consolidation、answer synthesis 上的作用，
减少系统对固定关键词和模板的依赖。
```
