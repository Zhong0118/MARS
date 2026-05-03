# Window Builder, Topic Tracking, and Benchmark Design

This document explains three things that are central to the next stage of MARS:

1. how discussion windows should be built from raw events
2. how topics should be tracked across fragmented conversations
3. what benchmark means in this project and why more data is required

## 1. Current State

Right now, the MVP has:
- `RawEvent` ingestion
- deterministic `MockLLM` extraction
- keyword retrieval
- reconciliation and supersede handling

What it does **not** yet truly solve:
- long chat segmentation
- topic drift inside one chat
- fragmented topic re-entry such as `A -> B -> A -> C -> B`
- realistic extraction quality evaluation

That is why `window_builder` and `topic_tracker` are needed.

## 2. How Semantic Recognition Works Right Now

Current semantic recognition is limited.

In the present `MockLLM`:
- extraction is based on deterministic pattern matching
- relation judgment is based on deterministic pattern matching

This means:
- the pipeline is real
- the database writes are real
- the state transitions are real
- the semantic understanding is simulated

So the current MVP proves system plumbing, not production-quality semantics.

## 3. Are Topic Markers Hard-coded?

In the new MVP scaffolding, topic markers are **default-configured**, not
permanently hard-coded.

That means:
- there is a default marker dictionary
- it can be overridden through config
- later it can be replaced by a learned or LLM-assisted mechanism

Current examples:
- `tech_route`
- `timeline`
- `risk`
- `reporting`

These markers are useful for MVP heuristics, but they are not meant to be the
final topic engine.

## 4. Window Builder: Why It Exists

`window_builder` is the layer that answers:

> Which raw events should be considered together before memory extraction?

This cannot rely on only one signal.

### It should not be only time-based

Because a chat can look like:

```text
7:00 A
8:00 B
8:02 A
next day C
third day B
```

Pure time slicing will either:
- split one topic too much
- or merge different topics incorrectly

### It should not be only chat-based

Because one Feishu group can discuss many unrelated topics.

### It should not be only keyword-based

Because:
- synonyms exist
- people resume topics implicitly
- some transitions are pragmatic rather than lexical

## 5. MVP Window Builder Strategy

The current design uses a heuristic-first strategy.

### Signals used for splitting

- chat boundary
- thread boundary
- large time gap
- explicit shift markers such as:
  - `另外`
  - `回到`
  - `说回`
  - `correction:`
- maximum message cap per candidate window
- coarse topic-marker shifts

### Why this is acceptable for MVP

It does not solve full discourse segmentation.

It does:
- keep the logic inspectable
- reduce obviously bad merges
- create candidate windows for later LLM extraction

## 6. Topic Tracker: Why It Exists

`topic_tracker` answers:

> After windows are built, what topic should each window belong to?

This matters because real collaboration history is not linear.

A topic may:
- pause
- resume later
- jump across chats
- appear in multiple revisions

The tracker is not yet a full online topic model.
It is a bridge between raw windows and later memory governance.

## 7. MVP Topic Tracker Strategy

The current design is also heuristic-first.

### Assignment signals

1. topic markers
2. window-level `topic_hint`
3. lexical overlap with previously assigned topics
4. fallback creation of a new topic label

### Why this matters

It gives the system a coarse way to say:

```text
this window is probably about tech_route
this window is probably about reporting
this looks like a new topic
```

This is enough to:
- support future windowed extraction
- improve reconcile candidate selection
- reduce cross-topic contamination

## 8. Should We Implement All Possible Directions?

No. We should not implement three competing systems in parallel right now.

The right approach is layered:

### Layer 1: heuristic baseline

Use:
- window heuristics
- topic markers
- lexical overlap

### Layer 2: real LLM enhancement

Later use LLM for:
- deciding whether a window is coherent
- splitting or merging borderline windows
- assigning higher-quality topic labels

### Layer 3: future embedding/hybrid retrieval

Later use:
- vector similarity
- hybrid recall
- topic memory linkage

So the answer is:

```text
do not choose one forever
do not implement everything at once
start with heuristics, then layer in LLM, then layer in embeddings
```

## 9. When Should Real LLM Be Used?

Now that the core pipeline is already working, the right next step is:

- keep `MockLLM` for deterministic local testing
- add a real provider alongside it

The real LLM should first be used for:

1. memory extraction from windows
2. relation judgment for reconciliation
3. optionally topic assignment refinement

The recommended architecture is:

```text
provider = mock | real
```

So the same extractor/reconciler can run either:
- deterministic local mode
- real semantic mode

## 10. What Does Benchmark Mean Here?

Benchmark does **not** mean measuring CPU performance only.

It means evaluating whether the memory system is actually useful.

In MARS, benchmark has three main categories:

### 10.1 Anti-noise benchmark

Question:
- after many irrelevant messages, can the system still retrieve the correct memory?

Metrics:
- Recall@1
- Recall@3
- Source Accuracy

### 10.2 Conflict benchmark

Question:
- when a new statement contradicts or replaces an old one, can the system update correctly?

Metrics:
- Conflict Detection Accuracy
- Supersede Accuracy
- Status Accuracy

### 10.3 Efficiency benchmark

Question:
- does MARS reduce the time and steps needed to recover project memory?

Metrics:
- Time Reduction
- Step Reduction
- Input Character Reduction

## 11. Why the Current Data Is Not Enough

Your intuition is right: the current bundled sample data is too small and too
simple to prove real semantic robustness.

Right now it only proves:
- the architecture works
- state changes work
- retrieval works on a toy case

It does **not** yet prove:
- topic drift handling
- mixed-topic long-chat segmentation
- realistic conflict ambiguity
- retrieval under substantial noise

That is why benchmark design must include more sample data.

## 12. What Extra Data Is Needed

At minimum, the benchmark set should expand in three directions.

### 12.1 Long mixed-topic chat

Need samples where:
- topics alternate
- old topics return later
- one chat contains several project concerns

Example:
- technical route
- deployment issue
- weekly report
- technical route again

### 12.2 Ambiguous update cases

Need samples where:
- a new statement is not clearly supersede vs support vs conflict
- relation judgment is genuinely nontrivial

### 12.3 Noise-heavy retrieval cases

Need samples where:
- one key memory is surrounded by many unrelated messages
- the memory must still be found reliably

## 13. Recommended Next Implementation Order

The recommended next order is:

1. integrate `window_builder` into extraction flow
2. integrate `topic_tracker` into window labeling and reconcile candidate filtering
3. add real LLM provider support
4. expand benchmark datasets
5. implement `run_benchmark.py`

## 14. What the New Modules Mean

### `app/core/window_builder.py`

Purpose:
- split raw event streams into candidate discussion windows

### `app/core/topic_tracker.py`

Purpose:
- assign a coarse topic to each candidate window

These modules do not solve the whole problem yet.
They create the structure that later real LLM and benchmark work will rely on.

## 15. Final Mental Model

Use this summary:

```text
Window Builder:
code proposes candidate chunks

Topic Tracker:
code proposes coarse topical continuity

LLM:
decides semantic meaning inside or across those chunks

Benchmark:
proves whether the whole memory system is actually useful
```
