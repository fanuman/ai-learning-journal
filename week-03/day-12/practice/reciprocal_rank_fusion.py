def reciprocal_rank_fusion(ranked_lists, k=60):
    fused_scores = {}
    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list, start=1):
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + 1 / (k + rank)
    return sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)