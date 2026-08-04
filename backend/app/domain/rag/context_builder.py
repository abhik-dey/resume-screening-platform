"""
Build numbered source context for RAG.

Pure and I/O-free. Each retrieved resume becomes a numbered SourceChunk the
LLM must cite by ID — numbering is what makes citation validation possible
at all, since an uncited or wrongly-cited claim becomes mechanically
detectable rather than a matter of judgement.

A token budget applies because retrieved context grows unboundedly with K,
and an over-long prompt either errors or gets silently truncated by the
provider — the latter being worse, since it means the model answers from
partial context without anyone knowing.
"""
from dataclasses import dataclass

# Rough proxy for a token budget. Deliberately conservative: exceeding a
# model's context window fails loudly, but silent provider-side truncation
# would let the model answer from partial sources undetected.
MAX_CONTEXT_CHARS = 12000
MAX_CHARS_PER_SOURCE = 2000


@dataclass
class SourceChunk:
    """One retrieved resume, numbered for citation."""

    source_id: int  # 1-based, what the LLM cites as [1], [2], ...
    resume_id: str
    candidate_name: str
    similarity: float
    text: str


def build_source_chunks(retrieved: list[dict]) -> list[SourceChunk]:
    """Turn retrieval hits into numbered, budget-limited source chunks.

    `retrieved` items need: resume_id, candidate_name, similarity, text.
    Input is assumed already ordered best-first by the retriever; chunks are
    numbered in that order so [1] is always the strongest match.

    Sources are dropped rather than truncated mid-way when the budget runs
    out — a half-cut resume could easily read as though a candidate lacks
    experience that was simply cut off.
    """
    chunks: list[SourceChunk] = []
    used_chars = 0

    # Numbering comes from len(chunks), not enumerate: skipped sources
    # must not leave gaps in the citation IDs the model is given.
    for item in retrieved:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        if len(text) > MAX_CHARS_PER_SOURCE:
            text = text[:MAX_CHARS_PER_SOURCE] + "\n[...truncated]"
        if used_chars + len(text) > MAX_CONTEXT_CHARS:
            break

        chunks.append(
            SourceChunk(
                source_id=len(chunks) + 1,
                resume_id=str(item.get("resume_id", "")),
                candidate_name=item.get("candidate_name") or "Unidentified candidate",
                similarity=float(item.get("similarity", 0.0)),
                text=text,
            )
        )
        used_chars += len(text)

    return chunks


def format_context(chunks: list[SourceChunk]) -> str:
    """Render chunks as the numbered block the LLM sees."""
    if not chunks:
        return "(No sources retrieved.)"
    return "\n\n".join(
        f"[{chunk.source_id}] Candidate: {chunk.candidate_name}\n{chunk.text}"
        for chunk in chunks
    )
