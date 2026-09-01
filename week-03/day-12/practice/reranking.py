# reranking.py
import chromadb
from openai import OpenAI
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db_langchain")  # confirm this path
collection = chroma_client.get_collection(name="ai_governance_docs_lc")

all_data = collection.get()
all_ids = all_data["ids"]
all_chunks = all_data["documents"]
id_to_text = dict(zip(all_ids, all_chunks))
print(f"Pulled {len(all_chunks)} chunks")

def get_embedding(text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(input=text, model=model)
    return response.data[0].embedding

def bm25_search(query, ids, chunks, k=20):
    tokenized_corpus = [chunk.lower().split() for chunk in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    tokens = query.lower().split()
    scores = bm25.get_scores(tokens)
    ranked_positions = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [ids[i] for i in ranked_positions]

def semantic_search(query, k=20):
    query_embedding = get_embedding(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=k)
    return results["ids"][0]

def reciprocal_rank_fusion(ranked_lists, k=60):
    fused_scores = {}
    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list, start=1):
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + 1 / (k + rank)
    return sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)

reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def rerank(query, candidate_ids, top_k=5):
    candidates = [id_to_text[cid] for cid in candidate_ids]
    pairs = [(query, chunk) for chunk in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidate_ids, candidates, scores), key=lambda x: x[2], reverse=True)
    return ranked[:top_k]


query = "What is prompt injection and how do you prevent it?"

bm25_ids = bm25_search(query, all_ids, all_chunks, k=20)
semantic_ids = semantic_search(query, k=20)

print("\nSemantic-only top 5 (for comparison against Day 8/11):")
for doc_id in semantic_ids[:5]:
    print(f"  {id_to_text[doc_id][:80]}...")

fused = reciprocal_rank_fusion([bm25_ids, semantic_ids])
top_20_ids = [doc_id for doc_id, score in fused[:20]]

final = rerank(query, top_20_ids, top_k=5)
print("\nFinal re-ranked top 5:")
for doc_id, chunk, score in final:
    print(f"  {score:.4f} - {chunk[:80]}...")