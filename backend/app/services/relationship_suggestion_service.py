
import re
import hashlib

from app.services.knowledge_extraction_service import (
    split_into_sentences,
)


STOPWORDS = {
    "the", "and", "for", "from", "with", "that", "this",
    "was", "were", "are", "is", "will", "would", "should",
    "could", "can", "may", "must", "has", "have", "had",
    "its", "their", "they", "them", "then", "than", "also",
    "into", "onto", "over", "under", "before", "after",
    "when", "where", "while", "because", "which", "what",
    "who", "whom", "our", "your", "you", "they", "not",
    "but", "all", "any", "each", "such", "other", "some",
    "project", "work", "task", "item", "system", "team",
    "platform", "document", "information",
}


# Pattern format:
# (relationship type, regex pattern, reverse direction)

RELATION_PATTERNS = [
    (
        "depends_on",
        re.compile(
            r"(?P<left>.+?)\s+"
            r"(?:depends on|depends upon|is dependent on|"
            r"relies on|requires)\s+"
            r"(?P<right>[^.!?]+)",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "blocks",
        re.compile(
            r"(?P<left>.+?)\s+blocks\s+(?P<right>[^.!?]+)",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "blocks",
        re.compile(
            r"(?P<left>.+?)\s+(?:is|are)\s+blocked by\s+"
            r"(?P<right>[^.!?]+)",
            re.IGNORECASE,
        ),
        True,
    ),
    (
        "supports",
        re.compile(
            r"(?P<left>.+?)\s+supports\s+(?P<right>[^.!?]+)",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "informs",
        re.compile(
            r"(?P<left>.+?)\s+informs\s+(?P<right>[^.!?]+)",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "related_to",
        re.compile(
            r"(?P<left>.+?)\s+(?:is\s+)?related to\s+"
            r"(?P<right>[^.!?]+)",
            re.IGNORECASE,
        ),
        False,
    ),
]


def get_keywords(text: str) -> set[str]:
    """Extract meaningful words for conservative title matching."""

    words = re.findall(
        r"[a-zA-Z0-9]{3,}",
        text.lower(),
    )

    return {
        word
        for word in words
        if word not in STOPWORDS
    }


def clean_phrase(phrase: str) -> str:
    """Remove trailing explanations and surrounding punctuation."""

    phrase = re.split(
        r"\b(?:because|while|when|which|so that|although)\b",
        phrase,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    return phrase.strip(" \t\r\n,;:-()[]{}")


def match_knowledge_item(
    phrase: str,
    approved_items: list,
):
    """
    Match a phrase against approved knowledge-item titles.

    Return an item only when the best match is sufficiently strong
    and unambiguous.
    """

    phrase_keywords = get_keywords(phrase)

    if not phrase_keywords:
        return None

    scored_items = []

    for item in approved_items:
        title_keywords = get_keywords(item.title)

        if not title_keywords:
            continue

        overlap = phrase_keywords.intersection(title_keywords)

        if not overlap:
            continue

        coverage = len(overlap) / len(phrase_keywords)

        # Require at least half of the meaningful phrase
        # to match the candidate's title.
        if coverage < 0.5:
            continue

        precision = len(overlap) / len(title_keywords)

        score = (coverage * 0.7) + (precision * 0.3)

        scored_items.append((score, item))

    if not scored_items:
        return None

    scored_items.sort(
        key=lambda result: result[0],
        reverse=True,
    )

    best_score, best_item = scored_items[0]

    # Avoid guessing when more than one item has an equally
    # strong title match.
    if len(scored_items) > 1:
        second_score, _ = scored_items[1]

        if abs(best_score - second_score) < 0.001:
            return None

    return best_item


def extract_relation_from_sentence(
    sentence: str,
) -> dict | None:
    """Identify explicit relationship language."""

    for relation_type, pattern, reverse in RELATION_PATTERNS:

        match = pattern.search(sentence)

        if not match:
            continue

        left_phrase = clean_phrase(match.group("left"))
        right_phrase = clean_phrase(match.group("right"))

        if not left_phrase or not right_phrase:
            continue

        return {
            "relation_type": relation_type,
            "left_phrase": left_phrase,
            "right_phrase": right_phrase,
            "reverse": reverse,
        }

    return None


def generate_relationship_candidates(
    approved_items: list,
    chunks: list,
) -> list[dict]:
    """
    Generate evidence-backed relationship candidates.

    Both endpoints must match approved knowledge items.
    Every candidate retains its original evidence chunk.

    This service never approves a relationship.
    """

    candidates = []
    seen = set()

    for chunk in chunks:

        sentences = split_into_sentences(chunk.chunk_text)

        for sentence in sentences:

            relation = extract_relation_from_sentence(sentence)

            if relation is None:
                continue

            left_item = match_knowledge_item(
                relation["left_phrase"],
                approved_items,
            )

            right_item = match_knowledge_item(
                relation["right_phrase"],
                approved_items,
            )

            # If either side cannot be identified reliably,
            # do not create a relationship.
            if left_item is None or right_item is None:
                continue

            if left_item.id == right_item.id:
                continue

            if relation["reverse"]:
                source_item = right_item
                target_item = left_item
            else:
                source_item = left_item
                target_item = right_item

            relation_type = relation["relation_type"]

            evidence_excerpt = chunk.chunk_text.strip()

            evidence_hash = hashlib.sha256(
                (
                    f"{source_item.id}|"
                    f"{target_item.id}|"
                    f"{relation_type}|"
                    f"{evidence_excerpt}"
                ).encode("utf-8")
            ).hexdigest()

            unique_key = (
                source_item.id,
                target_item.id,
                relation_type,
                evidence_hash,
            )

            if unique_key in seen:
                continue

            seen.add(unique_key)

            candidates.append({
                "source_item_id": source_item.id,
                "target_item_id": target_item.id,
                "relation_type": relation_type,
                "evidence_chunk_id": chunk.id,
                "evidence_excerpt": evidence_excerpt,
                "evidence_hash": evidence_hash,
            })

    return candidates