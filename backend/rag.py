"""
RAG over the candidate's resume.

- Embeddings: open-source Hugging Face model, run locally (no API key).
- Vector store: in-memory Chroma, one collection per interview room.
  Nothing is written to disk; the collection is deleted when the session ends.
"""

import os
import re
from functools import lru_cache
from io import BytesIO
from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# bge models recommend this prefix for *queries* (not for documents).
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Load the embedding model once per process (first call downloads it)."""
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF. Returns '' if there is no text layer."""
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _collection_name(room: str) -> str:
    # Chroma: 3-63 chars, [a-zA-Z0-9._-], must start/end alphanumeric.
    return re.sub(r"[^a-zA-Z0-9._-]", "-", room)[:63]


def build_resume_store(
    room: str,
    resume_text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> Chroma:
    """Chunk the resume text and index it in an in-memory collection for `room`."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks: List[Document] = splitter.create_documents([resume_text])
    if not chunks:
        raise ValueError("Resume produced no text chunks")

    # No persist_directory => ephemeral, in-memory client.
    return Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        collection_name=_collection_name(room),
    )


def deduplicate_documents(docs: List[Document]) -> List[Document]:
    """Remove near-duplicate chunks caused by overlap (first-150-chars fingerprint)."""
    seen = set()
    unique_docs = []
    for doc in docs:
        fingerprint = " ".join(doc.page_content[:150].strip().split())
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique_docs.append(doc)
    return unique_docs


def query_store(store: Chroma, query: str, k: int = 4, deduplicate: bool = True) -> str:
    """Semantic search over a resume store. Returns concatenated chunks."""
    retrieve_k = int(k * 1.5) if deduplicate else k
    docs = store.similarity_search(_BGE_QUERY_PREFIX + query, k=retrieve_k)
    if deduplicate:
        docs = deduplicate_documents(docs)[:k]
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def delete_store(store: Chroma) -> None:
    store.delete_collection()
