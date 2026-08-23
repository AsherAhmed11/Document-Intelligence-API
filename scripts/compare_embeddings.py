"""
Embedding model comparison script.

Run this BEFORE choosing your production embedding model.
It indexes a test document with the three candidate local sentence-transformers models
and runs the same queries against all three — you inspect the results and pick the winner.

Usage:
    python -m scripts.compare_embeddings --doc path/to/test.pdf --queries queries.txt

Or hardcode test queries below and run:
    python scripts/compare_embeddings.py
"""
import asyncio
import os
import sys
import argparse
import warnings

# Suppress langchain-experimental sunset warning
warnings.filterwarnings("ignore", message=".*langchain-experimental.*")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
CHROMA_DIR = "./chroma_store"
COLLECTION_PREFIX = "documents"
TOP_K = 5

MODELS_TO_COMPARE = [
    "BAAI/bge-large-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
]

# ── Hardcode your test queries here ───────────────────────────────────────────
TEST_QUERIES = [
    "What are the indemnification obligations of the licensor?",
    "When does the agreement terminate and what are the renewal terms?",
    "What are the payment terms and what happens with late payments?",
    "What is the definition of Confidential Information?",
    "What are the SLA uptime guarantees and what credits apply?",
]


def print_results(query: str, model_name: str, results: dict) -> None:
    print(f"\n{'='*70}")
    print(f"  Model : {model_name}")
    print(f"  Query : {query}")
    print(f"{'='*70}")

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not docs:
        print("  No chunks retrieved.")
        return

    for rank, (doc, meta, dist) in enumerate(zip(docs, metas, distances), 1):
        score = round(1 - dist, 4)      # convert distance → similarity
        page = meta.get("page_number", "?")
        has_ref = "[CROSS-REF]" if meta.get("has_cross_ref") else ""
        is_section = f"Sec {meta.get('section_id')}" if meta.get('section_id') else ""
        label = " ".join(filter(None, [is_section, has_ref]))

        print(f"\n  [{rank}] score={score:.4f}  page={page}  {label}")
        print(f"      {doc[:200].replace(chr(10), ' ')}...")


async def compare(doc_path: str | None, query_list: list[str]) -> None:
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)

    # Cache loaded sentence-transformer models to avoid reloading them multiple times
    print("\nLoading local embedding models...")
    models = {}
    for model_name in MODELS_TO_COMPARE:
        print(f"  Loading {model_name}...")
        models[model_name] = SentenceTransformer(model_name)

    # Check if collections exist and have data
    indexing_needed = False
    for model_name in MODELS_TO_COMPARE:
        model_suffix = model_name.replace("/", "_").replace(".", "_")
        col_name = f"{COLLECTION_PREFIX}_{model_suffix}"
        try:
            col = chroma.get_collection(col_name)
            if col.count() == 0:
                indexing_needed = True
        except Exception:
            indexing_needed = True

    if indexing_needed:
        if doc_path is None:
            print("\nCollections are empty. Run with --doc path/to/your.pdf first.")
            print("Example: python scripts/compare_embeddings.py --doc sample.pdf")
            sys.exit(1)

        print(f"\nIndexing '{doc_path}' using all three models...")
        from app.config import get_settings
        from app.services.document_service import DocumentService

        with open(doc_path, "rb") as f:
            contents = f.read()
        ext = doc_path.rsplit(".", 1)[-1].lower()
        filename = os.path.basename(doc_path)

        for model_name in MODELS_TO_COMPARE:
            print(f"\nProcessing pipeline for {model_name}...")
            settings = get_settings()
            # Override settings dynamically
            settings.embedding_model = model_name
            service = DocumentService(settings)
            
            # Re-index the same document (DocumentService uses dynamically named collections)
            chunk_count = await service.process_and_index(
                document_id="compare_test",
                filename=filename,
                contents=contents,
                extension=ext,
            )
            print(f"  Indexed {chunk_count} chunks.")

    # Run queries against all models
    print("\n\n" + "="*70)
    print("  LOCAL EMBEDDING MODEL COMPARISON")
    print("  Evaluate which model retrieves more relevant chunks for your queries.")
    print("  Higher score = more similar to your question.")
    print("="*70)

    for query in query_list:
        for model_name in MODELS_TO_COMPARE:
            model_suffix = model_name.replace("/", "_").replace(".", "_")
            col_name = f"{COLLECTION_PREFIX}_{model_suffix}"
            col = chroma.get_collection(col_name)

            # Embed query locally using cached model
            vec = models[model_name].encode(query).tolist()

            results = col.query(
                query_embeddings=[vec],
                n_results=TOP_K,
                include=["documents", "metadatas", "distances"],
            )
            print_results(query, model_name, results)

    print("\n\n" + "="*70)
    print("  DECISION GUIDE")
    print("  * Choose BAAI/bge-large-en-v1.5 if: retrieval accuracy is top priority.")
    print("  * Choose BAAI/bge-base-en-v1.5 if: you want a great balance of speed & quality.")
    print("  * Choose sentence-transformers/all-MiniLM-L6-v2 if: speed & memory are critical.")
    print("  Set EMBEDDING_MODEL=<chosen> in your .env after deciding.")
    print("="*70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare local embedding models")
    parser.add_argument("--doc", help="Path to a PDF to index for testing", default=None)
    parser.add_argument(
        "--queries", help="Path to a text file with one query per line", default=None
    )
    args = parser.parse_args()

    queries = TEST_QUERIES
    if args.queries:
        with open(args.queries) as f:
            queries = [line.strip() for line in f if line.strip()]

    asyncio.run(compare(args.doc, queries))
