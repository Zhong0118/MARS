# Consolidation Cost Plan

## 1. 文档目的

这份文档回答一个现实问题：

```text
如果 consolidator 对每一对 memory 都调用一次 LLM，
成本和延迟会不会太高？
```

答案是：会。

因此需要一套成本控制策略，但不能一上来就把系统复杂化成向量检索或多阶段大编排。

## 2. 当前复杂度问题

假设同一批次提取出 `N` 条 memory。

如果做全 pair 比较：

```text
O(N²)
```

即使 `N` 不大，真实 provider 下也会带来：

- 费用增长
- 延迟增加
- 网络失败面变大
- 不稳定性增加

所以必须先做 prefilter。

## 3. 成本控制总原则

### 原则 1

先用 cheap signals 过滤掉明显不可能 merge 的 pair。

### 原则 2

只把“有可能 merge，但本地规则拿不准”的 pair 送给 LLM。

### 原则 3

优先保护高优先级 memory，不要为了减少数量而强行比较一切。

## 4. 建议的三级 prefilter

### Level 1: 硬过滤

这些 pair 直接不送 LLM：

- `project_id` 不同
- `version_group_id` 明显不同
- `topic` 明显不同

这一层的目标是：

```text
快速砍掉完全无关 pair
```

### Level 2: 类型过滤

这些组合默认保持独立，除非非常像 duplicate：

- `decision + decision`
- `risk + risk`
- `procedure + procedure`
- `decision + risk`
- `decision + procedure`
- `risk + procedure`

建议策略：

- 默认跳过
- 只有标题和内容近似度很高时，才进入下一层

### Level 3: 轻量语义线索

这些线索都很便宜，可以在本地先算：

- `source_event_ids` 是否有交集
- 标题 token overlap
- 内容 token overlap
- 时间距离是否很近
- 是否共享关键标签

建议规则：

- 如果完全没有交集、时间又远、token overlap 极低
  - 直接不送 LLM
- 如果 overlap 中等，且 topic/version_group 一致
  - 才送 LLM

## 5. 推荐的调用策略

### 方案 A：主记忆驱动比较

不是两两全比，而是：

1. 先选一个 primary
2. 其他 memory 依次和 primary 比较
3. 被保留下来的 independent memory 再成为新的 primary

优点：

- 比全 pair 更省
- 和 consolidator 的 cluster 思路一致

这也是当前结构最适合继续强化的方向。

### 方案 B：高优先级跳过

对于：

- `decision`
- `risk`
- `procedure`

之间的 pair，可以默认：

- 只有“高度相似”时才比较
- 否则直接独立保留

这能显著减少不必要的 LLM 请求。

## 6. 推荐的 cheap feature

为了支持 prefilter，建议只保留这几类低成本特征：

### 6.1 来源重叠

```text
source_event_ids overlap
```

如果 overlap 很高，通常值得比较。

### 6.2 标题/内容 token overlap

只需简单 lexical overlap，不需要 embedding。

### 6.3 时间接近度

如果两条 memory 来自同一批里时间很近，更可能是一条主 memory 加 supporting fragment。

### 6.4 类型组合

类型组合本身就是强信号：

- `decision + fact`：更值得比较
- `risk + fact`：更值得比较
- `decision + risk`：默认 less likely

## 7. 推荐的执行顺序

建议把 consolidator 的成本控制流程写成：

1. group by `project_id + version_group_id/topic`
2. 选 primary
3. 对每个 candidate 先做三级 prefilter
4. 只有通过 prefilter 的 pair 才调 `judge_consolidation`
5. merge 或保留独立

这样最终就不是：

```text
全部 pair -> 全部 LLM
```

而是：

```text
全部 pair -> 大量 cheap reject -> 少量 LLM judgement
```

## 8. 建议的观测指标

为了判断成本控制是否有效，建议后面记录：

- 每批 memory 总数
- prefilter 后进入 LLM 的 pair 数
- 最终真正 merge 的 pair 数
- 平均每批 consolidator LLM 调用数
- 被 prefilter 掉的比例

理想目标不是绝对最小，而是：

```text
在不明显伤害 merge 质量的前提下，
大幅减少 LLM pair 判断次数。
```

## 9. 当前阶段最合理的策略

短期内不建议直接做：

- embedding prefilter
- 向量数据库
- 多模型协作筛选

当前最合理的是：

- 规则 prefilter
- 小规模 LLM pair judgement

因为它：

- 易实现
- 易调试
- 更符合当前 MARS 的 MVP 状态

## 10. 最终建议

Consolidator 的成本控制目标不应是：

```text
完全不用 LLM
```

而应是：

```text
把 LLM 只用在真正有价值的 pair 上。
```

所以最合理的下一阶段方案是：

1. 先把 consolidation eval set 建起来
2. 再引入三级 prefilter
3. 再比较：
   - merge 质量是否下降
   - LLM 调用次数是否显著减少

如果 quality 几乎不掉、调用量明显下降，
这套方案就是成功的。
