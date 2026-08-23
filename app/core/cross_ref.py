"""
Cross-reference detection for legal documents.

Architecture decision (yours):
  - Only detect INTERNAL legal cross-references (section/clause/annex pointers)
  - Deliberately exclude external citations (books, articles, case law)
  - Metadata is only populated on chunks that actually contain this language
"""
import re
from dataclasses import dataclass


# ── Keyword dictionary ─────────────────────────────────────────────────────────
# Grouped by type so you can expand individual categories independently.
# These are the ONLY triggers that activate cross-reference metadata storage.

CROSS_REF_TRIGGERS: dict[str, list[str]] = {
    "direct_pointer": [
        "see section", "see clause", "see article",
        "see annex", "see schedule", "see exhibit", "see appendix",
    ],
    "definitional": [
        "as defined in", "as defined above", "as defined below",
        "has the meaning given in", "has the meaning set out in",
        "has the meaning assigned in", "as such term is defined in",
    ],
    "obligation": [
        "pursuant to", "in accordance with", "subject to",
        "as provided in", "as set forth in", "as set out in",
        "as described in", "as specified in", "as stated in",
    ],
    "positional_pointer": [
        "under section", "under clause", "under article",
        "referred to in", "referred to above", "referred to below",
        "defined in section", "described in section", "set out in section",
        "set forth in section",
    ],
}

# Flat list for O(n) scanning
_ALL_TRIGGERS: list[str] = [
    t for group in CROSS_REF_TRIGGERS.values() for t in group
]

# Pattern to extract the section/annex number that follows a trigger
_TARGET_PATTERN = re.compile(
    r"""
    (?:section|clause|article|annex|schedule|exhibit|appendix)   # label
    \s*                                                           # optional space
    (                                                             # capture group
        [\d]+(?:\.[\d]+)*                                         # e.g. 3, 3.2, 3.2.1
        (?:\([a-z]\))?                                            # optional (a), (b)
        [a-z]?                                                    # optional trailing letter
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Heading detection — used to assign section_id to chunks that ARE a section
# Matches: "3.", "3.2", "3.2.1", "Section 3", "ARTICLE IV", "Clause 5(a)"
_HEADING_PATTERN = re.compile(
    r"""
    ^                                                             # start of line
    (?:
        (?:section|clause|article|annex|schedule|exhibit)\s+     # labeled heading
        |
        (?:[\d]+\.)+\s*                                          # numbered heading like "3.2 "
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class CrossRefResult:
    has_cross_ref: bool
    trigger_types: list[str]          # which categories fired
    targets: list[str]                # extracted section numbers e.g. ["3.2", "A"]


@dataclass
class SectionInfo:
    is_section_heading: bool
    section_id: str | None            # e.g. "3.2", "Annex A" — None if not a heading


# ── Detection functions ────────────────────────────────────────────────────────

def detect_cross_references(text: str) -> CrossRefResult:
    """
    Scan chunk text for internal legal cross-references.
    Only activates your conditional metadata path — not called for every chunk.
    """
    text_lower = text.lower()
    fired_types: list[str] = []

    for trigger_type, triggers in CROSS_REF_TRIGGERS.items():
        if any(t in text_lower for t in triggers):
            fired_types.append(trigger_type)

    if not fired_types:
        return CrossRefResult(has_cross_ref=False, trigger_types=[], targets=[])

    # Extract section numbers that follow the triggers
    targets = list({m.group(1) for m in _TARGET_PATTERN.finditer(text)})

    return CrossRefResult(
        has_cross_ref=True,
        trigger_types=fired_types,
        targets=targets,
    )


def detect_section_heading(text: str) -> SectionInfo:
    """
    Check if the START of a chunk is a section heading.
    If yes, extract the section_id so this chunk can be found by
    direct metadata filter during second-hop retrieval.
    """
    stripped = text.strip()
    match = _HEADING_PATTERN.match(stripped)
    if not match:
        return SectionInfo(is_section_heading=False, section_id=None)

    # Extract just the section identifier (number or label)
    id_match = re.search(
        r'([\d]+(?:\.[\d]+)*(?:\([a-z]\))?[a-z]?|[A-Z]+\s+[\w]+)',
        stripped[:60],
    )
    section_id = id_match.group(0).strip() if id_match else None

    return SectionInfo(is_section_heading=True, section_id=section_id)
