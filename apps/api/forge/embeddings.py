"""Local embeddings with fastembed (ONNX on CPU, no API calls)."""

from functools import cache
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from tokenizers import Tokenizer

MODEL = "BAAI/bge-small-en-v1.5"
# Recommended by the BGE authors for short queries against passages.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "fastembed"


@cache
def model() -> TextEmbedding:
    return TextEmbedding(MODEL, cache_dir=str(CACHE_DIR))


@cache
def tokenizer() -> Tokenizer:
    # A copy without truncation, so long texts report their real length.
    tok = Tokenizer.from_str(model().model.tokenizer.to_str())
    tok.no_truncation()
    tok.no_padding()
    return tok


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text).ids)


def embed(texts: list[str]) -> list[np.ndarray]:
    return list(model().embed(texts, batch_size=32))


def embed_query(query: str) -> np.ndarray:
    return embed([QUERY_PREFIX + query])[0]
