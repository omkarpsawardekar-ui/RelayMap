
import hashlib
import re

from collections import Counter


# Rule-based patterns: these identify candidate evidence,
# not verified project facts.

CLASSIFICATION_PATTERNS = [
    (
        "blocker",
        re.compile(
            r"\b(blocker|blocked by|blocking|cannot proceed|"
            r"unable to proceed|waiting for|impediment|"
            r"preventing progress|at risk)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "decision",
        re.compile(
            r"\b(decided|decision|agreed|approved|selected|"
            r"chosen|adopted|opted for|confirmed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "dependency",
        re.compile(
            r"\b(depends on|dependent on|depends upon|"
            r"relies on|rely on|prerequisite|downstream|"
            r"upstream|requires)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "responsibility",
        re.compile(
            r"\b(responsible for|assigned to|owned by|"
            r"owner of|accountable for|in charge of|"
            r"led by)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "question",
        re.compile(
            r"\b(unresolved question|open question|"
            r"needs clarification|requires clarification|"
            r"unknown|unclear|TBD|to be determined)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "task",
        re.compile(
            r"\b(to-?do|action item|next step|next action|"
            r"must|needs? to|should|plan to|"
            r"unfinished|outstanding work|"
            r"will implement|will build|will create|"
            r"will develop|will deliver|"
            r"implement|build|develop|complete|"
            r"finish|deliver|follow-up)\b",
            re.IGNORECASE,
        ),
    ),
]


OWNER_PATTERNS = [
    re.compile(
        r"\b(?:assigned to|owned by|led by)\s+"
        r"([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2})"
    ),
    re.compile(
        r"\b([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2})"
        r"\s+(?:is|will be)\s+"
        r"(?:responsible for|the owner of|leading)\b"
    ),
]


def split_into_sentences(text: str) -> list[str]:
    """
    Split document chunks into readable evidence excerpts.

    Blank lines separate paragraphs. Sentence boundaries are
    used within each paragraph.
    """

    paragraphs = re.split(r"\n\s*\n", text)

    sentences = []

    for paragraph in paragraphs:
        normalized = re.sub(r"\s+", " ", paragraph).strip()

        if not normalized:
            continue

        parts = re.split(
            r"(?<=[.!?])\s+(?=[A-Z0-9\"“'(])",
            normalized,
        )

        for part in parts:
            excerpt = part.strip()

            if len(excerpt) < 25:
                continue

            if len(excerpt) > 800:
                continue

            sentences.append(excerpt)

    return sentences


def classify_evidence(excerpt: str) -> str | None:
    """
    Return the strongest matching category.

    Each excerpt receives one candidate category to avoid
    creating several overlapping records from the same sentence.
    """

    for item_type, pattern in CLASSIFICATION_PATTERNS:
        if pattern.search(excerpt):
            return item_type

    if excerpt.endswith("?"):
        return "question"

    return None


def find_candidate_owner(excerpt: str) -> str | None:
    """
    Capture an explicit name mention when the wording supports it.

    This is only a candidate mention, never a verified user assignment.
    """

    for pattern in OWNER_PATTERNS:
        match = pattern.search(excerpt)

        if match:
            return match.group(1).strip()

    return None


def create_candidate(excerpt: str) -> dict | None:
    """Build an evidence-backed candidate from a source excerpt."""

    item_type = classify_evidence(excerpt)

    if item_type is None:
        return None

    clean_title = re.sub(
        r"^\s*(?:[-*•]\s*|\d+[.)]\s*)",
        "",
        excerpt,
    ).strip()

    title = clean_title[:247]

    if len(clean_title) > 247:
        title += "..."

    evidence_hash = hashlib.sha256(
        excerpt.encode("utf-8")
    ).hexdigest()

    return {
        "item_type": item_type,
        "title": title,
        "description": (
            "Rule-based candidate extracted from source evidence. "
            "Verify its meaning, context and status before treating "
            "it as established project knowledge."
        ),
        "source_excerpt": excerpt,
        "evidence_hash": evidence_hash,
        "candidate_owner_mention": find_candidate_owner(excerpt),
        "work_status": "unknown",
        "review_status": "pending",
        "extraction_method": "rule_based",
    }


def extract_candidates_from_chunk(chunk_text: str) -> list[dict]:
    """Extract candidate knowledge records from one evidence chunk."""

    candidates = []
    seen_hashes = set()

    for excerpt in split_into_sentences(chunk_text):
        candidate = create_candidate(excerpt)

        if candidate is None:
            continue

        evidence_hash = candidate["evidence_hash"]

        if evidence_hash in seen_hashes:
            continue

        seen_hashes.add(evidence_hash)
        candidates.append(candidate)

    return candidates