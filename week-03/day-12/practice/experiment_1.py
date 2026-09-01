from bm25_search import bm25_search
from reciprocal_rank_fusion import reciprocal_rank_fusion

from openai import OpenAI
import numpy as np

client = OpenAI()


def get_embedding(text, model="text-embedding-3-small"):
    response = client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


def cosine_similarity(vec_a, vec_b):
    vec_a = np.array(vec_a)
    vec_b = np.array(vec_b)
    dot_product = np.dot(vec_a, vec_b)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    return dot_product / (norm_a * norm_b)

toy_chunks = [
    "The movie was excellent.",
    "The movie was not excellent.",
    "She baked a chocolate cake for the party.",
]
# query = "Find reviews that were not positive"
query = "Was the movie good?"

bm25_results = bm25_search(query, toy_chunks, k=3)
print("BM25 ranking:")
for idx, score in bm25_results:
    print(f"  {score:.4f} - {toy_chunks[idx]}")

query_emb = get_embedding(query)
sims = [(i, cosine_similarity(query_emb, get_embedding(chunk))) for i, chunk in enumerate(toy_chunks)]
semantic_ranked_ids = [i for i, s in sorted(sims, key=lambda x: x[1], reverse=True)]
bm25_ranked_ids = [idx for idx, score in bm25_results]

print("Semantic-only ranking:")
for i, score in sorted(sims, key=lambda x: x[1], reverse=True):
    print(f"  {score:.4f} - {toy_chunks[i]}")

fused = reciprocal_rank_fusion([bm25_ranked_ids, semantic_ranked_ids])
print("\nFused (hybrid) ranking:")
for idx, score in fused:
    print(f"  {score:.4f} - {toy_chunks[idx]}")