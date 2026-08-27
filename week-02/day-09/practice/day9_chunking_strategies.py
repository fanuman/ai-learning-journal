


text = """Acme Corp's remote work policy allows employees to work from abroad for up to 45 days per year. Manager approval is required for trips longer than two weeks. Employees must maintain reliable internet access and be available during core hours. This policy was updated in March to reflect employee feedback from the annual survey. The updated policy also clarifies tax implications for extended international work.

Acme Corp's marketing strategy for next quarter focuses heavily on social media engagement. The team plans to increase video content production by 40 percent. A new influencer partnership program will launch alongside the product release. Budget allocation has shifted from print advertising to digital channels entirely. Early results from pilot campaigns show promising engagement metrics."""


# 1. Fixed-size
def fixed_size_chunk(text, chunk_size=200, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

print("Fixed Size Chunks")
print(fixed_size_chunk(text))

# 2. Recursive
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=200,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""]
)
recursive_chunks = splitter.split_text(text)

print("----------------------------------------")
print("Recursive Chunks")
print(recursive_chunks)

# 3. Semantic
import re
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

def split_into_sentences(text):
    return re.split(r'(?<=[.!?])\s+', text.strip())

def semantic_chunk(text, similarity_threshold=0.18):
    sentences = split_into_sentences(text)
    embeddings = [get_embedding(s) for s in sentences]

    chunks = []
    current_chunk = [sentences[0]]

    for i in range(1, len(sentences)):
        sim = cosine_similarity(embeddings[i - 1], embeddings[i])
        # print(f"{sim:.4f} - {sentences[i][:50]}...")
        if sim < similarity_threshold:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentences[i]]
        else:
            current_chunk.append(sentences[i])

    chunks.append(" ".join(current_chunk))
    return chunks


print("----------------------------------------")
print("Semantic Chunks")
print(semantic_chunk(text))