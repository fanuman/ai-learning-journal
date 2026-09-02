# pipeline_semantic.py
from openai import OpenAI
import chromadb
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI()

# Same collection Day 11/12 already confirmed working - verify this path
# matches wherever it actually landed on your machine
chroma_client = chromadb.PersistentClient(path="./chroma_db_langchain")
collection = chroma_client.get_collection(name="ai_governance_docs_lc")

def get_embedding(text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(input=text, model=model)
    return response.data[0].embedding

def retrieve(query, k=5):
    query_embedding = get_embedding(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=k)
    chunks, distances = results["documents"][0], results["distances"][0]
    # for d in distances:
    #     print(f"  {d:.4f}")
    return chunks, distances

def build_prompt(query, chunks):
    context = "\n\n".join(chunks)
    return f"""Answer the question using ONLY the context below. If the answer isn't in the context, say "I don't have information about that."

Context:
\"\"\"
{context}
\"\"\"

Question: {query}
Answer:"""

def run_semantic(query: str, k: int = 5) -> tuple[str, list[str]]:
    chunks, distances = retrieve(query, k=k)

    if all(distance >= 1.2 for distance in distances):
        return "I don't have information about that. (No Document Matches)", chunks

    prompt = build_prompt(query, chunks)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content, chunks


if __name__ == "__main__":
    # print("Real match distances:")
    # _, chunks = run_semantic("What is prompt injection and how do you prevent it?")
    # print("\nKnown-irrelevant distances:")
    # _, chunks = run_semantic("What's the best programming language for beginners?")

    _, chunks = run_semantic("What is LLM01?")
    for c in chunks:
        print(f"\n--- chunk ---\n{c[:200]}")