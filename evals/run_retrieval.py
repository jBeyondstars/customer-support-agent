"""Compare vector, keyword and hybrid search on a small labelled question set.

For each question we look at the rank of the first chunk that comes from one of
its expected documents. With 62 chunks almost everything lands in the top 5, so
hit@1 and MRR are the numbers that actually tell the methods apart.
"""

import json
from datetime import date
from pathlib import Path

import psycopg

from support_agent.config import get_settings
from support_agent.llm import get_embeddings
from support_agent.rag.retriever import hybrid_search, keyword_search, vector_search

HERE = Path(__file__).parent
K = 5

METHODS = {
    "vector": lambda conn, question, embedding: vector_search(conn, embedding, K),
    "keyword": lambda conn, question, embedding: keyword_search(conn, question, K),
    "hybrid": lambda conn, question, embedding: hybrid_search(conn, question, embedding, K),
}


def first_hit(results, expected: list[str]) -> int | None:
    return next((rank for rank, r in enumerate(results, 1) if r.document in expected), None)


def hit_at(ranks: list[int | None], k: int) -> float:
    return sum(r is not None and r <= k for r in ranks) / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    return sum(1 / r for r in ranks if r) / len(ranks)


def main() -> None:
    lines = (HERE / "datasets" / "retrieval.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    embeddings = get_embeddings().embed_documents([case["question"] for case in cases])

    table = [
        f"| method | hit@1 EN | hit@1 FR | MRR EN | MRR FR | hit@{K} all |",
        "|---|---|---|---|---|---|",
    ]
    not_first: dict[str, list[str]] = {}

    with psycopg.connect(get_settings().database_url) as conn:
        for name, run in METHODS.items():
            ranks = {"en": [], "fr": []}
            for case, embedding in zip(cases, embeddings, strict=True):
                rank = first_hit(run(conn, case["question"], embedding), case["expected"])
                ranks[case.get("lang", "en")].append(rank)
                if rank != 1:
                    label = f"rank {rank}" if rank else "missed"
                    not_first.setdefault(name, []).append(f"{case['question']} ({label})")

            en, fr = ranks["en"], ranks["fr"]
            table.append(
                f"| {name} | {hit_at(en, 1):.0%} | {hit_at(fr, 1):.0%}"
                f" | {mrr(en):.2f} | {mrr(fr):.2f} | {hit_at(en + fr, K):.0%} |"
            )

    report = [
        f"# Retrieval eval, {date.today()}",
        "",
        f"{len(cases)} questions ({sum(c.get('lang') == 'fr' for c in cases)} in French).",
        "",
        *table,
    ]
    for name, questions in not_first.items():
        report += ["", f"Not ranked first by {name}:", *[f"- {q}" for q in questions]]

    text = "\n".join(report) + "\n"
    (HERE / "reports").mkdir(exist_ok=True)
    (HERE / "reports" / "retrieval.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
