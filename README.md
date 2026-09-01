# PharmaAssistant

A multi-tenant skincare/pharmacy product-recommendation chatbot: retrieval over a per-tenant product catalog, generation grounded strictly in the retrieved products, with per-tenant API keys, quotas, and observability.

## Problem

A pharmacy/skincare store wants a chat widget that recommends products from *its own* catalog — not a generic "AI skincare advisor" that might invent a product the store doesn't sell. Each store (tenant) has its own catalog, prompts, and pricing; a customer's question ("something for oily skin under €30") needs to be answered from real inventory, with a graceful "we don't sell that" when it's genuinely out of catalog.

## Architecture

👉 [Architecture documentation](docs/architecture.md) has the full component diagram, data flows, and contracts.

What's real today: `FastAPI` API (`service/main.py`) → per-tenant API-key auth + daily quota → `PharmaAssistant` core (`app/pharma_assistant.py`): metadata prefilter (price/category, deterministic regex parsing) + semantic ranking over OpenAI embeddings → OpenAI chat generation constrained to the retrieved product cards only.

## Stack

- **API**: FastAPI + uvicorn
- **Retrieval**: OpenAI embeddings (`text-embedding-3-large` by default) + FAISS (numpy fallback if FAISS isn't available), cosine similarity, with a deterministic metadata prefilter (price range, category) ahead of the semantic ranking
- **Generation**: OpenAI chat (`gpt-4o-mini` by default), prompted to only recommend from the product cards it was given
- **Multi-tenant**: per-tenant catalog/prompts/config (`data/clients/<id>/`, `profiles/clients/<id>.yaml`), per-tenant API key + daily quota (`service/tenants.yaml`)
- **Observability**: JSON access logs, Prometheus metrics (`/metrics`)
- **Tests**: pytest, 84+ tests (unit + integration), all mocking OpenAI — see [Evaluation](#evaluation) for the real-API numbers

## How to run it

```bash
cp .env.example .env
# edit .env: set OPENAI_API_KEY

docker compose up --build -d
curl -s http://localhost:8080/healthz | jq .
```

**Honest gap, not glossed over:** `docker-compose.yml` preloads `client_1`/`client_2` (`PRELOAD_TENANTS`), and those are the only tenants in `service/tenants.yaml` — but neither has a catalog/profile on disk. The only tenant with a real, working catalog is `farmacia_carmen_sanjuan`, which isn't registered in `tenants.yaml`. So `/healthz` passes out of the box, but a real `/greet`/`/answer` call needs one of these first:

```bash
# Option A: add farmacia_carmen_sanjuan to service/tenants.yaml with an api_key, then:
curl -s "http://localhost:8080/greet?client_id=farmacia_carmen_sanjuan" -H "x-api-key: <the key you set>" | jq .

# Option B: follow docs/getting-started.md to build out client_1's catalog/profile from scratch
```

This is tracked as the top item in [Known limitations](#known-limitations) — it's a real gap found in this repo, not left implicit.

Run tests: `make test` (or `pytest -q`). Run the real eval (costs a few cents in OpenAI credits): `poetry run eval-runner`.

## Key decisions

- **Metadata prefilter before semantic search, not semantic search alone.** Price and category constraints are parsed deterministically (regex, `app/price_parser.py`/`app/pattern_loader.py`) and applied *before* the embedding-based ranking. A query like "vitamin C serum under €30" first narrows candidates by price, then ranks semantically within them — cheaper, faster, and doesn't rely on the embedding model understanding numeric constraints.
- **Generation is constrained to retrieved product cards, not the whole catalog.** The compose prompt (`data/prompts/compose_prompt.txt`) is given only the top-k retrieved cards as JSON and instructed never to invent products outside them — see [Evaluation](#evaluation) for how well that held up in a real, measured run.
- **Per-tenant everything, file-based, no database.** Catalogs, prompts, patterns, and index caches are all per-tenant files/directories (`data/clients/<id>/`, `storage/<id>/`) rather than a shared DB with tenant_id columns. Simpler to reason about for a small number of tenants, and makes cross-tenant leaks easy to test for directly at the filesystem layer (see the bug story below).
- **`gpt-4o-mini` / `text-embedding-3-large`.** Cheap tier, appropriate for a portfolio project evaluated on a handful of queries, not a cost-at-scale decision.

## A bug I found and fixed: the core feature was broken in the only environment that matters

72+ tests passing in CI on every PR gave a false sense of security. I didn't trust that and tried to actually run the thing end-to-end.

**What I assumed:** `/greet` and `/answer` — the actual product — worked, since the whole test suite was green and had been for months.

**What I found:** `get_assistant_for()` (the function that loads a tenant's real config off disk) called `resolve_config_namespace(..., repo_root=Path("../../service"))`. That path doesn't correspond to anything real in either environment the app actually runs in — Docker (`WORKDIR /app`, with `data/`/`profiles/` copied there) or local (`uvicorn` run from the repo root, per the docs). In both cases it resolved outside the project entirely, so loading any tenant's catalog raised `FileNotFoundError` — uncaught, so the client got a raw `500`. **Every real `/greet` and `/answer` call, for every tenant, in every real environment, always failed.**

**Why it had gone unnoticed:** every single test that exercises these endpoints stubs `get_assistant_for()` out entirely (`monkeypatch.setattr(svc, "get_assistant_for", ...)`) so tests don't need a real OpenAI key. That's the right call for keeping tests fast and free — but it meant the one function that wires a real tenant to real data was never exercised by anything, ever.

**The fix:** `repo_root=Path(".")`, matching the deployment convention the Dockerfile already established. Added a regression test that calls the *real* `get_assistant_for()` (only `PharmaAssistant` itself is stubbed, so no OpenAI call happens) against the real `farmacia_carmen_sanjuan` tenant, and asserts the resolved catalog path actually exists on disk. Verified it fails against the old code and passes against the fix.

## Evaluation

A real, hand-labeled eval run against the live OpenAI API and the one real product catalog (`farmacia_carmen_sanjuan`, 30 products) — not a mocked or simulated run.

**Dataset**: 9 cases (`src/scripts/eval_fixtures.py`), each hand-written and justified directly by the catalog's own product copy (not guessed) — 8 with a known-correct expected product, 1 deliberately out-of-catalog (hair care; the store only sells skincare).

**Latest run** (`farmacia_carmen_sanjuan`, top_k=6, n=9):

| Metric | Value |
|---|---|
| Retrieval recall (8 scored cases) | 1.00 |
| Retrieval precision@6 | 0.167 (expected — see note below) |
| Out-of-catalog correctly rejected | 0 / 1 |
| Possible hallucinations flagged | 0 / 9 |
| Latency p50 / p95 — retrieve | 250ms / 276ms |
| Latency p50 / p95 — answer (full generation) | 3.4s / 5.2s |
| Tokens (embedding / chat prompt / chat completion) | 264 / 7,868 / 2,416 |
| Estimated cost, full run | ~$0.003 |

*Precision@6 note: every case in this set has exactly one known-correct product, so 1/6 is the maximum precision@6 achievable given the ground truth's own design — not a retrieval quality problem. A larger eval set with multiple acceptable products per query would make this metric more informative.*

Re-run it yourself: `poetry run eval-runner` (writes a full JSON report to `.eval_artifacts/`, gitignored).

### What the eval caught

- **Groundedness held up**: 0/9 cases had a product mentioned in the generated answer that wasn't actually retrieved — the "only recommend from what you were given" instruction worked in this run.
- **Relevance didn't, for the out-of-catalog case.** Asked "Do you sell hair dye or shampoo?", the assistant correctly said in text that it doesn't — then recommended 6 unrelated skincare products anyway, because `retrieve()` has no relevance/similarity-score threshold; it always returns the top-k by similarity, even when none of them are actually relevant. This is *not* a hallucination (every product mentioned was real and genuinely retrieved) — it's a distinct retrieval-relevance gap. See [Known limitations](#known-limitations).
- **A real cost bug**: instrumenting token usage for this eval surfaced that `greet()`/`answer()` each called the chat API twice per request, discarding the first response — doubling real cost and latency on every call since the code was written. Fixed as part of building this eval (see commit history).

## Known limitations

- **`tenants.yaml` doesn't match the only real tenant.** `client_1`/`client_2` (the only entries in `service/tenants.yaml`, and what `docker-compose.yml` preloads) have no catalog/profile on disk. `farmacia_carmen_sanjuan` (the only tenant with real data) isn't registered for auth. See [How to run it](#how-to-run-it) for the workaround; not yet fixed.
- **No relevance threshold in retrieval.** `retrieve()` always returns the top-k candidates by similarity, even for genuinely out-of-catalog questions — see [Evaluation](#evaluation). Fixing this is a retrieval-logic change (a minimum similarity score, or a separate in-domain classifier), intentionally not done yet.
- **The offline `build_index.py` tool and the live app use incompatible index-cache formats.** `src/scripts/build_index.py` has a real deterministic hash-based embedding fallback (`--backend hash`, no OpenAI key needed) — but it writes a `meta.json` without the `signature` field `app/index_cache.py` requires, so the live `PharmaAssistant` class never recognizes a cache built this way and always falls through to real OpenAI calls. The two were never wired together.
- **No cross-tenant catalog test against the live class** — the [cross-tenant isolation tests](tests/integatrion/test_cross_tenant_isolation.py) verify auth, quota, and config-path resolution don't leak between tenants, all without needing OpenAI; there's no equivalent test using two real, fully-built `PharmaAssistant` instances (that would need two real catalogs' worth of embedding calls per test run).
- **9-case eval is a smoke test, not a benchmark.** Useful to catch regressions and characterize real behavior (as it did above), not to claim a statistically robust quality number.
- **No deployed/hosted demo.** A public endpoint backed by real OpenAI calls is a real cost/abuse surface for a portfolio project; verified instead via a real eval run against the live API (above) and `docker compose up` for `/healthz`.

## What's next

- Register `farmacia_carmen_sanjuan` in `service/tenants.yaml` (or build out `client_1` per `docs/getting-started.md`) so the docker-compose demo works end-to-end without a manual step.
- Add a minimum-similarity threshold to `retrieve()` so genuinely out-of-catalog questions return no products instead of the nearest-but-irrelevant ones.
- Reconcile `build_index.py`'s hash-backend cache format with `app/index_cache.py` so a pre-built index actually gets used (real latency/cost win for cold starts).
- Grow the eval set past a 9-case smoke test, with multiple acceptable products per query so precision@k becomes informative.

## License

[MIT](LICENSE)
