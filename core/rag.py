import json
import os
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# load env variables
load_dotenv()
INDEX_PATH = "vector_index"

api_key = os.getenv("OPENROUTER_API_KEY")


def build_vector_store(path: str):
    if api_key is None:
        raise ValueError("OPENROUTER_API_KEY not set")

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",  # embedding model
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr(api_key),
    )

    # load existing index if present
    if os.path.exists(INDEX_PATH):
        print("[RAG] Loading existing FAISS index...")
        return FAISS.load_local(
            INDEX_PATH, embeddings, allow_dangerous_deserialization=True
        )

    print("[RAG] Building FAISS index...")

    with open(path) as f:
        chunks = json.load(f)

    texts = [c["content"] for c in chunks]

    vectorstore = FAISS.from_texts(texts, embeddings)

    vectorstore.save_local(INDEX_PATH)

    print("[RAG] Index saved to disk.")

    return vectorstore


# retrieve top k relevant chunks
def retrieve_context(vectorstore, query: str, k: int = 4):
    docs = vectorstore.similarity_search(query, k=k)
    return [d.page_content for d in docs]
