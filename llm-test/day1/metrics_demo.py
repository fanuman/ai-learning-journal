import math


def precision_at_k(retrieved, relevant, k):
    return sum(c in relevant for c in retrieved[:k]) / k


def recall_at_k(retrieved, relevant, k):
    return sum(c in relevant for c in retrieved[:k]) / len(relevant)


def hit_rate_at_k(retrieved, relevant, k):
    return 1.0 if any(c in relevant for c in retrieved[:k]) else 0.0


def mrr(retrieved, relevant):
    for rank, chunk in enumerate(retrieved, start=1):
        if chunk in relevant:
            return 1 / rank
    return 0.0


def ndcg_at_k(retrieved, relevant, k):
    dcg = sum(1 / math.log2(rank + 1)
              for rank, chunk in enumerate(retrieved[:k], start=1) if chunk in relevant)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant), k) + 1))
    return dcg / ideal


relevant = {"c2", "c4"}   # the chunks a human labelled as relevant for this question

searches = {
    "vector only":   ["c7", "c2", "c9", "c4", "c1"],
    "after re-rank": ["c2", "c4", "c7", "c9", "c1"],
    "bad search":    ["c7", "c9", "c1", "c3", "c5"],
}

print(f"{'search':<14} {'P@5':>5} {'R@5':>5} {'R@3':>5} {'hit@5':>6} {'MRR':>5} {'nDCG@5':>7}")
for name, retrieved in searches.items():
    print(f"{name:<14} "
          f"{precision_at_k(retrieved, relevant, 5):>5.2f} "
          f"{recall_at_k(retrieved, relevant, 5):>5.2f} "
          f"{recall_at_k(retrieved, relevant, 3):>5.2f} "
          f"{hit_rate_at_k(retrieved, relevant, 5):>6.1f} "
          f"{mrr(retrieved, relevant):>5.2f} "
          f"{ndcg_at_k(retrieved, relevant, 5):>7.3f}")