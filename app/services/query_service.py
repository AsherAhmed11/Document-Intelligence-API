"""
QueryService — Gemini-powered RAG pipeline.

Architecture:
  - Embed question with gemini-embedding-001 (same model as documents)
  - Retrieve top-k chunks from ChromaDB with cosine similarity filter
  - Multi-hop: if LLM detects a cross-reference, fetch that section and re-answer
  - Gemini Flash returns structured JSON natively
  - General knowledge fallback: if question isn't answered by document context,
    LLM provides an answer using general knowledge with a clear disclaimer.
"""
import os
import json
import asyncio
import re
import chromadb
from app.config import Settings
from app.models.query import QueryResponse, Citation
from app.core.embeddings import EmbeddingClient


SYSTEM_PROMPT = """You are an expert Q&A assistant for legal, business, and general documents.
You will be provided with numbered context chunks from a document.

RULES:
1. PRIMARY: If the question CAN be answered using the provided context chunks, answer comprehensively using the context and cite chunk numbers using [N] format (e.g. [1], [2]).
2. GENERAL KNOWLEDGE FALLBACK: If the provided context chunks DO NOT contain sufficient information to answer the question, answer the question accurately using your general knowledge, but clearly state in your answer that it is based on general knowledge because the specific details were not found in the uploaded document. In this fallback case, set answer_found=false and citations=[].
3. CROSS-REFERENCES: If the context references another section (e.g., "see Section 3.2"), set needs_followup=true and list section IDs in refs_to_fetch.
4. Return ONLY valid JSON matching this schema:

{
  "answer": "Your detailed answer here (with inline [N] citations if using document context)",
  "citations": [0, 1],
  "needs_followup": false,
  "refs_to_fetch": [],
  "answer_found": true
}"""


GENERAL_KNOWLEDGE_SYSTEM_PROMPT = """You are an expert Q&A assistant.
Answer the user's question accurately using your general knowledge.
At the beginning of your answer, explicitly note that this response is based on general knowledge because the specific details were not found in the uploaded document.

CRITICAL REQUIREMENT FOR GENERAL KNOWLEDGE:
At the bottom of your answer, you MUST provide a dedicated "General References & Verification Sources:" section listing 2-3 standard, reputable reference sources (such as Cornell Law School Legal Information Institute, Black's Law Dictionary, official documentation, or standard legal/technical treatises) so the user can independently verify the answer.

Return ONLY valid JSON matching this schema:
{
  "answer": "Note: This response is based on general knowledge as relevant details were not found in the document.\\n\\n[Your detailed answer]\\n\\nGeneral References & Verification Sources:\\n1. [Source 1 Name / Reference]\\n2. [Source 2 Name / Reference]",
  "citations": [],
  "needs_followup": false,
  "refs_to_fetch": [],
  "answer_found": false
}"""


class QueryService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._embed_client = EmbeddingClient(settings)

        # ChromaDB client
        self._chroma = chromadb.PersistentClient(
            path=settings.chroma_persist_directory
        )
        model_suffix = settings.embedding_model.replace("/", "_").replace(".", "_")
        self._collection = self._chroma.get_or_create_collection(
            f"{settings.chroma_collection_name}_{model_suffix}",
            metadata={"hnsw:space": "cosine"},
        )

        # Gemini LLM client (google-genai SDK)
        if settings.llm_provider == "gemini":
            from google import genai
            from google.genai import types as gentypes
            self._gemini_client = genai.Client(api_key=settings.gemini_api_key)
            self._gentypes = gentypes
            self._llm_provider = "gemini"
        else:
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
        """Check if document_id has been indexed."""
        meta_path = os.path.join(
            self.settings.chroma_persist_directory,
            "doc_metadata",
            f"{document_id}.json"
        )
        return os.path.exists(meta_path)

    async def _call_llm(self, context_str: str, question: str, system_prompt: str = SYSTEM_PROMPT) -> dict:
        """Call the LLM and return a parsed JSON dict."""
        prompt = f"{system_prompt}\n\nContext:\n{context_str}\n\nQuestion: {question}"

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
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"}
            ]
            resp = await self._llm.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content or ""

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(0)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "answer": raw,
                "citations": [],
                "needs_followup": False,
                "refs_to_fetch": [],
                "answer_found": False,
            }

    async def _general_knowledge_fallback(self, question: str) -> dict:
        """Answer question using LLM general knowledge when document has no matching information."""
        prompt = f"{GENERAL_KNOWLEDGE_SYSTEM_PROMPT}\n\nQuestion: {question}"

        if self._llm_provider == "gemini":
            _model = self.settings.llm_model
            _config = self._gentypes.GenerateContentConfig(
                temperature=0.2,
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
            resp = await self._llm.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": GENERAL_KNOWLEDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {question}"}
                ],
                temperature=0.2,
            )
            raw = resp.choices[0].message.content or ""

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(0)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "answer": f"Note: Based on general knowledge:\n\n{raw}",
                "citations": [],
                "needs_followup": False,
                "refs_to_fetch": [],
                "answer_found": False,
            }

    async def answer(
        self,
        document_id: str,
        question: str,
        top_k: int = 6,
    ) -> QueryResponse:
        """Core RAG pipeline: embed → retrieve → (optional cross-ref hop) → generate → cite / fallback."""

        # Direct General Knowledge query (no document selected/uploaded)
        if document_id in ["general", "none", ""]:
            gk_res = await self._general_knowledge_fallback(question)
            return QueryResponse(
                document_id="general",
                question=question,
                answer=gk_res.get("answer", "No answer could be generated."),
                citations=[],
                answer_found=False,
            )

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

        # If document has no vectors or zero results, use general knowledge
        if not documents_list:
            gk_res = await self._general_knowledge_fallback(question)
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer=gk_res.get("answer", "No answer could be generated."),
                citations=[],
                answer_found=False,
            )

        scored_chunks = []
        for doc, meta, dist, cid in zip(documents_list, metadatas, distances, ids):
            similarity = max(0.0, 1.0 - dist)
            scored_chunks.append({"id": cid, "text": doc, "metadata": meta, "score": similarity})

        max_score = max(c["score"] for c in scored_chunks)

        # If similarity is extremely low (< 0.10), use General Knowledge fallback directly
        if max_score < 0.10:
            gk_res = await self._general_knowledge_fallback(question)
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer=gk_res.get("answer", "No relevant context found in document."),
                citations=[],
                answer_found=False,
            )

        # Context accumulation
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

        # Quick LLM call — max 1 hop if cross-reference requested
        context_str = fmt_context(context_items)
        args = await self._call_llm(context_str, question)

        needs_followup = args.get("needs_followup", False)
        refs_to_fetch = args.get("refs_to_fetch", [])

        if needs_followup and refs_to_fetch:
            fetched = []
            for ref in refs_to_fetch[:2]:  # Limit to 2 refs max for speed
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
                context_str = fmt_context(context_items)
                args = await self._call_llm(context_str, question)

        # Build response
        answer_found = args.get("answer_found", True)
        raw_answer = args.get("answer", "")

        # If LLM indicates the context does not contain the answer, perform General Knowledge fallback with verification sources
        if not answer_found or "unable to answer" in raw_answer.lower() or "does not contain" in raw_answer.lower():
            gk_res = await self._general_knowledge_fallback(question)
            raw_answer = gk_res.get("answer", raw_answer)
            answer_found = False

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

        def remap(m):
            return f"[{index_mapping.get(int(m.group(1)), m.group(1))}]"

        final_answer = re.sub(r'\[(\d+)\]', remap, raw_answer)
        if ref_lines:
            final_answer += "\n\nReferences:\n" + "\n".join(ref_lines)

        return QueryResponse(
            document_id=document_id,
            question=question,
            answer=final_answer,
            citations=final_citations,
            answer_found=answer_found,
        )
