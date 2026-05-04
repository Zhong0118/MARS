# Consolidation Protocol

## 1. 文档目的

这份文档定义 MARS 中 `Consolidator` 的职责、输入输出和语义判断标准。

它的目标不是做长期状态治理，而是解决一个更前置的问题：

```text
同一批次提取出来的 memories 太碎，
哪些应该合并成一条更强的 memory，
哪些应该独立保留。
```

`Consolidator` 位于：

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

## 2. Consolidator 的边界

### Consolidator 负责

- 同批次 memory 的语义归并
- 识别 supporting fragment
- 识别 near-duplicate
- 保护高价值主记忆不被碎片淹没
- 在进入 `Reconciler` 之前减少 memory 数量

### Consolidator 不负责

- 和数据库里历史 memory 的 supersede / conflict 判断
- 长期状态迁移
- 版本号推进
- provenance 丢弃
- 检索排序

换句话说：

```text
Consolidator 处理的是 “same-batch structure”
Reconciler 处理的是 “cross-batch state”
```

## 3. 输入与输出

### 输入

一批已经经过：

- LLM extraction
- Pydantic validation
- post-processing

之后的 `MemoryObject` 列表。

这些 memory 应已经具备：

- `memory_type`
- `topic`
- `version_group_id`
- `source_event_ids`
- `confidence`
- `importance`

### 输出

一个更少但更强的 `MemoryObject` 列表。

目标是：

- 保留主记忆
- 吸收 supporting memory
- 保留 truly independent memory

## 4. Consolidation 的关系类型

本模块不复用 `Reconciler` 的 `judge_relation(new, existing)` 语义。

它应该使用更贴合“同批次归并”的关系协议。

建议保留 4 类：

### 4.1 `support`

含义：

- candidate 是 primary 的支持性补充
- 它提供背景、事实、理由、局部上下文
- 单独保存价值低于并入 primary 的价值

典型例子：

- 一个 `decision`
- 加上一条 supporting `fact`
- 加上一条解释这项 decision 的 `preference`

### 4.2 `duplicate`

含义：

- candidate 和 primary 基本在表达同一条 durable memory
- 只是换了说法、压缩程度不同、或措辞更像 supporting explanation

### 4.3 `independent`

含义：

- candidate 虽然和 primary 同 topic
- 但本身是另一条应独立保留的 durable memory

典型例子：

- 同一个 `tech_route` topic 下
- 一条是“最终决策”
- 另一条是“明确风险”
- 它们相关，但不应合并成一条

### 4.4 `unrelated`

含义：

- 表面上在一个 topic bucket 里
- 但语义上不属于同一条记忆单元

## 5. 输出协议建议

`judge_consolidation(primary, candidate)` 的建议输出：

```json
{
  "merge_decision": true,
  "relation": "support",
  "merge_role": "support",
  "reason": "The candidate only adds supporting rationale to the same decision.",
  "confidence": 0.83,
  "keep_separate_reason": null
}
```

字段含义：

- `merge_decision`
  - 是否合并
- `relation`
  - `support | duplicate | independent | unrelated`
- `merge_role`
  - 当前版本建议只需要 `support | null`
- `reason`
  - 合并或不合并的核心理由
- `confidence`
  - 模型对判断的信心
- `keep_separate_reason`
  - 当不合并时，给出一句明确理由

## 6. 合并规则建议

### 6.1 应优先合并的情况

- `decision + fact`
- `decision + preference`
- `risk + supporting fact`
- `procedure + supporting fact`
- `fact + duplicate fact`

前提是它们确实在说同一条 durable memory。

### 6.2 默认不应合并的情况

- `decision + risk`
- `decision + procedure`
- `risk + procedure`
- `decision + decision`
- `risk + risk`

除非模型有非常强的理由认为其中一个只是另一个的重述。

### 6.3 高优先级类型保护

高优先级类型建议定义为：

- `decision`
- `risk`
- `procedure`

原则：

```text
两个高优先级 memory 在同 topic 下通常保持独立，
否则很容易丢失一条真正有治理意义的 memory。
```

## 7. Consolidator 的工作顺序

建议顺序：

1. 先做硬过滤
2. 再选 primary
3. 再判断 candidate 是否并入
4. 最后保留 cluster 结果

### 7.1 硬过滤

直接不比较的情况：

- `project_id` 不同
- `version_group_id` 明显不同
- `topic` 明显不同

### 7.2 选 primary

可参考优先级：

1. `decision`
2. `risk / procedure`
3. `fact`
4. `preference`
5. `episode`

然后再综合：

- `importance`
- `confidence`
- `source_event_ids` 数量
- 时间位置

### 7.3 判断 candidate

对每个 candidate：

- 如果 `support / duplicate`：并入 primary
- 如果 `independent / unrelated`：保留独立 memory

## 8. 合并后的数据写法建议

合并不是删除 candidate 的信息，而是把它吸收到 primary 中。

建议保留：

- `source_event_ids` 取并集
- `rationale` 去重合并
- `tags` 去重合并
- 必要时把 supporting fact 压进 content

但不要把不同类别的主语义混成一坨：

- `decision` 不应被写成“decision + risk + procedure 全部平铺”的大杂烩

## 9. 当前最重要的质量目标

Consolidator 的第一目标不是“尽可能少的 memory”，而是：

```text
更合理的粒度
```

如果过度合并，会出现：

- 记忆失真
- 风险被吞掉
- 检索时只剩一个模糊大 memory

如果合并不足，会出现：

- 一条 event 一条 memory
- 搜索结果过碎
- 主记忆不突出

所以目标应是：

```text
少，但不能乱并；
强，但不能糊成一团。
```
