from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(
    vector_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
    top_k: int = 20,
    k: int = 60,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion (RRF) 融合向量和 BM25 两路检索结果。

    RRF 的直观理解：如果一段文本在两路检索中排名都靠前，它的综合得分会很高；
    如果只在一路中排名靠前，得分中等；如果两路排名都靠后，得分最低。
    不需要对分数做归一化，天然兼容不同检索系统的评分分布。

    数学公式：
        score(d) = sum(1 / (k + rank_i(d)))
    其中 rank_i(d) 是文档 d 在第 i 路结果中的排名（从 1 开始）。
    k=60 是 RRF 论文（Cornack et al.）建议的典型值：
    较大的 k 值降低排名靠前文档的领先优势，使更多文档有机会进入 top_k。
    """
    # id -> [score, doc_dict]
    rrf_scores: dict[str, list] = {}

    for rank, doc in enumerate(vector_results):
        doc_id = doc.get("id", "")
        if doc_id:
            rrf_scores[doc_id] = [1.0 / (k + rank + 1), doc]

    for rank, doc in enumerate(bm25_results):
        doc_id = doc.get("id", "")
        if not doc_id:
            continue
        if doc_id in rrf_scores:
            rrf_scores[doc_id][0] += 1.0 / (k + rank + 1)
        else:
            rrf_scores[doc_id] = [1.0 / (k + rank + 1), doc]

    sorted_results = sorted(rrf_scores.values(), key=lambda x: x[0], reverse=True)
    return [doc for _, doc in sorted_results[:top_k]]
