from dataclasses import dataclass, replace

import psycopg

from support_agent.llm import get_embeddings


@dataclass(frozen=True)
class SearchResult:
    chunk_id: int
    document: str
    title: str
    section: str
    content: str
    score: float


def vector_search(
    conn: psycopg.Connection, embedding: list[float], limit: int
) -> list[SearchResult]:
    rows = conn.execute(
        """
        select c.id, c.document_path, d.title, c.section, c.content,
               1 - (c.embedding <=> %(e)s::vector) as score
        from kb_chunks c
        join kb_documents d on d.path = c.document_path
        order by c.embedding <=> %(e)s::vector
        limit %(limit)s
        """,
        {"e": embedding, "limit": limit},
    ).fetchall()
    return [SearchResult(*row) for row in rows]


def keyword_search(conn: psycopg.Connection, query: str, limit: int) -> list[SearchResult]:
    # plainto_tsquery ANDs every word, which almost never matches a full
    # question. OR-ing the lexemes and letting ts_rank sort it out works better.
    rows = conn.execute(
        """
        with q as (
            select string_agg(quote_literal(lexeme), ' | ')::tsquery as query
            from unnest(to_tsvector('english', %(query)s))
        )
        select c.id, c.document_path, d.title, c.section, c.content,
               ts_rank_cd(c.tsv, q.query) as score
        from kb_chunks c
        join kb_documents d on d.path = c.document_path
        cross join q
        where c.tsv @@ q.query
        order by score desc
        limit %(limit)s
        """,
        {"query": query, "limit": limit},
    ).fetchall()
    return [SearchResult(*row) for row in rows]


def reciprocal_rank_fusion(*rankings: list[SearchResult], k: int = 60) -> list[SearchResult]:
    scores: dict[int, float] = {}
    results: dict[int, SearchResult] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1 / (k + rank)
            results.setdefault(result.chunk_id, result)
    best = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [replace(results[chunk_id], score=scores[chunk_id]) for chunk_id in best]


def hybrid_search(
    conn: psycopg.Connection,
    query: str,
    embedding: list[float],
    limit: int = 5,
    candidates: int = 20,
) -> list[SearchResult]:
    fused = reciprocal_rank_fusion(
        vector_search(conn, embedding, candidates),
        keyword_search(conn, query, candidates),
    )
    return fused[:limit]


def search(conn: psycopg.Connection, query: str, limit: int = 5) -> list[SearchResult]:
    return hybrid_search(conn, query, get_embeddings().embed_query(query), limit)
