"""Deterministic answer-language integrity.

The local provider (a small, multilingual model) can ignore a soft "answer in the
question's language" instruction and reply in the wrong script — the live incident was an
ENGLISH question answered in HEBREW that then degenerated into CJK with a leaked ``{``.

These helpers make the language contract enforceable WITHOUT depending on the model:
- ``question_language`` picks the target language deterministically from the question.
- ``answer_language_ok`` / ``answer_is_garbage`` / ``generation_acceptable`` judge a
  generated answer so the client can refuse to cache (or even surface) defective output.

Scope is the corpus's languages — English + Hebrew. The rule is intentionally lenient on
a *stray* foreign token (an English answer may quote a Hebrew filename) and strict only
when the WRONG script dominates or never-legitimate scripts (CJK) appear.
"""
from __future__ import annotations

import re

_HEBREW = re.compile(r"[֐-׿]")
# CJK ideographs + Japanese kana + Hangul — never legitimate for this EN/HE corpus.
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_LATIN = re.compile(r"[A-Za-z]")
_ARABIC = re.compile(r"[؀-ۿ]")

# Leaked structured-output fragments: the schema keys or an unterminated object/array.
_LEAK = re.compile(r'\{\s*"?(?:answer|citations|insufficient)"?\s*[:}]', re.I)


def question_language(text: str) -> str:
    """The deterministic target language for the answer: ``he`` if the question contains
    any Hebrew letter, else ``en``. Matches the router's own language detection."""
    return "he" if _HEBREW.search(text or "") else "en"


def script_counts(text: str) -> dict[str, int]:
    t = text or ""
    return {
        "hebrew": len(_HEBREW.findall(t)),
        "cjk": len(_CJK.findall(t)),
        "latin": len(_LATIN.findall(t)),
        "arabic": len(_ARABIC.findall(t)),
    }


def answer_language_ok(answer: str, expected: str) -> bool:
    """True when ``answer`` is plausibly in the ``expected`` language (``en``/``he``).

    Lenient by design: only the WRONG script DOMINATING (or any CJK) is a failure, so a
    correct answer that quotes a stray foreign token still passes."""
    c = script_counts(answer)
    if c["cjk"] > 0:
        return False                      # CJK is never legitimate here — hard reject
    if expected == "he":
        # A Hebrew answer must contain Hebrew. A substantial all-Latin reply to a Hebrew
        # question is the mirror of the reported bug.
        return not (c["hebrew"] == 0 and c["latin"] >= 8)
    # expected == "en" (default): reject only when Hebrew/Arabic OUT-WEIGHS Latin.
    wrong = c["hebrew"] + c["arabic"]
    return not (wrong > 0 and wrong >= c["latin"])


def answer_is_garbage(answer: str) -> bool:
    """True for output that leaked the JSON envelope / prompt scaffolding rather than a
    clean prose answer (code fences, a trailing ``{``/``[``, or schema keys)."""
    a = (answer or "").strip()
    if not a:
        return False                      # emptiness is handled as 'insufficient' elsewhere
    if "```" in a:
        return True
    if a.endswith(("{", "[")):
        return True
    return bool(_LEAK.search(a))


def generation_acceptable(data: object, expected_lang: str) -> bool:
    """Whether a structured generation result is fit to surface (and to cache).

    A defective result (wrong dict shape, garbage text, or wrong-language answer) is
    rejected so the client falls through to the deterministic extractive fallback and
    never caches the bad output."""
    if not isinstance(data, dict):
        return False
    ans = data.get("answer")
    if not isinstance(ans, str):
        return False
    if answer_is_garbage(ans):
        return False
    return answer_language_ok(ans, expected_lang)
