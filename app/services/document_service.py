"""
DocumentService — Phase 3 complete implementation.

Implements:
  - Text extraction (PDF via PyMuPDF, TXT)
  - Semantic chunking (no overlap — your architecture decision)
  - Conditional metadata (cross-ref fields only on chunks that need them)
  - Section ID tagging on heading chunks (enables precise second-hop lookup)
  - Dual-model indexing into two ChromaDB collections for comparison
  - Document-level metadata persisted as JSON
"""
import asyncio
import json
import os
from datetime import datetime

import chromadb

from app.config import Settings
from app.core.chunker import extract_text, semantic_chunk, RawChunk
from app.core.cross_ref import detect_cross_references, detect_section_heading
from app.core.embeddings import EmbeddingClient
from app.models.document import DocumentMetadataResponse, DocumentStatus


# ── Metadata store ─────────────────────────────────────────────────────────────
# Simple JSON file per document — ChromaDB is for vectors, not document records.

def _meta_path(document_id: str, persist_dir: str) -> str:
    meta_dir = os.path.join(persist_dir, "doc_metadata")
    os.makedirs(meta_dir, exist_ok=True)
    return os.path.join(meta_dir, f"{document_id}.json")


def _save_metadata(document_id: str, data: dict, persist_dir: str) -> None:
    with open(_meta_path(document_id, persist_dir), "w") as f:
        json.dump(data, f, default=str)


def _load_metadata(document_id: str, persist_dir: str) -> dict | None:
    path = _meta_path(document_id, persist_dir)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _delete_metadata(document_id: str, persist_dir: str) -> bool:
    path = _meta_path(document_id, persist_dir)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


# ── Chunk metadata builder ─────────────────────────────────────────────────────

def _build_chunk_metadata(
    chunk: RawChunk,
    chunk_index: int,
    document_id: str,
    filename: str,
) -> dict:
    """
    Build ChromaDB metadata dict for a single chunk.

    Applies your conditional metadata strategy:
      - Base fields: always present
      - section_id: only if chunk starts with a section heading
      - has_cross_ref + targets: only if chunk contains legal cross-ref language
    """
    meta: dict = {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "filename": filename,
        "page_number": chunk.page_number,
    }

    # Detect if this chunk IS a section heading → store section_id
    # so second-hop retrieval can locate it directly by filter
    heading = detect_section_heading(chunk.text)
    if heading.is_section_heading and heading.section_id:
        meta["section_id"] = heading.section_id

    # Detect if this chunk REFERENCES another section → store cross-ref info
    # This is your conditional metadata — only added when actually needed
    cross_ref = detect_cross_references(chunk.text)
    if cross_ref.has_cross_ref:
        meta["has_cross_ref"] = True
        meta["cross_ref_trigger_types"] = ",".join(cross_ref.trigger_types)
        meta["cross_ref_targets"] = ",".join(cross_ref.targets)

    return meta


# ── Service ────────────────────────────────────────────────────────────────────

class DocumentService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._embed_client = EmbeddingClient(settings)

        # Single ChromaDB collection dynamically named based on the active local model
        self._chroma = chromadb.PersistentClient(
            path=settings.chroma_persist_directory
        )
        model_suffix = settings.embedding_model.replace("/", "_").replace(".", "_")
        self._collection = self._chroma.get_or_create_collection(
            f"{settings.chroma_collection_name}_{model_suffix}"
        )

    async def process_and_index(
        self,
        document_id: str,
        filename: str,
        contents: bytes,
        extension: str,
    ) -> int:
        """
        Full pipeline: extract → chunk → embed (local model) → index → save metadata.
        Returns chunk count.
        """
        # Step 1: Extract text with page numbers
        pages = await asyncio.to_thread(extract_text, contents, extension)

        # Step 2: Semantic chunking (no overlap, meaning-based splits)
        raw_chunks = await asyncio.to_thread(
            semantic_chunk, pages, self.settings
        )

        if not raw_chunks:
            raise ValueError("Document produced no chunks — it may be empty or unreadable.")

        chunk_texts = [c.text for c in raw_chunks]

        # Step 3: Embed with the active local model
        embeddings = await self._embed_client.embed_batch(chunk_texts)

        # Step 4: Build metadata for each chunk (your conditional schema)
        metadatas = [
            _build_chunk_metadata(chunk, idx, document_id, filename)
            for idx, chunk in enumerate(raw_chunks)
        ]

        ids = [f"{document_id}_chunk_{i}" for i in range(len(raw_chunks))]

        # Step 5: Upsert into the ChromaDB collection
        def _upsert() -> None:
            vectors = [r.vector for r in embeddings]
            self._collection.upsert(
                ids=ids,
                embeddings=vectors,
                documents=chunk_texts,
                metadatas=metadatas,
            )

        await asyncio.to_thread(_upsert)

        # Step 6: Persist document-level metadata
        _save_metadata(
            document_id,
            {
                "document_id": document_id,
                "filename": filename,
                "status": DocumentStatus.READY,
                "chunk_count": len(raw_chunks),
                "uploaded_at": datetime.utcnow().isoformat(),
                "file_size_bytes": len(contents),
            },
            self.settings.chroma_persist_directory,
        )

        return len(raw_chunks)

    async def get_metadata(self, document_id: str) -> DocumentMetadataResponse | None:
        data = await asyncio.to_thread(
            _load_metadata, document_id, self.settings.chroma_persist_directory
        )
        if data is None:
            return None
        return DocumentMetadataResponse(**data)

    async def delete(self, document_id: str) -> bool:
        """Delete vectors from collection + metadata file."""
        data = await asyncio.to_thread(
            _load_metadata, document_id, self.settings.chroma_persist_directory
        )
        if data is None:
            return False

        chunk_count = data.get("chunk_count", 0)
        ids = [f"{document_id}_chunk_{i}" for i in range(chunk_count)]

        def _delete_from_chroma() -> None:
            try:
                self._collection.delete(ids=ids)
            except Exception:
                pass   # IDs may be partially indexed — best effort

        await asyncio.to_thread(_delete_from_chroma)
        await asyncio.to_thread(
            _delete_metadata, document_id, self.settings.chroma_persist_directory
        )
        return True
