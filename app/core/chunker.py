"""
Semantic chunker — wraps LangChain's SemanticChunker with page tracking.

Architecture decision (yours):
  - Semantic chunking: group sentences by meaning, not by token count
  - No overlap: semantic boundaries respect complete thoughts; overlap is
    a fixed-size chunking artifact that doesn't apply here
  - Breakpoint threshold: tuned for dense legal text (higher = fewer,
    larger, more coherent chunks). Tune BREAKPOINT_PERCENTILE yourself
    based on your actual documents.
"""
import fitz  # PyMuPDF
from dataclasses import dataclass

from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.embeddings import HuggingFaceEmbeddings


# ── Tuning knob — this is YOUR decision ───────────────────────────────────────
# Higher percentile = fewer chunk boundaries = larger, more coherent chunks
# For dense legal text: 90–97 is a reasonable range to experiment with
# Lower percentile = more breakpoints = smaller, more granular chunks
BREAKPOINT_PERCENTILE = 95


@dataclass
class RawChunk:
    """A chunk of text with its source page number."""
    text: str
    page_number: int        # 1-indexed page from the source PDF
    char_start: int         # approximate character offset in full document text


def extract_pages_from_pdf(contents: bytes) -> list[dict]:
    """
    Extract text per page from raw PDF bytes using PyMuPDF.
    Returns list of {page_number, text} dicts.
    """
    doc = fitz.open(stream=contents, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text("text")
        if text.strip():                      # skip blank pages
            pages.append({
                "page_number": page.number + 1,   # 1-indexed
                "text": text,
            })
    doc.close()
    return pages


def extract_text_from_txt(contents: bytes) -> list[dict]:
    """Wrap plain text as a single 'page' for uniform processing."""
    text = contents.decode("utf-8", errors="replace")
    return [{"page_number": 1, "text": text}]


def extract_text_from_docx(contents: bytes) -> list[dict]:
    """Extract text from DOCX bytes as a single 'page'."""
    import io
    from docx import Document as DocxDocument
    doc = DocxDocument(io.BytesIO(contents))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [{"page_number": 1, "text": text}]


def extract_text(contents: bytes, extension: str) -> list[dict]:
    """Route to the correct extractor based on file type."""
    if extension == "pdf":
        return extract_pages_from_pdf(contents)
    elif extension == "txt":
        return extract_text_from_txt(contents)
    elif extension == "docx":
        return extract_text_from_docx(contents)
    else:
        raise ValueError(f"Unsupported extension for text extraction: {extension}")


def semantic_chunk(
    pages: list[dict],
    settings,
) -> list[RawChunk]:
    """
    Apply semantic chunking across the full document text.

    Strategy:
      1. Concatenate all pages into one string (track page boundaries)
      2. Run SemanticChunker — it embeds sentences and finds meaning-based
         breakpoints, no fixed token count, no overlap
      3. Map each chunk back to its source page number

    The SemanticChunker uses the specified HuggingFace embedding model locally
    to find semantic breakpoints.
    """
    # Build full text with page boundary markers
    full_text = ""
    page_boundaries: list[tuple[int, int]] = []   # (char_start, page_number)

    for page in pages:
        start = len(full_text)
        full_text += page["text"] + "\n"
        page_boundaries.append((start, page["page_number"]))

    def char_to_page(char_pos: int) -> int:
        """Find which page a character position belongs to."""
        page_num = 1
        for (start, pnum) in page_boundaries:
            if char_pos >= start:
                page_num = pnum
            else:
                break
        return page_num

    # Run LangChain's SemanticChunker using custom client wrapper
    from app.core.embeddings import EmbeddingClient, LangChainEmbeddingWrapper
    client = EmbeddingClient(settings)
    embeddings = LangChainEmbeddingWrapper(client)
    chunker = SemanticChunker(
        embeddings=embeddings,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=BREAKPOINT_PERCENTILE,
    )

    docs = chunker.create_documents([full_text])

    # Map chunks back to source pages
    raw_chunks: list[RawChunk] = []
    scan_pos = 0
    for doc in docs:
        text = doc.page_content
        char_start = full_text.find(text, scan_pos)
        if char_start == -1:
            char_start = scan_pos
        page_num = char_to_page(char_start)
        raw_chunks.append(RawChunk(
            text=text,
            page_number=page_num,
            char_start=char_start,
        ))
        scan_pos = char_start + len(text)

    return raw_chunks
