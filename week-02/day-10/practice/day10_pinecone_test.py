import os

import httpcore
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

# Something on this network resets the TLS handshake to Pinecone's data-plane
# hosts (*.svc.*.pinecone.io) whenever the ClientHello carries an SNI extension.
# The control plane (api.pinecone.io) is unaffected, which is why create_index
# works but upsert/query die with "[Errno 54] Connection reset by peer".
# Dropping SNI for pinecone.io hosts gets the handshake through. The certificate
# chain is still verified against the system CAs; only the hostname match is
# skipped, since without SNI the server can't know which name we asked for.
# Delete this block when running on a network that doesn't filter SNI.
_start_tls = httpcore._backends.sync.SyncStream.start_tls


def _start_tls_without_sni(self, ssl_context, server_hostname=None, timeout=None):
    if server_hostname and server_hostname.endswith("pinecone.io"):
        ssl_context.check_hostname = False
        server_hostname = None
    return _start_tls(self, ssl_context, server_hostname, timeout)


httpcore._backends.sync.SyncStream.start_tls = _start_tls_without_sni

openai_client = OpenAI()
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))


model = 'gpt-4o-mini'

# To delete existing index in case of some mistake
# pc.delete_index(name="my_documents")

index_name = "acme-handbook"

if not pc.has_index(index_name):
    pc.create_index(
        name=index_name,
        dimension=1536,          # must match your embedding model
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")  # free tier: us-east-1 only
    )

index = pc.index(index_name)

def get_embedding(text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


documents = [
    "Acme Corp's remote work policy allows employees to work from abroad for up to 45 days per year, with manager approval required for trips longer than 2 weeks.",
    "Acme Corp provides a $75 monthly stipend for home office equipment, reimbursable with receipts submitted within 90 days.",
    "Acme Corp's parental leave policy grants 16 weeks of fully paid leave for the primary caregiver and 6 weeks for the secondary caregiver.",
    "Acme Corp's standard vacation policy is 22 days per year, increasing to 27 days after 5 years of tenure.",
]


index.upsert(vectors=[
    (f"doc_{i}", get_embedding(doc), {"text": doc})
    for i, doc in enumerate(documents)
])


def retrieve(query, k=3):
    query_embedding = get_embedding(query)
    results = index.query(vector=query_embedding, top_k=k, include_metadata=True)
    return results

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
    results = retrieve(query, k=k)

    for match in results.matches:
        print(f"{match.score:.4f} - {match.metadata['text']}")

    if all(match.score <= 0.5 for match in results.matches):
        return "I don't have information about that. (No Document Matches)"

    chunks = [match.metadata["text"] for match in results.matches]
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