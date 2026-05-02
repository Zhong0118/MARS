我已经把 `run_extract.py` 的摘要补上 `content` 了。现在跑完会直接看到提取出的正文内容。

下面我把你现在这套系统，从“当前怎么跑”到“后面每个 phase 做什么”系统讲清楚。

**1. `--ingest-only` 到底是怎么生效的**

你看到这行：

```python
parser.add_argument("--ingest-only", action="store_true", help="Only persist raw events, skip memory extraction.")
```

`action="store_true"` 的意思是：

- 你**不写** `--ingest-only`  
  那么 `args.ingest_only == False`
- 你**写了** `--ingest-only`  
  那么 `args.ingest_only == True`

它真正体现在 [run_extract.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/scripts/run_extract.py) 里的这段判断：

```python
if args.ingest_only:
    print(f"Ingested {len(events)} raw events from {args.input}")
    return
```

意思就是：

- 如果你带了 `--ingest-only`
  - 程序只会：
    - 读 JSON
    - 转成 `RawEvent`
    - 写入 `raw_events`
    - 同步 tenant/user/chat/project 这些上下文表
  - 然后**提前 return**
  - 不会继续走 extractor
  - 不会写 `memory_objects`
  - 不会写 `memory_sources`

所以：

```powershell
python scripts/run_extract.py --input xxx.json --ingest-only
```

只做 Phase 2 的 ingestion。

而：

```powershell
python scripts/run_extract.py --input xxx.json
```

会继续往下做 Phase 3 的 extraction。

**2. 目前完整的文件调用流程是什么**

你现在可以把流程记成下面这条线：

```text
scripts/run_extract.py
    ->
app/connectors/sample_loader.py
    ->
app/storage/models.py 中的 RawEvent
    ->
app/storage/db.py 写 raw_events
    ->
app/core/extractor.py
    ->
app/llm/provider.py 的 MockLLM
    ->
app/storage/models.py 中的 MemoryObject
    ->
app/storage/db.py 写 memory_objects + memory_sources
```

更细一点讲：

**第一步：入口脚本**
- [run_extract.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/scripts/run_extract.py)
- 作用：
  - 解析命令行参数
  - 初始化数据库
  - 调 loader
  - 决定是“只入 raw events”还是“继续提取 memory”

**第二步：样例数据读取**
- [sample_loader.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/connectors/sample_loader.py)
- 作用：
  - 读取 `data/sample_chats/*.json`
  - 每条 message 转成 `RawEvent`

**第三步：原始事件入库**
- [db.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/storage/db.py)
- 用到：
  - `insert_raw_events(...)`
- 写入表：
  - `raw_events`

**第四步：同步轻量上下文实体**
- 还是 [run_extract.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/scripts/run_extract.py) 里的 `sync_context_entities(...)`
- 写入表：
  - `tenants`
  - `users`
  - `chats`
  - `projects`
  - `project_chats`
  - `chat_memberships`

**第五步：记忆提取**
- [extractor.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/core/extractor.py)
- 作用：
  - 收到一批 `RawEvent`
  - 调用 provider
  - 拿到候选 memory
  - 用 Pydantic 校验成 `MemoryObject`

**第六步：MockLLM 给出结构化候选**
- [provider.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/llm/provider.py)
- 作用：
  - 现在不是调真模型
  - 而是根据样例文本内容，稳定返回一段结构化 JSON 候选

**第七步：结构化记忆入库**
- [run_extract.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/scripts/run_extract.py) 里的 `persist_extracted_memories(...)`
- 调用 [db.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/storage/db.py)：
  - `insert_memory_object(...)`
  - `insert_memory_sources(...)`
- 写入表：
  - `memory_objects`
  - `memory_sources`

**3. 现在每张关键表在当前阶段存什么**

当前最重要的是这几张：

- `raw_events`
  - 存每一条原始聊天消息
  - 一条 message -> 一条 `RawEvent`

- `memory_objects`
  - 存提取出的结构化记忆
  - 比如：
    - `Phase One Demo Uses Streamlit`
    - `status = active`
    - `topic = tech_route`

- `memory_sources`
  - 存 memory 和原始 event 的关联
  - 比如这条 decision memory 关联了 4 条 message

- `retrieval_logs`
  - 你运行 `search_memory.py` 时会写
  - 记录 query、project、召回了哪些 memory、延迟等

- `policy_actions`
  - 目前 schema 已有，但真正会大量开始写是在后面 reconciliation / push 阶段

- `memory_edges`
  - 目前 schema 已有
  - 真正会开始写是在 supersede / conflict 阶段

**4. 当前 `search_memory.py` 的流程是什么**

现在检索这条线是：

```text
scripts/search_memory.py
    ->
app/core/retriever.py
    ->
app/storage/db.py 读取 memory_objects
    ->
关键词打分
    ->
生成 EvidencePack
    ->
写 retrieval_logs
    ->
终端打印结果
```

所以你现在看到的输出：

```text
[1] Phase One Demo Uses Streamlit
...
source_event_ids: evt_msg_001 ...
```

其实已经不是原始聊天，而是：
- 从 `memory_objects` 里取出的结构化 memory
- 再通过 `memory_sources` 找回来的 provenance

**5. 后续 phase 分别做什么**

你现在已经大致走到了：

- Phase 2：RawEvent ingestion
- Phase 3：MockLLM extraction
- Phase 4：Keyword retrieval

后面核心阶段是这些：

**Phase 5: Reconciliation and Supersede**
- 目标：
  - 处理“新记忆是否覆盖旧记忆”
- 典型场景：
  - 原来是 Streamlit
  - 后来老师明确改成 Vue + FastAPI
- 会写的表：
  - `memory_objects`
    - 旧 memory -> `superseded`
    - 新 memory -> `active`
  - `memory_edges`
    - 写 `supersedes`
  - `policy_actions`
    - 记录这次为什么判断成 supersede

这是“验证版本治理和冲突处理”的关键阶段。

**Phase 6: FastAPI Routes**
- 目标：
  - 把现在这些 CLI 能力暴露成 HTTP API
- 会有：
  - `/api/ingest/messages`
  - `/api/memory/extract`
  - `/api/memory/search`
  - `/api/memory/reconcile`
  - `/health`

这是“验证服务化调用”的阶段。

**Phase 7: Benchmark**
- 目标：
  - 证明系统不只是能跑，还真的有用
- 主要验证：
  - anti-noise
  - conflict
  - efficiency
- 会用：
  - `benchmark_results`
  - `reports/benchmark_report.md`
  - `reports/benchmark_results.csv`

这是“验证效果”的阶段。

**Phase 8: Vector Store Placeholder**
- 目标：
  - 给以后向量检索留接口
- 现在不会做真实大规模 embedding 系统
- 更像是“为后续 semantic retrieval 做接口准备”

**Phase 9: OpenClaw / Feishu Adapter Placeholder**
- 目标：
  - 增加适配器占位
- 让系统未来能接：
  - OpenClaw payload
  - Feishu event payload

这是“验证多入口接入边界”的阶段。

**Phase 10: Optional Onboarding Pack**
- 目标：
  - 基于现有 memories 生成新人 onboarding 包

**6. 真正的 LLM 在哪个 phase 接进来**

严格按你这份本地 MVP 计划，**Phase 3 本来就是 LLM boundary 出现的地方**。

只是现在我们用的是：
- `MockLLM`

后面真正变成真实 LLM API，不一定非要等某个全新 phase，可以理解成：

- Phase 3 当前版本：`MockLLM`
- Phase 3 后续增强版：真实 LLM provider

也就是说，**真 LLM 其实就是在 Phase 3 这层替换 provider**。

不会改动大的主干，只是把：

```text
MemoryExtractor -> MockLLM
```

替换成：

```text
MemoryExtractor -> Real LLM Provider
```

比如：
- OpenAI
- Qwen
- DeepSeek
- 兼容 OpenAI API 的服务

所以真 LLM 的落点是：
- [provider.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/llm/provider.py)

而不是去改 `run_extract.py`、`db.py` 或 `search_memory.py` 这些主干。

**7. 哪些 phase 是“验证其他相关内容”的**

你问“后面的 phase 哪里是验证其他相关内容的”，可以这样看：

- Phase 2
  - 验证 ingestion 能不能稳定落原始事件

- Phase 3
  - 验证 extraction schema 和结构化记忆链路

- Phase 4
  - 验证 retrieval 是否能把记忆查出来，并带来源

- Phase 5
  - 验证 conflict / supersede / version governance

- Phase 6
  - 验证 API 服务化能力

- Phase 7
  - 验证系统效果是否真的有价值
  - 这是“效果证明阶段”

- Phase 8
  - 验证以后能否平滑扩展 semantic retrieval

- Phase 9
  - 验证接 OpenClaw / Feishu 的边界是否干净

- Phase 10
  - 验证 memory 能不能转化成更高层应用价值，比如 onboarding

**8. 为什么现在先用 MockLLM，而不是立刻真 LLM**

因为现在这一步先要验证的是：

```text
RawEvent -> MemoryObject -> Retrieval -> Reconciliation
```

这条“系统骨架”对不对。

如果太早接真 LLM，你会同时遇到：
- prompt 不稳定
- JSON 输出不稳定
- API key / 网络 / 费用问题
- 难以判断是系统逻辑错了还是模型输出波动

所以 MockLLM 的意义是：
- 先把系统 plumbing 跑通
- 先让 schema、表、helper、脚本稳定
- 之后再把 provider 换成真实 LLM

这是工程上很正常的做法。

**9. 你现在最应该怎么理解“当前阶段”**

你现在不是在“做最终产品”，而是在搭一个非常清晰的闭环：

```text
Phase 2: 原始消息进来
Phase 3: 提炼成结构化记忆
Phase 4: 把记忆查出来
Phase 5: 处理新旧记忆冲突
Phase 6: 对外提供 API
Phase 7: 证明系统有效
```

只要这个闭环跑通，后面接真 LLM、接 Feishu、接服务器，都是沿着现有边界扩展。

**10. 我建议你下一步怎么走**

如果你现在要继续写代码，我建议顺序是：

1. 继续做 `Phase 5`
   把 `conflict_update.json` 跑通
   这是最关键的“记忆治理”阶段

2. 再决定是否把 `provider.py` 改造成：
   - `MockLLM`
   - `RealLLMProvider`
   - 通过配置切换

也就是说，我建议先把 supersede 做完，再接真 LLM。因为这样你先把“系统逻辑”稳定住，再换“语义引擎”。

如果你愿意，我下一步可以直接继续帮你写 `Phase 5`，把：
- 旧记忆改成 `superseded`
- 新记忆写成 `active`
- 插入 `memory_edges`
- 插入 `policy_actions`
- 然后让 `search_memory.py` 查“当前技术路线”时返回新的 active memory