"""Split sections into overlapping chunks of whole sentences."""

import math
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise

from forge.book import Section

# bge-small truncates at 512 tokens, so chunks stay well under that.
MAX_TOKENS = 350
OVERLAP_TOKENS = 50

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“‘(•])")


@dataclass
class Chunk:
    section_path: str
    text: str
    token_count: int
    pdf_page_start: int
    pdf_page_end: int


def clean(text: str) -> str:
    # Keep compound words like "stimulus-\nresponse" together, then unwrap lines.
    return re.sub(r"\s+", " ", re.sub(r"-\n", "-", text)).strip()


def sentences(section: Section) -> list[tuple[int, str]]:
    """Return (pdf page, sentence) pairs, using the page where each sentence starts."""
    text, line_starts, line_pages = "", [], []
    for page, line in section.lines:
        line_starts.append(len(text))
        line_pages.append(page)
        text += line + "\n"

    bounds = [0, *(m.end() for m in SENTENCE_END.finditer(text)), len(text)]
    result = []
    for start, end in pairwise(bounds):
        sentence = clean(text[start:end])
        if sentence:
            result.append((line_pages[bisect_right(line_starts, start) - 1], sentence))
    return result


def split_long(sentence: str, tokens: int, max_tokens: int) -> list[str]:
    # Flattened tables come out as one huge "sentence"; cut them by words.
    words = sentence.split()
    parts = math.ceil(tokens / max_tokens)
    size = math.ceil(len(words) / parts)
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]


def chunk_section(
    section: Section,
    count_tokens: Callable[[str], int],
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    pieces = []  # (page, text, tokens)
    for page, sentence in sentences(section):
        tokens = count_tokens(sentence)
        if tokens <= max_tokens:
            pieces.append((page, sentence, tokens))
        else:
            pieces += [(page, part, count_tokens(part)) for part in split_long(sentence, tokens, max_tokens)]

    chunks, current = [], []
    for piece in pieces:
        if current and sum(p[2] for p in current) + piece[2] > max_tokens:
            chunks.append(current)
            overlap = []
            for prev in reversed(current):
                if sum(p[2] for p in overlap) + prev[2] > overlap_tokens:
                    break
                overlap.insert(0, prev)
            current = overlap
        current.append(piece)
    if current:
        chunks.append(current)

    result = []
    for group in chunks:
        text = " ".join(p[1] for p in group)
        result.append(Chunk(section.path, text, count_tokens(text), group[0][0], group[-1][0]))
    return result
