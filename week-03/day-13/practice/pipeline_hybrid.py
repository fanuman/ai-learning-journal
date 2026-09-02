# pipeline_hybrid.py
import chromadb
from openai import OpenAI
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db_langchain")
collection = chroma_client.get_collection(name="ai_governance_docs_lc")

all_data = collection.get()
all_ids = all_data["ids"]
all_chunks = all_data["documents"]
id_to_text = dict(zip(all_ids, all_chunks))

# Loaded once at import time, not inside run_hybrid(). This model load is
# expensive - reloading it on every question in run_eval.py's loop would
# be Day 3's wasted-work lesson again, just with a model instead of an
# API call. One load, reused across every call this process makes.
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')


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


def rerank(query, candidate_ids, top_k=5):
    candidates = [id_to_text[cid] for cid in candidate_ids]
    pairs = [(query, chunk) for chunk in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidate_ids, candidates, scores), key=lambda x: x[2], reverse=True)
    return ranked[:top_k]


def build_prompt(query, chunks):
    # Deliberately identical wording to pipeline_semantic.py's prompt.
    # If the prompt text also differed between the two pipelines, any
    # score difference run_eval.py finds couldn't be attributed to
    # retrieval strategy alone - same "change one variable at a time"
    # principle from Day 2's prompt comparisons.
    context = "\n\n".join(chunks)
    return f"""Answer the question using ONLY the context below. If the answer isn't in the context, say "I don't have information about that."

Context:
\"\"\"
{context}
\"\"\"

Question: {query}
Answer:"""


def run_hybrid(query: str, top_k: int = 5) -> tuple[str, list[str]]:
    bm25_ids = bm25_search(query, all_ids, all_chunks, k=20)
    semantic_ids = semantic_search(query, k=20)
    fused = reciprocal_rank_fusion([bm25_ids, semantic_ids])
    top_20_ids = [doc_id for doc_id, score in fused[:20]]

    final = rerank(query, top_20_ids, top_k=top_k)
    chunks = [chunk for _, chunk, _ in final]

    # No hard score threshold here, unlike pipeline_semantic.py's distance
    # check. Day 12 found RRF's fused scores cluster tightly regardless of
    # the real underlying signal strength, and the cross-encoder's raw
    # scores aren't calibrated against this corpus - neither is a number
    # worth thresholding on the way Chroma's cosine distance was. This
    # pipeline leans entirely on the prompt's grounding instruction to
    # trigger refusal - exactly what Day 12's bonus test already confirmed
    # works even with weak or irrelevant context.

    prompt = build_prompt(query, chunks)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content, chunks


if __name__ == "__main__":
    answer, chunks = run_hybrid("What is prompt injection and how do you prevent it?")
    print(answer)
    print(f"\n{len(chunks)} chunks retrieved")