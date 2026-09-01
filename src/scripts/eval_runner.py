#!/usr/bin/env python3
"""
Real evaluation run for PharmaAssistant against the `farmacia_carmen_sanjuan`
demo tenant -- the only tenant with a real product catalog today.

Unlike the pytest suite (which stubs PharmaAssistant everywhere to stay free
and fast), this script builds a real PharmaAssistant and makes real OpenAI
calls (embeddings + chat) for every case in eval_fixtures.py. It requires
OPENAI_API_KEY and has a small real cost -- see the printed token totals.

Usage:
    poetry run python -m scripts.eval_runner
    poetry run python -m scripts.eval_runner --top-k 6 --out-dir .eval_artifacts
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.pharma_assistant import PharmaAssistant, Settings
from app.profile_resolver import resolve_config_namespace
from scripts.eval_fixtures import CASES, TENANT_ID, EvalCase

REPO_ROOT = Path(__file__).resolve().parents[2]

# Estimated USD per 1M tokens, as published at time of writing (text-embedding-3-small,
# gpt-4o-mini). These drift over time -- treat the resulting $ figure as a rough order
# of magnitude, not an exact bill; the token counts themselves are the real measurement.
PRICE_PER_1M_TOKENS = {
    "embedding": 0.02,
    "chat_prompt": 0.15,
    "chat_completion": 0.60,
}


@dataclass
class UsageTotals:
    embedding_tokens: int = 0
    chat_prompt_tokens: int = 0
    chat_completion_tokens: int = 0

    def estimated_cost_usd(self) -> float:
        return (
            self.embedding_tokens / 1_000_000 * PRICE_PER_1M_TOKENS["embedding"]
            + self.chat_prompt_tokens / 1_000_000 * PRICE_PER_1M_TOKENS["chat_prompt"]
            + self.chat_completion_tokens / 1_000_000 * PRICE_PER_1M_TOKENS["chat_completion"]
        )


def _instrument_client(client: Any, totals: UsageTotals) -> None:
    """
    Wrap embeddings/chat calls on this one client *instance* to record real
    token usage for cost reporting, without touching app/pharma_assistant.py.
    """
    orig_embed = client.embeddings.create
    orig_chat = client.chat.completions.create

    def embed_wrapper(*args: Any, **kwargs: Any) -> Any:
        resp = orig_embed(*args, **kwargs)
        if getattr(resp, "usage", None):
            totals.embedding_tokens += resp.usage.total_tokens
        return resp

    def chat_wrapper(*args: Any, **kwargs: Any) -> Any:
        resp = orig_chat(*args, **kwargs)
        if getattr(resp, "usage", None):
            totals.chat_prompt_tokens += resp.usage.prompt_tokens
            totals.chat_completion_tokens += resp.usage.completion_tokens
        return resp

    client.embeddings.create = embed_wrapper
    client.chat.completions.create = chat_wrapper


@dataclass
class CaseResult:
    case_id: str
    query: str
    expected_products: list[str]
    expect_no_match: bool
    retrieved_products: list[str] = field(default_factory=list)
    retrieve_ms: float = 0.0
    answer_ms: float = 0.0
    answer_text: str = ""
    sources: list[str] = field(default_factory=list)
    precision_at_k: float | None = None
    recall: float | None = None
    correctly_rejected: bool | None = None  # only meaningful for expect_no_match cases
    possible_hallucinations: list[str] = field(default_factory=list)


def _grounding_check(answer_text: str, sources: list[str], all_product_names: list[str]) -> list[str]:
    """
    Heuristic faithfulness check: any catalog product name that appears (as a
    case-insensitive substring) in the generated answer but was never in the
    retrieved `sources` is a candidate hallucination -- the model invented a
    recommendation outside what it was given.
    """
    lowered_answer = answer_text.lower()
    sources_lower = {s.lower() for s in sources}
    flagged = []
    for name in all_product_names:
        if name.lower() in lowered_answer and name.lower() not in sources_lower:
            flagged.append(name)
    return flagged


def run_case(pa: PharmaAssistant, case: EvalCase, all_product_names: list[str]) -> CaseResult:
    result = CaseResult(
        case_id=case.id,
        query=case.query,
        expected_products=case.expected_products,
        expect_no_match=case.expect_no_match,
    )

    t0 = time.perf_counter()
    idxs = pa.retrieve(case.query)
    result.retrieve_ms = round((time.perf_counter() - t0) * 1000, 1)
    result.retrieved_products = [pa.cards[i].get("product_name", "") for i in idxs]

    if case.expected_products:
        hits = set(result.retrieved_products) & set(case.expected_products)
        result.precision_at_k = round(len(hits) / len(result.retrieved_products), 3) if result.retrieved_products else 0.0
        result.recall = round(len(hits) / len(case.expected_products), 3)

    t0 = time.perf_counter()
    answer = pa.answer(case.query)
    result.answer_ms = round((time.perf_counter() - t0) * 1000, 1)
    result.answer_text = answer.get("answer", "")
    result.sources = answer.get("sources", [])

    if case.expect_no_match:
        result.correctly_rejected = len(result.sources) == 0

    result.possible_hallucinations = _grounding_check(result.answer_text, result.sources, all_product_names)
    return result


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def summarize(results: list[CaseResult], totals: UsageTotals) -> dict[str, Any]:
    scored = [r for r in results if r.recall is not None]
    precisions = [r.precision_at_k for r in scored if r.precision_at_k is not None]
    recalls = [r.recall for r in scored if r.recall is not None]
    no_match_cases = [r for r in results if r.expect_no_match]
    retrieve_latencies = [r.retrieve_ms for r in results]
    answer_latencies = [r.answer_ms for r in results]

    return {
        "cases_total": len(results),
        "retrieval": {
            "mean_precision_at_k": round(statistics.mean(precisions), 3) if precisions else None,
            "mean_recall": round(statistics.mean(recalls), 3) if recalls else None,
            "cases_scored": len(scored),
        },
        "no_match_handling": {
            "cases": len(no_match_cases),
            "correctly_rejected": sum(1 for r in no_match_cases if r.correctly_rejected),
        },
        "grounding": {
            "cases_with_possible_hallucination": sum(1 for r in results if r.possible_hallucinations),
        },
        "latency_ms": {
            "retrieve_p50": _percentile(retrieve_latencies, 50),
            "retrieve_p95": _percentile(retrieve_latencies, 95),
            "answer_p50": _percentile(answer_latencies, 50),
            "answer_p95": _percentile(answer_latencies, 95),
        },
        "usage": asdict(totals) | {"estimated_cost_usd": round(totals.estimated_cost_usd(), 5)},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant-id", default=TENANT_ID)
    ap.add_argument("--out-dir", default=".eval_artifacts")
    args = ap.parse_args()

    cfg_ns = resolve_config_namespace(tenant_id=args.tenant_id, repo_root=REPO_ROOT)
    settings = Settings.from_config(cfg_ns)

    t0 = time.perf_counter()
    pa = PharmaAssistant(settings)
    init_ms = round((time.perf_counter() - t0) * 1000, 1)

    totals = UsageTotals()
    _instrument_client(pa.client, totals)

    all_product_names = [c.get("product_name", "") for c in pa.cards]

    results = [run_case(pa, case, all_product_names) for case in CASES]
    summary = summarize(results, totals)

    report = {
        "run_id": str(uuid4()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "tenant_id": args.tenant_id,
        "catalog_size": len(pa.df),
        "init_ms": init_ms,
        "top_k": settings.TOP_K,
        "embedding_model": settings.EMBEDDING_MODEL,
        "chat_model": settings.CHAT_MODEL,
        "summary": summary,
        "cases": [asdict(r) for r in results],
    }

    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval_run_{report['run_id']}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== PharmaAssistant eval: {args.tenant_id} ({len(results)} cases) ===")
    print(f"Retrieval: mean precision@k={summary['retrieval']['mean_precision_at_k']}, "
          f"mean recall={summary['retrieval']['mean_recall']} "
          f"(scored on {summary['retrieval']['cases_scored']} cases with expected products)")
    print(f"No-match handling: {summary['no_match_handling']['correctly_rejected']}/"
          f"{summary['no_match_handling']['cases']} correctly rejected out-of-catalog queries")
    print(f"Grounding: {summary['grounding']['cases_with_possible_hallucination']}/{len(results)} "
          "cases flagged a possible hallucination (heuristic substring check)")
    print(f"Latency ms: retrieve p50={summary['latency_ms']['retrieve_p50']} p95={summary['latency_ms']['retrieve_p95']} | "
          f"answer p50={summary['latency_ms']['answer_p50']} p95={summary['latency_ms']['answer_p95']}")
    print(f"Tokens: embedding={totals.embedding_tokens}, chat_prompt={totals.chat_prompt_tokens}, "
          f"chat_completion={totals.chat_completion_tokens} (~${summary['usage']['estimated_cost_usd']})")
    print(f"Report written to {out_path.relative_to(REPO_ROOT)}\n")

    for r in results:
        flag = ""
        if r.expect_no_match:
            flag = "OK" if r.correctly_rejected else "MISS (invented a product)"
        elif r.recall is not None:
            flag = f"recall={r.recall} precision@k={r.precision_at_k}"
        hallu = f" [possible hallucination: {r.possible_hallucinations}]" if r.possible_hallucinations else ""
        print(f"  - {r.case_id}: {flag}{hallu}")


if __name__ == "__main__":
    main()
