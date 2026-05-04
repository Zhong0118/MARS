# Consolidation Eval Set

## 1. 文档目的

这份文档定义一组专门用于评估 `Consolidator` 的最小样例。

它不直接测：

- 数据库写入
- 检索排序
- benchmark 全链路

它专门测：

```text
两条或几条 extracted memories
到底该不该合并
```

## 2. 评测原则

每个 case 尽量满足：

- 只聚焦一个 consolidation 问题
- 输入 memory 数量少
- 人工预期明确

评测时最关心的是：

- `merge_decision` 对不对
- `relation` 对不对
- 是否过度 merge
- 是否漏掉明显应该 merge 的 supporting memory

## 3. 核心 case 类型

### Case 1: decision + supporting fact

输入：

- `decision`: “Phase one uses Streamlit for faster demo delivery.”
- `fact`: “Current data processing code is Python-based.”

预期：

- `fact` 合并进 `decision`
- `relation = support`

原因：

- 第二条不是独立主记忆，更像 supporting basis

### Case 2: decision + preference

输入：

- `decision`: “Use Streamlit for the first demo.”
- `preference`: “Zhang San prefers Streamlit because it is faster.”

预期：

- `preference` 合并进 `decision`
- `relation = support`

### Case 3: decision + risk

输入：

- `decision`: “Use Streamlit for the first demo.”
- `risk`: “Deployment may fail on demo day due to unstable school network.”

预期：

- 不合并
- `relation = independent`

原因：

- 两条都属于 durable memory，且治理意义不同

### Case 4: decision + procedure

输入：

- `decision`: “Use Streamlit for the first demo.”
- `procedure`: “If school network fails, switch to local package fallback.”

预期：

- 默认不合并
- `relation = independent`

原因：

- procedure 是可执行 fallback，不应吞到 decision 里

### Case 5: risk + supporting fact

输入：

- `risk`: “There is a high deployment risk on demo day.”
- `fact`: “The school network has been unstable for three days.”

预期：

- `fact` 合并进 `risk`
- `relation = support`

### Case 6: fact + duplicate fact

输入：

- `fact A`: “Current pipeline uses Python and pandas.”
- `fact B`: “The existing data cleaning pipeline is implemented in Python with pandas.”

预期：

- 合并
- `relation = duplicate`

### Case 7: same topic, different sub-memory

输入：

- `fact`: “Teacher review moved to next Friday.”
- `fact`: “Frontend skeleton is already ready.”

topic 都可能被归到同一个 broad project topic

预期：

- 不合并
- `relation = independent` 或 `unrelated`

原因：

- 它们不是同一条 memory

### Case 8: decision + duplicate decision

输入：

- `decision A`: “Phase one should use Vue + FastAPI.”
- `decision B`: “Use Vue frontend and FastAPI backend for phase one.”

预期：

- 允许合并
- 但只在模型强信心判断其为重复时
- `relation = duplicate`

### Case 9: risk + risk

输入：

- `risk A`: “Network instability may break deployment.”
- `risk B`: “Live demo could fail due to Wi-Fi outage.”

预期：

- 默认独立，除非模型非常确定二者只是表述重复

原因：

- risk 很容易在 broad topic 下被误合并

### Case 10: preference + preference

输入：

- `preference A`: “PM prefers a faster demo route.”
- `preference B`: “Teacher prefers a more engineered frontend.”

预期：

- 大概率不合并

原因：

- 它们代表不同立场，不该被抹平

## 4. 进阶 case

### Case 11: one primary + two supporting

输入：

- `decision`
- `fact`
- `preference`

预期：

- `fact` 和 `preference` 都并入 `decision`
- 最终只保留 1 条主 memory

### Case 12: one primary + one supporting + one independent

输入：

- `decision`
- `fact` supporting 它
- `risk` 独立

预期：

- `fact` 并入 `decision`
- `risk` 单独保留

最终保留 2 条

## 5. 建议的评测记录格式

每个 case 建议至少记录：

- `case_id`
- `input_memories`
- `expected_merge_pairs`
- `expected_separate_pairs`
- `expected_cluster_count`

例如：

```json
{
  "case_id": "cons_case_01",
  "description": "decision + supporting fact",
  "input_memories": [
    {"memory_type": "decision", "topic": "tech_route", "title": "..."},
    {"memory_type": "fact", "topic": "tech_route", "title": "..."}
  ],
  "expected_merge_pairs": [["m1", "m2"]],
  "expected_separate_pairs": [],
  "expected_cluster_count": 1
}
```

## 6. 建议的核心指标

### 6.1 `merge_precision`

系统判定 merge 的 pair 里，有多少是真的该 merge。

### 6.2 `merge_recall`

真正应该 merge 的 pair 里，有多少被系统 merge 到了。

### 6.3 `over_merge_rate`

不该 merge 却被 merge 的比例。

### 6.4 `under_merge_rate`

该 merge 却没 merge 的比例。

### 6.5 `cluster_count_accuracy`

最终保留的 memory 数量是否符合预期。

## 7. 使用建议

这套 eval set 建议先于：

- mixed topic benchmark
- full run_extract benchmark

原因很简单：

```text
先把 consolidation 判断测清楚，
再去测完整写入链，
问题定位会清楚得多。
```
