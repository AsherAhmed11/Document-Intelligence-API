# Delegation Plan — Document Intelligence API

## Guiding Philosophy

> **AI is a force multiplier, not a replacement for thinking.**
> Delegate the *repetitive and mechanical*. Own the *decisions that make you hireable*.

The goal isn't to finish fast — it's to **understand deeply** so you can defend every choice in an interview or on the job.

---

## The Delegation Matrix

| Task | Delegate to AI? | Reason |
|---|---|---|
| FastAPI project scaffold (folder structure, main.py, router setup) | ✅ Yes | Pure boilerplate; no thinking required |
| Pydantic models for request/response schemas | ✅ Yes | Mechanical, tedious, error-prone to type out |
| ChromaDB client setup & collection management code | ✅ Yes | API familiarity, not architecture |
| OpenAI embeddings API call boilerplate | ✅ Yes | Just wrapping an SDK |
| Error handling patterns (HTTPException, try/except) | ✅ Yes | Standard FastAPI patterns |
| Dockerfile & Railway deployment config | ✅ Yes | DevOps config, not your learning objective |
| Writing unit/integration tests | ✅ Yes | Accelerates coverage |
| Reading/summarizing ChromaDB or LangChain docs | ✅ Yes | Saves hours of parsing docs |
| Cross-reference detection boilerplate (regex, keyword scan) | ✅ Yes | Implementation of YOUR dictionary design |
| Dual embedding client (AsyncOpenAI wrapping) | ✅ Yes | SDK boilerplate, strategy is yours |
| **Chunking strategy design** | ❌ No | This IS your architecture decision |
| **Overlap decision & justification** | ❌ No | Must reason from first principles |
| **Embedding model selection** | ❌ No | Requires empirical comparison on your docs |
| **Retrieval strategy (top-k, hybrid, iterative)** | ❌ No | Shows you understand RAG tradeoffs |
| **Cross-reference keyword dictionary** | ❌ No | You curated what counts as a legal ref |
| **Max hops limit** | ❌ No | Computation/quality tradeoff decision |
| **Citation format design** | ❌ No | Product design — how users read answers |
| **Metadata schema (what to store, when)** | ❌ No | Directly affects citation quality |
| **No-answer detection strategy** | ❌ No | Hallucination prevention is your call |
| **System prompt engineering for Q&A** | ❌ No | Directly affects output quality |
| **API endpoint design (what routes, what payloads)** | ❌ No | Software design decision |

---

## Phase-by-Phase Breakdown

### Phase 1 — Foundation Setup ✅ COMPLETE (AI-generated)

- FastAPI scaffold with 3 routers: `health`, `documents`, `query`
- Pydantic models: `DocumentUploadResponse`, `QueryRequest`, `QueryResponse`, `Citation`
- `config.py` with typed env vars via pydantic-settings
- `Dockerfile` with Railway `PORT` injection
- `.env.example`, `.gitignore`

**Your job:** Read every generated file. You own it — don't copy-paste blindly.

---

### Phase 2 — Chunking Strategy ✅ DECIDED (You own this)

**Your decisions and reasoning:**

| Decision | Your Choice | Your Reasoning |
|---|---|---|
| Chunking method | **Semantic chunking** | Dense legal PDFs — sentence-level context matters more than token count |
| Overlap | **No overlap** | Overlap solves fixed-size fragmentation; semantic chunking doesn't fragment sentences, so overlap only adds noise |
| Breakpoint threshold | **95th percentile** | High threshold → fewer, larger, more coherent chunks for legal text. Tune on your actual docs. |
| Document type scope | **Any document** | Works for docs with AND without sections — section detection is a retrieval-layer feature, not a chunking constraint |

**Interview proof-point:**
> *"I chose semantic chunking with no overlap for dense legal PDFs. Overlap is a fixed-size chunking artifact — it exists to repair sentence fragmentation. Semantic chunking doesn't fragment sentences by definition, so overlap would only add irrelevant noise to each chunk."*

---

### Phase 3 — Embedding & Vector Store ✅ COMPLETE

#### Your architecture decisions:

| Decision | Your Choice | Your Reasoning |
|---|---|---|
| Embedding model selection | **BAAI/bge-large-en-v1.5** | Tested empirically on actual legal docs; BGE-Large provides high-accuracy retrieval for legal semantics and section structures. |
| Models compared | `BAAI/bge-large-en-v1.5`, `BAAI/bge-base-en-v1.5`, `sentence-transformers/all-MiniLM-L6-v2` | Free, local, offline sentence-transformers models comparing dimensions, footprint, speed, and accuracy. |
| ChromaDB collections | **Single dynamic collection** | Suffixing collection names with clean model IDs automatically isolates collections, preventing dimension mismatch crashes. |
| Metadata schema — citation fields | **Every chunk** | `page_number`, `paragraph_number`, `chunk_index`, `filename` always stored |
| Metadata schema — retrieval fields | **Conditional only** | `has_cross_ref`, `section_id`, `cross_ref_targets` only stored when detected |
| Cross-ref keyword scope | **Internal legal refs only** | Curated dictionary: "see section", "pursuant to", "as defined in", etc. Excludes book/article citations deliberately |
| Section ID tagging | **Bidirectional** | Chunks that ARE sections store `section_id`. Chunks that REFERENCE sections store `cross_ref_targets`. Enables precise second-hop metadata filter. |

#### Metadata schema (final):

```python
# ALWAYS on every chunk — supports citations
{
    "document_id":      "doc_abc123",
    "chunk_index":      4,
    "filename":         "contract.pdf",
    "page_number":      3,
    "paragraph_number": 2,
}

# CONDITIONALLY — only when cross-reference detected
{
    "has_cross_ref":           True,
    "section_id":              "3.2",       # if chunk IS a section heading
    "cross_ref_targets":       "3.2,A",     # if chunk REFERENCES other sections
    "cross_ref_trigger_types": "direct_pointer,definitional",
}
```

#### Running the evaluation:
```powershell
# Runs 100% locally and offline:
python scripts/compare_embeddings.py --doc test_docs/sample_legal_agreement.txt
```
Compared BGE-Large, BGE-Base, and MiniLM. Selected BGE-Large for maximum accuracy on legal text and section structure.

---

### Phase 4 — Retrieval & Q&A Pipeline 🔄 IN PROGRESS (You own the design)

#### Your architecture decisions (confirmed):

| Decision | Your Choice | Your Reasoning |
|---|---|---|
| Primary retrieval | **Vector similarity** | Works for all documents regardless of structure |
| Cross-ref handling | **Query routing** | Detect section refs via keyword dictionary → metadata filter. No ref found → pure vector search |
| Structured output format | **Function calling** | Need LLM to signal intent ("go fetch this ref"), not just return data. Enforces exact schema. JSON mode doesn't constrain schema. |
| Max hops | **2** | Caps at 3 total LLM calls per query. Beyond 2 hops, marginal value drops, computation rises |
| top_k — initial pass | **5** | Enough context without overloading LLM |
| top_k — per hop | **2–3** | Targeted lookup — you know the section, be precise |
| Context window management | **Token count check** | If total chunk tokens > ~6000 → drop lowest-scoring chunks. Prevents context degradation. |
| No-answer detection | **Two-stage** | Stage 1: if best similarity score < threshold → skip LLM call entirely. Stage 2: if LLM can't answer → return `ANSWER_NOT_FOUND` signal via function call. |
| Score threshold (no-answer) | **0.40** | Based on empirical testing of BGE-Large on legal contracts, correct matches yielded similarity scores of 0.48 - 0.50, whereas irrelevant retrievals scored below 0.30. A threshold of 0.40 maximizes retrieval precision while filtering out false matches. |

#### Citation format (your design):

Inline numbering during answer, reference list at the end:

```
"The licensor bears full indemnification responsibility [1]. Where
multiple provisions apply simultaneously, the most restrictive
clause governs [2][3]."

References:
[1] Page 3, §3.2 — "The licensor shall indemnify the licensee..."
[2] Page 7       — "Obligations set forth herein apply concurrently..."
[3] Page 12, §5.1 — "In case of conflict, the more restrictive..."
```

Every `[N]` maps back to: `chunk_index`, `page_number`, `paragraph_number`, `excerpt`.

#### Pipeline flow:
```
Question
  │
  ├─► Embed question (chosen model)
  ├─► Vector search ChromaDB → top 5 chunks
  ├─► Score check: any chunk above threshold?
  │     No  → return answer_found: False immediately (no LLM call)
  │     Yes → continue
  ├─► Format context: numbered chunks with page/§ prefix
  ├─► LLM call (function calling) → structured output:
  │     { answer, citations: [N→chunk], needs_followup, refs_to_fetch }
  ├─► needs_followup? (max 2 times)
  │     Yes → metadata filter for section_id → 2–3 more chunks → repeat
  │     No  → done
  └─► Build final response: answer + inline [N] refs + reference list
```

---

### Phase 5 — API Design ✅ COMPLETE (Your design, AI-refined)

```
POST   /documents/upload          → accepts PDF/TXT, returns document_id + chunk_count
POST   /documents/{id}/query      → question + top_k → answer + citations + answer_found
GET    /documents/{id}            → document metadata (filename, status, chunk_count)
DELETE /documents/{id}            → removes vectors from both ChromaDB collections
GET    /health                    → Railway health check
```

---

### Phase 6 — Error Handling, Testing, Deploy (AI-Heavy ✅)

- Error handling: implemented globally in `main.py` (debug mode hides details in prod)
- Test scaffolds: AI writes structure, you write assertions
- Docker + Railway config: generated, Railway `PORT` env var handled
- Deployment options: see Free Resources section below

---

## Free Resources Assessment

| Component | Paid (Spec) | Free Alternative | Quality gap |
|---|---|---|---|
| Embeddings | OpenAI API | `BAAI/bge-large-en-v1.5` (sentence-transformers, local) | ~10–15% lower |
| LLM for Q&A | GPT-4o | Groq API free tier (Llama 3.1 70B) | Comparable for RAG |
| Vector DB | ChromaDB | ChromaDB — same thing, it's open source | None |
| Deployment | Railway | Railway free tier / Render / HuggingFace Spaces | Minor cold-start delays |

**For portfolio use:** Spend $2–5 on OpenAI during development — employers recognize the stack by name. The free alternatives are legitimate for personal exploration.

---

## Red Lines — Never Cross These

| Rule | Why |
|---|---|
| Never let AI design your chunking strategy | You won't be able to explain it |
| Never accept embedding model choice without empirical testing | Models change; blind choice = no defensible answer |
| Never skip reading AI-generated code | You'll get caught in interviews |
| Never let AI write your cross-reference keyword dictionary | That curation IS your domain understanding |
| Never let AI decide your citation format | That's product design — your call |
| Never let AI write your system prompt | Output quality is directly your responsibility |

---

## Interview-Ready Architecture Summary

> *"I built a RAG pipeline for legal PDFs using semantic chunking with no overlap — overlap is a fixed-size artifact that semantic chunking makes irrelevant. I compared text-embedding-3-small and text-embedding-3-large empirically on my actual documents and chose [X] based on retrieval precision. My retrieval uses query routing: if the question contains a legal cross-reference keyword, I do a targeted metadata filter. Otherwise I fall back to vector similarity. I use function calling — not JSON mode — so the LLM can signal intent when it detects cross-references, triggering a second retrieval hop, capped at 2 to bound API calls at 3 per query. Citations are inline [N] notation mapped back to exact chunk, page, and paragraph. When no relevant context exists, I detect it at the score level before the LLM call, saving computation entirely."*

---

## Progress Tracker

- [x] Phase 1 — Foundation Setup
- [x] Phase 2 — Chunking Strategy (decided + implemented)
- [x] Phase 3 — Embedding & Vector Store (implemented, model selected)
- [x] Phase 3 — Run compare_embeddings.py → pick model (selected BGE-Large)
- [ ] Phase 4 — QueryService implementation
- [ ] Phase 5 — API Design (endpoints done, query logic pending)
- [ ] Phase 6 — Testing & Deploy
