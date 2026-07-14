"""
STAGE 2 - Target Page Selection

Pure page-NUMBER selection, given the total page count and the doc_type
Stage 1 already classified. Nothing is rendered here - the orchestrator
renders only the page numbers this function returns.
"""
from typing import List

MAX_PAGES = 25
OFFER_LETTER_TARGET_PAGES_1_INDEXED = [1, 6, 7, 8, 11, 12]


def select_target_pages(total_pages: int, doc_type: str) -> List[int]:
    """Returns 1-indexed page numbers to render for extraction."""
    if doc_type == "SIGNED_OFFER_LETTER_JADE":
        return [p for p in OFFER_LETTER_TARGET_PAGES_1_INDEXED if p <= total_pages]

    return list(range(1, min(total_pages, MAX_PAGES) + 1))