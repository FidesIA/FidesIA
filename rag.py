"""
rag.py - Pipeline RAG pour FidesIA
ChromaDB (Solon embeddings) → LlamaIndex → Ollama streaming

La base ChromaDB est pré-indexée via Domicil-IA (collection share_CathIA).
"""

import json
import logging
import asyncio
import threading
from pathlib import Path
from typing import Optional

from llama_index.core import (
    VectorStoreIndex,
    Settings,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.prompts import PromptTemplate
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

import chromadb

from config import (
    CHROMA_PATH, OLLAMA_URL, OLLAMA_MODEL,
    EMBEDDING_MODEL, SIMILARITY_TOP_K, CONTEXT_TOP_K,
    CHUNK_SIZE, CHUNK_OVERLAP, LLM_TIMEOUT,
)
from prompts import build_system_prompt, CONDENSE_QUESTION_PROMPT

logger = logging.getLogger(__name__)

# === Globals (thread-safe) ===
_index: Optional[VectorStoreIndex] = None
_chroma_client: Optional[chromadb.PersistentClient] = None
_init_lock = threading.Lock()
COLLECTION_NAME = "share_CathIA"


# === Solon Embedding (avec prefix "query: " pour les recherches) ===

class SolonEmbedding(HuggingFaceEmbedding):
    """
    Wrapper Solon-embeddings qui ajoute le prefix "query: " aux requêtes.
    Requis par le modèle OrdalieTech/Solon-embeddings-large-0.1.
    """

    def _get_query_embedding(self, query: str) -> list[float]:
        return super()._get_query_embedding(f"query: {query}")

    def get_query_embedding(self, query: str) -> list[float]:
        return super().get_query_embedding(f"query: {query}")


# === Initialisation ===

def init_settings():
    """Configure LlamaIndex settings au démarrage."""
    Settings.llm = Ollama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_URL,
        request_timeout=LLM_TIMEOUT,
    )
    logger.info(f"Chargement du modèle d'embeddings {EMBEDDING_MODEL}...")
    Settings.embed_model = SolonEmbedding(
        model_name=EMBEDDING_MODEL,
        trust_remote_code=True,
    )
    Settings.node_parser = SentenceSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    logger.info(f"Settings: LLM={OLLAMA_MODEL}, Embeddings={EMBEDDING_MODEL}")


def _get_chroma_client() -> chromadb.PersistentClient:
    global _chroma_client
    with _init_lock:
        if _chroma_client is None:
            _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _chroma_client


def init_index() -> VectorStoreIndex:
    """
    Charge l'index ChromaDB pré-indexé (via Domicil-IA).
    La collection share_CathIA doit exister et contenir des embeddings.
    """
    global _index

    client = _get_chroma_client()

    try:
        collection = client.get_collection(COLLECTION_NAME)
        count = collection.count()
        if count > 0:
            logger.info(f"Collection '{COLLECTION_NAME}' chargée: {count} chunks")
            vector_store = ChromaVectorStore(chroma_collection=collection)
            with _init_lock:
                _index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
            return _index
        else:
            raise ValueError(f"Collection '{COLLECTION_NAME}' est vide (0 chunks)")
    except Exception as e:
        raise RuntimeError(
            f"Impossible de charger la collection ChromaDB '{COLLECTION_NAME}' "
            f"depuis {CHROMA_PATH}. Indexez d'abord le corpus via Domicil-IA "
            f"puis copiez chroma_db_CathIA/ dans data/chroma_db/. Erreur: {e}"
        )


def get_index() -> VectorStoreIndex:
    """Retourne l'index (le crée si nécessaire)."""
    global _index
    if _index is None:
        with _init_lock:
            if _index is None:
                _index = init_index()
    return _index


# === Condensation de question ===

async def condense_question(question: str, chat_history: list, max_exchanges: int = 3) -> str:
    """Reformule une question de suivi en question autonome."""
    if not chat_history:
        return question

    max_messages = max_exchanges * 2
    recent = chat_history[-max_messages:]

    history_lines = []
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        content_truncated = content[:500] + "..." if len(content) > 500 else content
        role_label = "Utilisateur" if role == "user" else "Assistant"
        history_lines.append(f"{role_label}: {content_truncated}")

    prompt = CONDENSE_QUESTION_PROMPT.format(
        chat_history="\n".join(history_lines),
        question=question,
    )

    try:
        response = await asyncio.to_thread(Settings.llm.complete, prompt)
        condensed = response.text.strip()
        if condensed.startswith('"') and condensed.endswith('"'):
            condensed = condensed[1:-1]
        if condensed.lower().startswith("question reformulée:"):
            condensed = condensed[20:].strip()
        if condensed and len(condensed) > 5:
            logger.info(f"Question condensée: '{question[:40]}...' → '{condensed[:40]}...'")
            return condensed
    except Exception as e:
        logger.warning(f"Condensation échouée: {e}")

    return question


# === Query streaming ===

async def query_stream(
    question: str,
    chat_history: list = None,
    age_group: str = None,
    knowledge_level: str = None,
    response_length: str = None,
):
    """
    Générateur SSE : interroge le RAG et yield des événements JSON.

    Yields:
        data: {"type": "chunk", "content": "..."}
        data: {"type": "sources", "sources_with_scores": [...]}
        data: {"type": "done"}
    """
    try:
        index = get_index()

        # Condenser si historique
        effective_question = question
        if chat_history:
            effective_question = await condense_question(question, chat_history)

        # System prompt personnalisé
        system_prompt = build_system_prompt(age_group, knowledge_level, response_length)

        # Template QA
        qa_template_str = f"""{system_prompt}

Documents de contexte :
{{context_str}}

---
QUESTION : {{query_str}}

Réponds en te basant uniquement sur les documents fournis. Cite tes sources."""

        # Query engine avec streaming
        query_engine = index.as_query_engine(
            similarity_top_k=SIMILARITY_TOP_K,
            streaming=True,
            text_qa_template=PromptTemplate(qa_template_str),
        )

        streaming_response = await asyncio.to_thread(query_engine.query, effective_question)

        # Stream les chunks
        for text in streaming_response.response_gen:
            chunk = json.dumps({"type": "chunk", "content": text})
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0)

        # Extraire les sources
        sources_with_scores = []
        seen = set()

        if hasattr(streaming_response, "source_nodes"):
            for node in streaming_response.source_nodes[:CONTEXT_TOP_K]:
                meta = getattr(node.node, "metadata", {})
                file_path = meta.get("file_path", "")
                file_name = meta.get("file_name", Path(file_path).name if file_path else "")

                if file_name and file_name not in seen:
                    seen.add(file_name)
                    score = getattr(node, "score", 0.0) or 0.0
                    sources_with_scores.append({
                        "file_name": file_name,
                        "file_path": file_path,
                        "relative_path": meta.get("relative_path", ""),
                        "source_folder": meta.get("source_folder", ""),
                        "score": round(score, 4),
                    })

        sources_with_scores.sort(key=lambda x: x["score"], reverse=True)

        sources_data = json.dumps({
            "type": "sources",
            "sources_with_scores": sources_with_scores,
        })
        yield f"data: {sources_data}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"RAG streaming error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'content': 'Une erreur est survenue lors du traitement de votre question.'})}\n\n"


def get_collection_stats() -> dict:
    """Retourne les stats de la collection ChromaDB."""
    try:
        client = _get_chroma_client()
        collection = client.get_collection(COLLECTION_NAME)
        return {
            "collection": COLLECTION_NAME,
            "chunks": collection.count(),
            "model": OLLAMA_MODEL,
            "embedding_model": EMBEDDING_MODEL,
        }
    except Exception as e:
        logger.warning(f"Impossible de lire les stats ChromaDB: {e}")
        return {
            "collection": COLLECTION_NAME,
            "chunks": 0,
            "model": OLLAMA_MODEL,
            "embedding_model": EMBEDDING_MODEL,
        }
