# experiment_2.py
import chromadb
from rank_bm25 import BM25Okapi

from bm25_search import bm25_search

# adjust this path based on what `find` showed you
chroma_client = chromadb.PersistentClient(path="./chroma_db_langchain")

# get_collection (not get_or_create) - if the name/path is wrong, this
# fails loudly instead of silently creating a new, empty collection
collection = chroma_client.get_collection(name="ai_governance_docs_lc")

all_data = collection.get()  # no query - just pulls everything stored
all_chunks = all_data["documents"]
print(f"Pulled {len(all_chunks)} chunks from the existing collection")

query = "What does GDPR say about AI risk management?"
results = bm25_search(query, all_chunks, k=10)

print(f"\nBM25 scores for: {query!r}")
for idx, score in results[:5]:
    print(f"  {score:.4f} - {all_chunks[idx][:80]}...")

top_chunk = all_chunks[results[0][0]]
print("gdpr" in top_chunk.lower())