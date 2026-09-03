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