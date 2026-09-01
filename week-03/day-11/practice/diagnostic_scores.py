from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()


embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

vectorstore = Chroma(
    persist_directory="./chroma_db_langchain",
    collection_name="ai_governance_docs_lc",
    embedding_function=embeddings

)

docs_with_scores = vectorstore.similarity_search_with_relevance_scores(
    "What is prompt injection and how do you prevent it?", k=5
)
print("Real match:")
for doc, score in docs_with_scores:
    print(f"  {score:.4f} - {doc.metadata['source']}, page {doc.metadata['page']}")

docs_with_scores_bad = vectorstore.similarity_search_with_relevance_scores(
    "What does GDPR say about AI risk management?", k=5
)
print("Near-miss:")
for doc, score in docs_with_scores_bad:
    print(f"  {score:.4f} - {doc.metadata['source']}, page {doc.metadata['page']}")