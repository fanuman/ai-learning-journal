from openai import OpenAI
import chromadb


client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# To delete existing collection in case of some mistake
# chroma_client.delete_collection(name="my_documents")

collection = chroma_client.get_or_create_collection(
    name="my_documents",
    configuration={"hnsw": {"space": "cosine"}}
)

def get_embedding(text, model="text-embedding-3-small"):
    response = client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


documents = [
    # Original set
    "The cat sat on the mat.",
    "A feline rested on the rug.",
    "The stock market crashed today.",
    "The bank raised interest rates.",
    "I sat by the river bank.",

    # Another clear paraphrase pair (different domain)
    "She baked a chocolate cake for the party.",
    "A chocolate dessert was made by her for the celebration.",

    # Another polysemous word - "spring" (mattress coil vs. season)
    "The old mattress had a broken spring.",
    "We visited the park in early spring.",

    # Near-duplicate - almost identical wording, tests the "ceiling" of similarity
    "The cat sat on the mat today.",

    # Negation - same topic, opposite meaning, minimal word change
    "The movie was excellent.",
    "The movie was not excellent.",

    # Same meaning, very different register (casual vs. formal)
    "Can u send me that file asap?",
    "Could you please send me that file as soon as possible?",

    # Totally unrelated, for a clean baseline
    "The Great Wall of China stretches thousands of miles.",
]

collection.add(
    ids=[f"doc_{i}" for i in range(len(documents))],
    documents=documents,
    embeddings=[get_embedding(doc) for doc in documents]
)

query = "Was the movie good?"
results = collection.query(
    query_embeddings=[get_embedding(query)],
    n_results=3
)


for doc, distance in zip(results["documents"][0], results["distances"][0]):
    print(f"{distance:.4f} - {doc}")