from support_agent.rag.retriever import SearchResult, reciprocal_rank_fusion


def result(chunk_id: int) -> SearchResult:
    return SearchResult(chunk_id, "doc.md", "Doc", "Doc", "text", score=0.0)


def test_chunk_found_by_both_searches_ranks_first():
    vector = [result(1), result(2), result(3)]
    keyword = [result(4), result(2)]

    fused = reciprocal_rank_fusion(vector, keyword)

    assert [r.chunk_id for r in fused] == [2, 1, 4, 3]


def test_empty_ranking_is_ignored():
    fused = reciprocal_rank_fusion([result(1), result(2)], [])

    assert [r.chunk_id for r in fused] == [1, 2]
    assert fused[0].score == 1 / 61
