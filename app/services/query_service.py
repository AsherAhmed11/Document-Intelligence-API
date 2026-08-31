"""
QueryService — Gemini-powered RAG pipeline.

Architecture:
  - Embed question with text-embedding-004 (same model as documents)
  - Retrieve top-k chunks from ChromaDB with cosine similarity filter
  - Multi-hop: if LLM detects a cross-reference, fetch that section and re-answer
  - Gemini 2.0 Flash returns structured JSON natively (no tool-calling needed)
  - Citations are extracted from the LLM's JSON response and mapped to source chunks
"""
import os
import json
import asyncio
import re
import chromadb
from app.config import Settings
from app.models.query import QueryResponse, Citation
from app.core.embeddings import EmbeddingClient


SYSTEM_PROMPT = """You are an expert Q&A assistant for analyzing legal and business documents.
Answer the user's question using ONLY the numbered context chunks provided below.

RULES:
1. Answer comprehensively and clearly.
2. Every claim MUST cite the context chunk index using [N] format (e.g. [0], [1]).
3. If the context has a cross-reference (e.g. "see Section 3.2", "pursuant to Annex A") critical to answering, set needs_followup=true and list the refs in refs_to_fetch.
4. If the context doesn't contain enough information, set answer_found=false.
5. Return ONLY valid JSON in this exact schema:

{
  "answer": "Your answer text with inline [N] citations",
  "citations": [0, 2],
  "needs_followup": false,
  "refs_to_fetch": [],
  "answer_found": true
}"""


class QueryService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._embed_client = EmbeddingClient(settings)

        # ChromaDB — same collection naming as DocumentService
        self._chroma = chromadb.PersistentClient(
            path=settings.chroma_persist_directory
        )
        model_suffix = settings.embedding_model.replace("/", "_").replace(".", "_")
        self._collection = self._chroma.get_or_create_collection(
            f"{settings.chroma_collection_name}_{model_suffix}",
            metadata={"hnsw:space": "cosine"},
        )

        # Gemini LLM client (new google-genai SDK)
        if settings.llm_provider == "gemini":
            from google import genai
            from google.genai import types as gentypes
            self._gemini_client = genai.Client(api_key=settings.gemini_api_key)
            self._gentypes = gentypes
            self._llm_provider = "gemini"
        else:
            # Fallback: OpenAI-compatible
            from openai import AsyncOpenAI
            if settings.llm_provider == "huggingface":
                self._llm = AsyncOpenAI(
                    api_key=settings.hf_api_key,
                    base_url="https://router.huggingface.co/v1"
                )
            else:
                self._llm = AsyncOpenAI(api_key=settings.openai_api_key)
            self._llm_provider = "openai"

    async def document_exists(self, document_id: str) -> bool:
        """Check if document_id has been indexed (metadata file exists)."""
        meta_path = os.path.join(
            self.settings.chroma_persist_directory,
            "doc_metadata",
            f"{document_id}.json"
        )
        return os.path.exists(meta_path)

    async def _call_llm(self, context_str: str, question: str) -> dict:
        """Call the LLM and return a parsed JSON dict."""
        prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context_str}\n\nQuestion: {question}"

        if self._llm_provider == "gemini":
            _model = self.settings.llm_model
            _config = self._gentypes.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            )
            response = await asyncio.to_thread(
                lambda: self._gemini_client.models.generate_content(
                    model=_model,
                    contents=prompt,
                    config=_config,
                )
            )
            raw = response.text.strip() if response.text else ""
        else:
            # OpenAI-compatible fallback
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"}
            ]
            resp = await self._llm.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content or ""

        # Extract JSON — strip markdown code fences if present
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(0)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Graceful fallback
            return {
                "answer": raw,
                "citations": [],
                "needs_followup": False,
                "refs_to_fetch": [],
                "answer_found": bool(raw.strip()),
            }

    async def answer(
        self,
        document_id: str,
        question: str,
        top_k: int,
    ) -> QueryResponse:
        """Core RAG pipeline: embed → retrieve → (optional multi-hop) → generate → cite."""

        # Step 1: Embed the question
        question_emb = await self._embed_client.embed(question)

        # Step 2: Vector search ChromaDB
        def _query_chroma():
            return self._collection.query(
                query_embeddings=[question_emb.vector],
                n_results=top_k,
                where={"document_id": document_id},
                include=["documents", "metadatas", "distances"],
            )

        results = await asyncio.to_thread(_query_chroma)

        documents_list = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        if not documents_list:
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer="I could not find any context in the document to answer your question.",
                citations=[],
                answer_found=False,
            )

        # Score filtering — ChromaDB cosine distance: 0=identical, 1=orthogonal
        # similarity = 1.0 - distance
        scored_chunks = []
        for doc, meta, dist, cid in zip(documents_list, metadatas, distances, ids):
            similarity = max(0.0, 1.0 - dist)
            scored_chunks.append({"id": cid, "text": doc, "metadata": meta, "score": similarity})

        max_score = max(c["score"] for c in scored_chunks)
        # Cosine threshold: 0.3 means 30% similarity — reasonable for short queries vs long docs
        if max_score < 0.15:  # Very permissive: only reject truly unrelated content
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer="I'm sorry — the document doesn't appear to contain relevant information for this question.",
                citations=[],
                answer_found=False,
            )

        # Multi-hop context accumulation
        context_items = []
        seen_ids: set[str] = set()

        def add_chunks(chunks):
            for c in chunks:
                if c["id"] not in seen_ids:
                    seen_ids.add(c["id"])
                    context_items.append(c)

        add_chunks(scored_chunks)

        def fmt_context(items):
            parts = []
            for i, item in enumerate(items):
                meta = item["metadata"]
                page = meta.get("page_number", "?")
                sec = meta.get("section_id", "")
                prefix = f"[{i}] Page {page}" + (f", §{sec}" if sec else "")
                parts.append(f"{prefix}:\n{item['text']}")
            return "\n\n".join(parts)

        # LLM loop (max 2 hops for cross-reference resolution)
        args: dict = {}
        for hop in range(3):
            context_str = fmt_context(context_items)
            args = await self._call_llm(context_str, question)

            needs_followup = args.get("needs_followup", False)
            refs_to_fetch = args.get("refs_to_fetch", [])

            if needs_followup and refs_to_fetch and hop < 2:
                fetched = []
                for ref in refs_to_fetch:
                    def _get_section(ref_id):
                        try:
                            return self._collection.get(
                                where={"$and": [
                                    {"document_id": {"$eq": document_id}},
                                    {"section_id": {"$eq": ref_id}},
                                ]}
                            )
                        except Exception:
                            return {}

                    sec_res = await asyncio.to_thread(_get_section, ref)
                    for doc, meta, cid in zip(
                        sec_res.get("documents", []),
                        sec_res.get("metadatas", []),
                        sec_res.get("ids", []),
                    ):
                        fetched.append({"id": cid, "text": doc, "metadata": meta, "score": 1.0})
                if fetched:
                    add_chunks(fetched)
                    continue
            break

        # Build final response
        answer_found = args.get("answer_found", True)
        raw_answer = args.get("answer", "")
        cited_indices = sorted({int(i) for i in re.findall(r'\[(\d+)\]', raw_answer)})

        final_citations = []
        index_mapping: dict[int, int] = {}
        ref_lines = []

        for ref_num, ctx_idx in enumerate(cited_indices, 1):
            index_mapping[ctx_idx] = ref_num
            if 0 <= ctx_idx < len(context_items):
                item = context_items[ctx_idx]
                meta = item["metadata"]
                page = meta.get("page_number", "?")
                sec = meta.get("section_id", "")
                sec_str = f", §{sec}" if sec else ""
                excerpt_preview = item["text"][:120].replace("\n", " ").strip()
                ref_lines.append(f"[{ref_num}] Page {page}{sec_str} — \"{excerpt_preview}...\"")
                final_citations.append(Citation(
                    chunk_index=meta.get("chunk_index", ctx_idx),
                    page_number=meta.get("page_number"),
                    excerpt=item["text"],
                    relevance_score=round(item["score"], 4),
                ))

        # Renumber inline citations [0] → [1], [2] → [2], etc.
        def remap(m):
            return f"[{index_mapping.get(int(m.group(1)), m.group(1))}]"

        final_answer = re.sub(r'\[(\d+)\]', remap, raw_answer)
        if ref_lines:
            final_answer += "\n\nReferences:\n" + "\n".join(ref_lines)

        if not answer_found:
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer=raw_answer or "I could not find enough relevant information to answer your question.",
                citations=[],
                answer_found=False,
            )

        return QueryResponse(
            document_id=document_id,
            question=question,
            answer=final_answer,
            citations=final_citations,
            answer_found=True,
        )
