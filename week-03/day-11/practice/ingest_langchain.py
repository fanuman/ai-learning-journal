# ingest_langchain.py
import glob
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma 
from dotenv import load_dotenv
from pathlib import Path
import hashlib


# To delete collection
# import chromadb
# chroma_client = chromadb.PersistentClient(path="./chroma_db_langchain")
# chroma_client.delete_collection(name="ai_governance_docs_lc")

# Chroma.from_documents() assigns a random UUID to every chunk by default,
# with no way to tell it "this chunk already exists, update it instead."
# That means every time this script runs, it adds a fresh copy of all
# chunks under new IDs rather than overwriting the previous run's data -
# which is exactly what caused 601 chunks to silently become 1803 after
# three reruns. Hashing each chunk's source + page + content into a
# deterministic ID means the same chunk always maps to the same ID, so
# Chroma correctly treats a rerun as an update (upsert) instead of a
# fresh insert. Content is included (not just source+page) so that if
# chunking parameters change and a page splits differently, the now-
# different chunk gets a new ID rather than silently overwriting an
# unrelated old one that happened to share the same source/page.
def generate_id(chunk):
    content = f"{chunk.metadata['source']}-{chunk.metadata['page']}-{chunk.page_content}"
    return hashlib.md5(content.encode()).hexdigest()


load_dotenv()

SCRIPT_DIR = Path(__file__).parent
pdf_files = list((SCRIPT_DIR / "data").glob("*.pdf"))
print(f"Found {len(pdf_files)} PDF(s)")

all_documents = []
for pdf_path in pdf_files:
    loader = PyPDFLoader(str(pdf_path))
    all_documents.extend(loader.load())  # one Document per PAGE

print(f"Loaded {len(all_documents)} pages total")

splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
chunks = splitter.split_documents(all_documents)
print(f"Split into {len(chunks)} chunks")

print("chunks-----------")
for i, chunk in enumerate(chunks):
    print(f"Chunk {i}: {chunk!r}")

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

ids = [generate_id(chunk) for chunk in chunks]

vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./chroma_db_langchain",
    collection_name="ai_governance_docs_lc",
    ids=ids
)
print(f"Stored {vectorstore._collection.count()} chunks")