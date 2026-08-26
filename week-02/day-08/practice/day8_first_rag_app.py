from openai import OpenAI
import chromadb


openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db")

model = 'gpt-4o-mini'

# To delete existing collection in case of some mistake
# chroma_client.delete_collection(name="my_documents")

def get_embedding(text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(input=text, model=model)
    return response.data[0].embedding

collection = chroma_client.get_or_create_collection(
    name="acme_handbook",
    configuration={"hnsw": {"space": "cosine"}}
)

documents = [
    "Acme Corp's remote work policy allows employees to work from abroad for up to 45 days per year, with manager approval required for trips longer than 2 weeks.",
    "Acme Corp provides a $75 monthly stipend for home office equipment, reimbursable with receipts submitted within 90 days.",
    "Acme Corp's parental leave policy grants 16 weeks of fully paid leave for the primary caregiver and 6 weeks for the secondary caregiver.",
    "Acme Corp's standard vacation policy is 22 days per year, increasing to 27 days after 5 years of tenure.",
]

collection.add(
    ids=[f"doc_{i}" for i in range(len(documents))],
    documents=documents,
    embeddings=[get_embedding(doc) for doc in documents]
)

def retrieve(query, k=3):
    query_embedding = get_embedding(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=k)
    return results["documents"][0], results["distances"][0]

def build_prompt(query, chunks):
    context = "\n\n".join(chunks)
    return f"""Answer the question using ONLY the context below. If the answer isn't in the context, say "I don't have information about that."

    Context:
    \"\"\"
    {context}
    \"\"\"

    Question: {query}
    Answer:"""

def generate_answer(query, k=3):
    chunks, distances = retrieve(query, k=k)

    # for doc, distance in zip(chunks, distances):
    #     print(f"{distance:.4f} - {doc}")

    if all(distance >= 0.5 for distance in distances):
        return "I don't have information about that. (No Document Matches)"

    prompt = build_prompt(query, chunks)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

question1 = "How many days can I work from abroad?"
answer1 = generate_answer(question1)
print("Question: ", question1)
print("Answer: ", answer1)

question2 = "What is Acme's stock price?"
answer2 = generate_answer(question2)
print("Question: ", question2)
print("Answer: ", answer2)