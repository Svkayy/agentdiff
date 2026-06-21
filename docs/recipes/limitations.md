# Limitations and Workarounds

AgentDiff's Tracer model still works best when each sample has a clean **start
and end** — one bounded slice of behavior. Several previously-missing pieces are
now covered locally: async runners, quickstart scaffolding, aiohttp/gRPC capture
shims, framework enrichment adapters, streaming chunk timelines, SQLite run
artifacts, local worker concurrency, traffic-derived test cases, and local
dashboard/monitor commands.

The remaining limitations are product/platform boundaries rather than small
library gaps.

## 1. Continuous / background monitoring agents

Alert routers, fraud watchers, log-triage bots, real-time moderation — anything
with no per-invocation boundary. `agentdiff monitor --run-compare` can run local
checks on an interval, but AgentDiff does not yet attach to production traffic as
a continuous ingestion service.

**Workaround:** scope your Runner to one synthetic event at a time. Seed the
agent's state, emit a single item, settle, snapshot, and treat that as one
sample (Recipe B).

## 2. Long-running workflows that pause for external events or human input

Multi-day onboarding, approval flows that wait hours, scheduled retries. Real
workflow checkpointing and replay is v2+.

**Workaround:** test each synchronous segment between pauses as its own test
case, seeding the pre-pause state as preconditions.

## 3. Distributed or shared-state load testing

`agentdiff compare --workers N` runs local concurrent samples. It is useful for
stress testing runners and capture paths, but it is not a distributed load
generator and it does not isolate or reset shared mutable state for you.

**Workaround:** keep the default sequential mode for correctness gates. Use
`--workers` only when your Runner and dependencies are safe to call
concurrently, and reset shared state between invocations.

---

## Still not first-class

- Hosted dashboard accounts, auth, organizations, and cloud run storage.
- Production traffic mirroring without a Runner or exported traffic sample.
- Durable workflow checkpoint/replay for multi-day agent executions.
- Full provider-native streaming timelines for every SDK shape; HTTP stream
  bodies are reconstructed when captured.
- Full semantic adapters for every framework feature. LangGraph, CrewAI,
  AutoGen, and LlamaIndex now emit first-class framework events, but each
  library's advanced callback surfaces can still be deepened over time.
