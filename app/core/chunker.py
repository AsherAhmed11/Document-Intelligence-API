"""
Paragraph-aware text chunker — no network calls, no embedding during chunking.

Architecture decision:
  - Chunking ≠ Embedding. These are separate concerns.
  - SemanticChunker (old) made embedding API calls just to find chunk boundaries.
    This was slow, unreliable (network-dependent), and caused 500 errors.
  - This chunker uses paragraph structure (natural in legal/business docs)
    to find boundaries — fast, deterministic, zero dependencies.

Strategy:
  1. Split text at paragraph boundaries (double newlines)
  2. Merge fragments shorter than min_chars into surrounding paragraphs
  3. Split oversized paragraphs at the nearest sentence boundary below max_chars
  4. Track page number for each resulting chunk
"""
import re
from dataclasses import dataclass
import fitz  # PyMuPDF


@dataclass
class RawChunk:
    """A chunk of text with its source page number."""
    text: str
    page_number: int   # 1-indexed page from the source document
    char_start: int    # approximate character offset in full document text


def extract_pages_from_pdf(contents: bytes) -> list[dict]:
    """Extract text per page from raw PDF bytes using PyMuPDF."""
    doc = fitz.open(stream=contents, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text("text")
        if text.strip():
            pages.append({"page_number": page.number + 1, "text": text})
    doc.close()
    return pages


def extract_text_from_txt(contents: bytes) -> list[dict]:
    """Wrap plain text as a single 'page' for uniform processing."""
    text = contents.decode("utf-8", errors="replace")
    return [{"page_number": 1, "text": text}]


def extract_text_from_docx(contents: bytes) -> list[dict]:
    """Extract text from DOCX bytes."""
    import io
    from docx import Document as DocxDocument
    doc = DocxDocument(io.BytesIO(contents))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [{"page_number": 1, "text": text}]


def extract_text(contents: bytes, extension: str) -> list[dict]:
    """Route to the correct extractor based on file extension."""
    if extension == "pdf":
        return extract_pages_from_pdf(contents)
    elif extension == "txt":
        return extract_text_from_txt(contents)
    elif extension == "docx":
        return extract_text_from_docx(contents)
    else:
        raise ValueError(f"Unsupported extension: {extension}")


def _split_at_sentence_boundary(text: str, max_chars: int) -> list[str]:
    """
    Split a long text into pieces of at most max_chars,
    breaking at sentence boundaries (. ! ?) where possible.
    """
    if len(text) <= max_chars:
        return [text]

    sentence_end = re.compile(r'(?<=[.!?])\s+')
    sentences = sentence_end.split(text)

    chunks = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 1 <= max_chars:
            current = (current + " " + sent).strip() if current else sent
        else:
            if current:
                chunks.append(current)
            # If a single sentence is still too long, hard-split at word boundaries
            if len(sent) > max_chars:
                words = sent.split()
                line = ""
                for word in words:
                    if len(line) + len(word) + 1 <= max_chars:
                        line = (line + " " + word).strip() if line else word
                    else:
                        if line:
                            chunks.append(line)
                        line = word
                if line:
                    current = line
            else:
                current = sent
    if current:
        chunks.append(current)
    return chunks


def paragraph_chunk(
    pages: list[dict],
    max_chunk_chars: int = 1500,
    min_chunk_chars: int = 80,
) -> list[RawChunk]:
    """
    Smart paragraph chunker. Fast, deterministic, zero network calls.

    Steps:
      1. Concatenate all page text, tracking page boundaries
      2. Split on paragraph breaks (blank lines / double newlines)
      3. Merge orphaned short paragraphs into their neighbour
      4. Split oversized paragraphs at sentence boundaries
      5. Map each final chunk back to its source page number
    """
    if not pages:
        return []

    # Build full text and record where each page starts
    full_text = ""
    page_boundaries: list[tuple[int, int]] = []  # (char_start, page_number)

    for page in pages:
        start = len(full_text)
        full_text += page["text"] + "\n"
        page_boundaries.append((start, page["page_number"]))

    def char_to_page(char_pos: int) -> int:
        page_num = page_boundaries[0][1]
        for (start, pnum) in page_boundaries:
            if char_pos >= start:
                page_num = pnum
            else:
                break
        return page_num

    # Split on paragraph boundaries (2+ newlines or blank lines)
    paragraphs_raw = re.split(r'\n{2,}', full_text)
    paragraphs = [p.strip() for p in paragraphs_raw if p.strip()]

    if not paragraphs:
        return []

    # Merge short paragraphs into adjacent longer ones
    merged: list[str] = []
    buffer = ""
    for para in paragraphs:
        if not buffer:
            buffer = para
        elif len(buffer) < min_chunk_chars or len(para) < min_chunk_chars:
            buffer = buffer + "\n\n" + para
        else:
            # Both are substantial — check if merging stays within max
            if len(buffer) + len(para) + 2 <= max_chunk_chars:
                buffer = buffer + "\n\n" + para
            else:
                merged.append(buffer)
                buffer = para
    if buffer:
        merged.append(buffer)

    # Split any remaining oversized chunks at sentence boundaries
    final_texts: list[str] = []
    for chunk in merged:
        final_texts.extend(_split_at_sentence_boundary(chunk, max_chunk_chars))

    # Build RawChunk objects, mapping back to source pages
    raw_chunks: list[RawChunk] = []
    scan_pos = 0
    for text in final_texts:
        if not text.strip():
            continue
        # Find approximate position in the full_text
        char_start = full_text.find(text[:50], scan_pos)
        if char_start == -1:
            char_start = scan_pos
        page_num = char_to_page(char_start)
        raw_chunks.append(RawChunk(
            text=text.strip(),
            page_number=page_num,
            char_start=char_start,
        ))
        scan_pos = max(scan_pos, char_start + len(text))

    return raw_chunks


# ── Public API — called by DocumentService ───────────────────────────────────

def semantic_chunk(pages: list[dict], settings) -> list[RawChunk]:
    """
    Entry point for DocumentService. Uses paragraph_chunk internally.
    Named 'semantic_chunk' for backwards compatibility.
    """
    return paragraph_chunk(
        pages,
        max_chunk_chars=getattr(settings, "chunk_max_chars", 1500),
        min_chunk_chars=getattr(settings, "chunk_min_chars", 80),
    )
