"""
Citation validation — the groundedness enforcement mechanism.

WHY THIS EXISTS
---------------
A prompt instructing an LLM to "only answer from the sources and cite them"
is a request, not a guarantee. Models cite sources that don't exist, cite
the wrong source, and state claims with no citation at all — all while
sounding completely confident.

In a hiring system, a fabricated claim about a real person ("Jane has eight
years of Kubernetes experience") is the worst output the system could
produce. So groundedness is verified in code after the fact, not assumed
because the prompt asked nicely.

WHAT THIS DOES AND DOESN'T CATCH
--------------------------------
CATCHES: citations to source IDs that don't exist, and claims with no
citation at all. Both are mechanically detectable.

DOES NOT CATCH: a claim citing a real source that doesn't actually support
it. Verifying that would require semantic entailment checking, which is its
own hard problem. This is why the API returns the full source text — so a
recruiter can check any claim themselves. Stated plainly rather than
implying the validation is stronger than it is.
"""
import re
from dataclasses import dataclass, field

# Matches [1], [2, 3], [1][4] etc. in prose, so citations written inline
# rather than in the structured field are still recoverable.
_INLINE_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass
class ValidatedClaim:
    text: str
    source_ids: list[int]
    is_grounded: bool
    warning: str | None = None


@dataclass
class ValidationResult:
    claims: list[ValidatedClaim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def grounded_claims(self) -> list[ValidatedClaim]:
        return [c for c in self.claims if c.is_grounded]

    @property
    def ungrounded_claims(self) -> list[ValidatedClaim]:
        return [c for c in self.claims if not c.is_grounded]

    @property
    def all_claims_ungrounded(self) -> bool:
        """True when nothing survived validation — the caller should treat
        the whole answer as unusable rather than showing a stripped-down
        version that might read as authoritative."""
        return bool(self.claims) and not self.grounded_claims


def extract_inline_citations(text: str) -> list[int]:
    """Pull [n] references out of prose. Used as a fallback when a claim's
    structured source_ids field is empty but it cited inline."""
    found: list[int] = []
    for match in _INLINE_CITATION.finditer(text):
        for part in match.group(1).split(","):
            part = part.strip()
            if part.isdigit():
                found.append(int(part))
    return found


def validate_claims(
    claims: list[dict], valid_source_ids: set[int]
) -> ValidationResult:
    """Verify every claim cites at least one real source.

    `claims` items need `text` and optionally `source_ids`.
    `valid_source_ids` is the set of IDs actually present in the context.
    """
    result = ValidationResult()

    for claim in claims:
        text = (claim.get("text") or "").strip()
        if not text:
            continue

        cited = [int(s) for s in (claim.get("source_ids") or []) if _is_int(s)]
        if not cited:
            # The model may have cited inline instead of populating the
            # structured field — recover those before rejecting the claim.
            cited = extract_inline_citations(text)

        real = [s for s in cited if s in valid_source_ids]
        fabricated = [s for s in cited if s not in valid_source_ids]

        if not cited:
            result.claims.append(
                ValidatedClaim(
                    text=text,
                    source_ids=[],
                    is_grounded=False,
                    warning="Claim has no citation and cannot be verified against any source.",
                )
            )
            result.warnings.append(f"Uncited claim removed: {_truncate(text)}")
        elif not real:
            # Every cited ID was invented. This is the exact failure mode
            # this module exists to catch.
            result.claims.append(
                ValidatedClaim(
                    text=text,
                    source_ids=[],
                    is_grounded=False,
                    warning=(
                        f"Claim cites source(s) {fabricated} which do not exist "
                        "in the retrieved context."
                    ),
                )
            )
            result.warnings.append(
                f"Claim citing nonexistent source(s) {fabricated} removed: {_truncate(text)}"
            )
        else:
            warning = None
            if fabricated:
                warning = (
                    f"Some cited source(s) {fabricated} do not exist and were ignored; "
                    f"the claim is retained on the basis of source(s) {real}."
                )
                result.warnings.append(
                    f"Ignored nonexistent source(s) {fabricated} in an otherwise grounded claim."
                )
            result.claims.append(
                ValidatedClaim(
                    text=text, source_ids=sorted(set(real)), is_grounded=True, warning=warning
                )
            )

    return result


def _is_int(value) -> bool:
    return isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit())


def _truncate(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[:limit] + "..."
