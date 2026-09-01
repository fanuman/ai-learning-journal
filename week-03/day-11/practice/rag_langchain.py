# rag_langchain.py
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
# from langchain_community.vectorstores import Chroma
from langchain_chroma import Chroma 
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from dotenv import load_dotenv
import os

load_dotenv()

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = Chroma(
    persist_directory="./chroma_db_langchain",
    embedding_function=embeddings,
    collection_name="ai_governance_docs_lc"
)
# retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
retriever = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"score_threshold": 0.35, "k": 5}
)

def format_docs(docs):
    return "\n\n".join(
        f"[Source: {os.path.basename(doc.metadata['source'])}, page {doc.metadata['page']}]\n{doc.page_content}"
        for doc in docs
    )

prompt = ChatPromptTemplate.from_template("""Answer the question using ONLY the context below. Cite which source document(s) and page(s) you used. If the answer isn't in the context, say "I don't have information about that."

Context:
\"\"\"
{context}
\"\"\"

Question: {question}
Answer:""")

model = ChatOpenAI(model="gpt-4o-mini")

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | model
    | StrOutputParser()
)

if __name__ == "__main__":
    print(rag_chain.invoke("What is prompt injection and how do you prevent it?"))

    # Obviously unrelated (should be filtered by the threshold, cheaply, before the LLM ever sees it):
    print("\n=== Programming language question ===")
    print(rag_chain.invoke("What's the best programming language for beginners?"))

    # Near Miss
    print("\n=== GDPR question ===n")
    print(rag_chain.invoke("What does GDPR say about AI risk management?"))