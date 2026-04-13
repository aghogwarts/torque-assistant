"""
rag.py — v2: Chroma vector DB with metadata-filtered retrieval

SOP retrieval uses Chroma's native `where` filtering:
  Tier 1: joint + vehicle_model filter → similarity rank within matches
  Tier 2: joint-only filter → similarity rank
  Tier 3: unfiltered similarity fallback (rare — only for unknown joints)

Incident retrieval filters by joint and/or tool_id using Chroma's $or operator.

Both collections are persisted to chroma_db/ and rebuilt only when the directory
is missing. Delete chroma_db/ to force a full rebuild.
"""

import json
import logging
import os
import shutil
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

load_dotenv()

logger = logging.getLogger("torque.rag")

CHROMA_DIR = "chroma_db"
SOP_COLLECTION = "sop_chunks"
INCIDENT_COLLECTION = "past_incidents"

api_key = os.getenv("OPENROUTER_API_KEY")


def _get_embeddings():
    if api_key is None:
        raise ValueError("OPENROUTER_API_KEY not set")
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr(api_key),
    )


# ── SOP Store ─────────────────────────────────────────────────────────────────

class SOPStore:
    """
    Chroma-backed SOP store with tiered metadata filtering.

    Tier 1: joint + vehicle_model → exact match, similarity ranked
    Tier 2: joint only → broader match across all vehicle models
    Tier 3: unfiltered similarity → fallback for unknown joints
    """

    def __init__(self, chroma: Chroma):
        self.chroma = chroma

    def retrieve(self, joint: str, vehicle_model: str = "",
                 validation: str = "", k: int = 6) -> list[str]:

        # Tier 1: joint + vehicle_model
        if vehicle_model:
            results = self.chroma.similarity_search(
                query=f"{joint} {validation}",
                k=k,
                filter={
                    "$and": [
                        {"joint": {"$eq": joint}},
                        {"vehicle_model": {"$eq": vehicle_model}},
                    ]
                },
            )
            if results:
                logger.debug("[RAG-SOP] Tier 1: %d chunks for %s + %s",
                             len(results), joint, vehicle_model)
                return [doc.page_content for doc in results]

        # Tier 2: joint only
        results = self.chroma.similarity_search(
            query=f"{joint} {validation}",
            k=k,
            filter={"joint": {"$eq": joint}},
        )
        if results:
            logger.debug("[RAG-SOP] Tier 2: %d chunks for %s (any model)",
                         len(results), joint)
            return [doc.page_content for doc in results]

        # Tier 3: unfiltered similarity fallback
        results = self.chroma.similarity_search(
            query=f"{joint} {validation}",
            k=k,
        )
        logger.debug("[RAG-SOP] Tier 3 fallback: %d chunks via similarity", len(results))
        return [doc.page_content for doc in results]


def build_vector_store(path: str) -> SOPStore:
    """
    Builds or loads the SOP Chroma collection.
    Persisted to chroma_db/. Delete the directory to force rebuild.
    """
    embeddings = _get_embeddings()
    collection_path = os.path.join(CHROMA_DIR, SOP_COLLECTION)

    if os.path.exists(collection_path):
        print(f"[RAG] Loading existing SOP collection from {collection_path}")
        chroma = Chroma(
            collection_name=SOP_COLLECTION,
            embedding_function=embeddings,
            persist_directory=collection_path,
        )
        count = chroma._collection.count()
        print(f"[RAG] SOP collection loaded — {count} chunks")
        return SOPStore(chroma)

    print("[RAG] Building SOP collection...")
    with open(path) as f:
        chunks = json.load(f)

    texts = []
    metadatas = []
    ids = []

    for chunk in chunks:
        texts.append(chunk["content"])
        ids.append(chunk["chunk_id"])
        metadatas.append({
            "chunk_id": chunk["chunk_id"],
            "chunk_type": chunk.get("chunk_type", ""),
            "sop_id": chunk.get("sop_id", ""),
            "joint": chunk.get("joint", ""),
            "vehicle_model": chunk.get("vehicle_model", ""),
            "station": chunk.get("station", ""),
            "tightening_method": chunk.get("tightening_method", ""),
            "safety_critical": str(chunk.get("safety_critical", "")),
        })

    chroma = Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        ids=ids,
        embedding=embeddings,
        collection_name=SOP_COLLECTION,
        persist_directory=collection_path,
    )

    print(f"[RAG] SOP collection built and persisted — {len(chunks)} chunks")
    return SOPStore(chroma)


# ── Incident Store ────────────────────────────────────────────────────────────

class IncidentStore:
    """
    Chroma-backed incident store with metadata filtering.

    Filters by joint and/or tool_id using $or, then falls back to
    unfiltered similarity if no metadata matches.
    """

    def __init__(self, chroma: Chroma):
        self.chroma = chroma

    def retrieve(self, joint: str, tool_id: str = "",
                 validation: str = "", k: int = 3) -> list[str]:

        # Build filter: match joint OR tool_id (either is relevant context)
        conditions = []
        if joint:
            conditions.append({"joint": {"$eq": joint}})
        if tool_id:
            conditions.append({"tool_id": {"$eq": tool_id}})

        if conditions:
            where_filter = {"$or": conditions} if len(conditions) > 1 else conditions[0]
            results = self.chroma.similarity_search(
                query=f"{joint} {validation} {tool_id}",
                k=k,
                filter=where_filter,
            )
            if results:
                logger.debug("[RAG-INC] Metadata hit: %d incidents for joint=%s tool=%s",
                             len(results), joint, tool_id)
                return [doc.page_content for doc in results]

        # Fallback: unfiltered similarity
        results = self.chroma.similarity_search(
            query=f"{joint} {validation} {tool_id}",
            k=k,
        )
        logger.debug("[RAG-INC] Fallback: %d incidents via similarity", len(results))
        return [doc.page_content for doc in results]


def build_incident_vector_store(path: str) -> IncidentStore:
    """
    Builds or loads the incident Chroma collection.
    Persisted to chroma_db/. Delete the directory to force rebuild.
    """
    embeddings = _get_embeddings()
    collection_path = os.path.join(CHROMA_DIR, INCIDENT_COLLECTION)

    if os.path.exists(collection_path):
        print(f"[RAG] Loading existing incident collection from {collection_path}")
        chroma = Chroma(
            collection_name=INCIDENT_COLLECTION,
            embedding_function=embeddings,
            persist_directory=collection_path,
        )
        count = chroma._collection.count()
        print(f"[RAG] Incident collection loaded — {count} incidents")
        return IncidentStore(chroma)

    print("[RAG] Building incident collection...")
    with open(path) as f:
        incidents = json.load(f)

    texts = []
    metadatas = []
    ids = []

    for i, inc in enumerate(incidents):
        texts.append(inc["content"])
        ids.append(f"INC-{i:04d}")
        metadatas.append({
            "tool_id": inc.get("tool_id") or "",
            "joint": inc.get("joint") or "",
            "station": inc.get("station") or "",
            "failure_type": inc.get("failure_type") or "",
        })

    chroma = Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        ids=ids,
        embedding=embeddings,
        collection_name=INCIDENT_COLLECTION,
        persist_directory=collection_path,
    )

    print(f"[RAG] Incident collection built and persisted — {len(incidents)} incidents")
    return IncidentStore(chroma)


# ── Convenience functions (used by workflow_nodes.py) ─────────────────────────

def retrieve_context(store: SOPStore, joint: str, vehicle_model: str = "",
                     validation: str = "", k: int = 6) -> list[str]:
    """Retrieve SOP context with metadata filtering."""
    return store.retrieve(joint, vehicle_model, validation, k)


def retrieve_incident_context(store: IncidentStore, joint: str, tool_id: str = "",
                              validation: str = "", k: int = 3) -> list[str]:
    """Retrieve incident context with metadata filtering."""
    return store.retrieve(joint, tool_id, validation, k)