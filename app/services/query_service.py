"""
QueryService — stub for you to implement.

This is where your retrieval and Q&A architecture lives:
  - How many chunks do you retrieve? (top_k from the request, but you can override)
  - What retrieval method? (cosine similarity, MMR, hybrid?)
  - How do you format the context for the LLM prompt?
  - How do you prevent hallucination when the answer isn't in the document?
  - How do you extract citations from the retrieved chunks?

These are YOUR decisions. Do not let AI write this logic.
"""
import os
import json
import asyncio
import re
import chromadb
from openai import AsyncOpenAI
from app.config import Settings
from app.models.query import QueryResponse, Citation
from app.core.embeddings import EmbeddingClient


class QueryService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._embed_client = EmbeddingClient(settings)

        # Initialize ChromaDB client
        self._chroma = chromadb.PersistentClient(
            path=settings.chroma_persist_directory
        )
        model_suffix = settings.embedding_model.replace("/", "_").replace(".", "_")
        self._collection = self._chroma.get_or_create_collection(
            f"{settings.chroma_collection_name}_{model_suffix}"
        )

        # Initialize LLM Client
        if settings.llm_provider == "bytez":
            self.openai_client = AsyncOpenAI(
                api_key=settings.bytez_api_key,
                base_url="https://api.bytez.com/models/v2/openai/v1"
            )
        else:
            self.openai_client = AsyncOpenAI(
                api_key=settings.openai_api_key
            )

    async def document_exists(self, document_id: str) -> bool:
        """
        Check whether document_id has been indexed in ChromaDB by verifying
        its metadata file exists.
        """
        meta_path = os.path.join(
            self.settings.chroma_persist_directory,
            "doc_metadata",
            f"{document_id}.json"
        )
        return os.path.exists(meta_path)

    async def answer(
        self,
        document_id: str,
        question: str,
        top_k: int,
    ) -> QueryResponse:
        """
        Core RAG pipeline with two-stage no-answer detection, query routing,
        and multi-hop cross-reference lookup.
        """
        # Step 1: Embed the question
        question_emb = await self._embed_client.embed(question)

        # Step 2: Vector search ChromaDB
        def _query_chroma():
            return self._collection.query(
                query_embeddings=[question_emb.vector],
                n_results=top_k,
                where={"document_id": document_id},
                include=["documents", "metadatas", "distances"]
            )
        results = await asyncio.to_thread(_query_chroma)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        if not documents:
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer="I could not find any context in the document to answer your question.",
                citations=[],
                answer_found=False
            )

        # Stage 1 Score check: convert distances to similarity scores (similarity = 1.0 - distance)
        max_score = 0.0
        scored_chunks = []
        for idx, (doc, meta, dist, cid) in enumerate(zip(documents, metadatas, distances, ids)):
            score = 1.0 - dist
            max_score = max(max_score, score)
            scored_chunks.append({
                "id": cid,
                "text": doc,
                "metadata": meta,
                "score": score
            })

        # Threshold check:
        if max_score < 0.40:
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer="I'm sorry, but I could not find any sufficiently relevant information in the document to answer your question.",
                citations=[],
                answer_found=False
            )

        # Step 3: Context management and follow-up loops
        context_items = []
        seen_ids = set()

        def add_chunks_to_context(chunks):
            for chunk in chunks:
                cid = chunk["id"]
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    context_items.append(chunk)

        add_chunks_to_context(scored_chunks)

        def format_context_string(items):
            formatted_parts = []
            for idx, item in enumerate(items):
                meta = item["metadata"]
                page = meta.get("page_number", "Unknown")
                sec = meta.get("section_id", None)
                prefix = f"[{idx}] Page {page}"
                if sec:
                    prefix += f", Section {sec}"
                formatted_parts.append(f"{prefix}:\n{item['text']}")
            return "\n\n".join(formatted_parts)

        # Setup system prompt and function calling tools
        system_prompt = (
            "You are an expert Q&A system for analyzing complex legal and business documents.\n"
            "Your task is to answer the user's question using ONLY the provided numbered context chunks.\n"
            "Guidelines:\n"
            "1. Answer the question comprehensively and clearly.\n"
            "2. Ground every single claim in the context. Use inline citations in the format '[N]' (where N is the 0-based chunk index, e.g. [0], [1], [2]) to reference the source chunk(s) supporting your claim.\n"
            "3. If the context does not contain enough information to answer the question, or if you cannot find the answer, return needs_followup=False and set answer_found=False.\n"
            "4. If the context contains a cross-reference (e.g. 'pursuant to Section 3.2', 'see Annex A') that is critical to fully answering the question, and that referenced section is NOT already in the provided context, you must set needs_followup=True and include the referenced section IDs (e.g. ['3.2']) in refs_to_fetch.\n"
            "5. ALWAYS call the submit_answer function to return your response."
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "submit_answer",
                    "description": "Submit the answer or request additional sections if a cross-reference is missing.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                                "description": "The answer to the question with inline citations (e.g. [1]). Empty or draft if needs_followup is true."
                            },
                            "citations": {
                                "type": "array",
                                "items": {
                                    "type": "integer"
                                },
                                "description": "List of context indices (e.g. [0, 2]) that support the answer."
                            },
                            "needs_followup": {
                                "type": "boolean",
                                "description": "True if additional cross-referenced sections are needed to complete the answer."
                            },
                            "refs_to_fetch": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "List of section identifiers (e.g., ['3.2', 'Annex A']) that need to be retrieved."
                            },
                            "answer_found": {
                                "type": "boolean",
                                "description": "Set to False if the context does not contain enough information to answer."
                            }
                        },
                        "required": ["answer", "citations", "needs_followup", "refs_to_fetch", "answer_found"]
                    }
                }
            }
        ]

        hop_count = 0
        max_hops = 2
        args = {}

        # Loop for multi-hop retrieval
        while hop_count <= max_hops:
            context_str = format_context_string(context_items)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"}
            ]

            response = await self.openai_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "submit_answer"}},
                temperature=0.0
            )

            tool_call = response.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)

            needs_followup = args.get("needs_followup", False)
            refs_to_fetch = args.get("refs_to_fetch", [])
            answer_found = args.get("answer_found", True)

            if needs_followup and refs_to_fetch and hop_count < max_hops:
                fetched_chunks = []
                for ref in refs_to_fetch:
                    def _query_section(ref_id):
                        try:
                            # Try querying by section_id metadata filter
                            return self._collection.get(
                                where={"$and": [
                                    {"document_id": {"$eq": document_id}},
                                    {"section_id": {"$eq": ref_id}}
                                ]}
                            )
                        except Exception:
                            try:
                                return self._collection.get(
                                    where={"section_id": ref_id}
                                )
                            except Exception:
                                return {}

                    sec_results = await asyncio.to_thread(_query_section, ref)
                    if sec_results:
                        sec_docs = sec_results.get("documents", [])
                        sec_metas = sec_results.get("metadatas", [])
                        sec_ids = sec_results.get("ids", [])
                        for doc, meta, cid in zip(sec_docs, sec_metas, sec_ids):
                            fetched_chunks.append({
                                "id": cid,
                                "text": doc,
                                "metadata": meta,
                                "score": 1.0  # direct metadata match
                            })

                if fetched_chunks:
                    add_chunks_to_context(fetched_chunks)
                    hop_count += 1
                    continue

            break

        # Stage 2 check & Final Response Builder
        answer_found = args.get("answer_found", True)
        if not answer_found:
            return QueryResponse(
                document_id=document_id,
                question=question,
                answer=args.get("answer") or "I could not find enough relevant information in the document to answer your question.",
                citations=[],
                answer_found=False
            )

        # Parse and clean citations
        raw_answer = args.get("answer", "")
        citation_pattern = re.compile(r'\[(\d+)\]')
        cited_indices = sorted(list({int(m) for m in citation_pattern.findall(raw_answer)}))

        final_citations = []
        index_mapping = {}
        ref_lines = []

        for ref_num, context_idx in enumerate(cited_indices, 1):
            index_mapping[context_idx] = ref_num
            if 0 <= context_idx < len(context_items):
                item = context_items[context_idx]
                meta = item["metadata"]
                page = meta.get("page_number", "?")
                sec = meta.get("section_id", None)
                sec_str = f", §{sec}" if sec else ""
                
                # Format a clean preview of the excerpt
                excerpt_clean = item["text"][:100].replace('\n', ' ').strip()
                ref_lines.append(f"[{ref_num}] Page {page}{sec_str} — \"{excerpt_clean}...\"")

                final_citations.append(
                    Citation(
                        chunk_index=meta.get("chunk_index", 0),
                        page_number=meta.get("page_number", None),
                        excerpt=item["text"],
                        relevance_score=item["score"]
                    )
                )

        # Re-map the inline citation indexes to match the references list order
        def replace_citations(match):
            idx = int(match.group(1))
            return f"[{index_mapping.get(idx, match.group(1))}]"

        final_answer = citation_pattern.sub(replace_citations, raw_answer)

        # Append references block to final answer
        if ref_lines:
            references_block = "\n\nReferences:\n" + "\n".join(ref_lines)
            final_answer += references_block

        return QueryResponse(
            document_id=document_id,
            question=question,
            answer=final_answer,
            citations=final_citations,
            answer_found=True
        )
