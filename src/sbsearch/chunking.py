"""Text chunking for semantic indexing (F6, Phase 3).

Chunking strategy: paragraph-based, not fixed-length. Paragraphs (separated
by a blank line) are the natural unit of a personal note, so they're kept
whole and greedily packed up to `max_chars`; only a paragraph that alone
exceeds `max_chars` gets force-split into overlapping slices, so a chunk
boundary doesn't sever a sentence from its immediate context.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 800
DEFAULT_OVERLAP = 100

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def chunk_text(
    text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_slice_long_paragraph(paragraph, max_chars, overlap))
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks


def _slice_long_paragraph(text: str, max_chars: int, overlap: int) -> list[str]:
    step = max_chars - overlap if overlap < max_chars else max_chars
    slices = []
    start = 0
    while start < len(text):
        end = start + max_chars
        slices.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return slices
