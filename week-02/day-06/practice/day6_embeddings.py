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

sentences = [
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

embeddings = [get_embedding(s) for s in sentences]
print(f"Embedding dimension: {len(embeddings[0])}")  # 1536

for i in range(len(sentences)):
    for j in range(i + 1, len(sentences)):
        sim = cosine_similarity(embeddings[i], embeddings[j])
        print(f"'{sentences[i]}' vs '{sentences[j]}': {sim:.4f}")