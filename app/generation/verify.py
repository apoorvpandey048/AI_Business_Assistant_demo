"""Citation verification — every cited id must correspond to retrieved evidence.

This catches the failure mode where a model invents a citation. We union the ids the
model declared with the [eN] markers actually present in the answer text, then check
all of them against the real evidence set.
"""
from __future__ import annotations

import re

from app.models import CitationCheck, Evidence

_MARKER = re.compile(r"\[(e\d+)\]")


def verify_citations(
    answer: str, declared: list[str], evidence: list[Evidence]
) -> CitationCheck:
    valid_ids = {e.id for e in evidence}
    in_text = set(_MARKER.findall(answer or ""))
    cited = sorted(set(declared) | in_text)
    unknown = sorted(c for c in cited if c not in valid_ids)
    verified = len(unknown) == 0 and (len(cited) > 0 or not evidence)
    if not evidence:
        note = "No evidence retrieved — answer should declare insufficient evidence."
    elif unknown:
        note = f"Citation(s) not backed by retrieved evidence: {unknown}."
    elif not cited:
        note = "Answer cited no evidence."
    else:
        note = f"All {len(cited)} citation(s) trace to retrieved evidence."
    return CitationCheck(verified=verified, cited_ids=cited, unknown_ids=unknown, note=note)
