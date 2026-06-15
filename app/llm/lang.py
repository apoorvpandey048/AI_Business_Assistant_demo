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


# --- benign language-selection directives (Sprint 15 / decision #2) -----------------
# An explicit, well-formed request to answer in a named language ("answer in Hebrew",
# "תענה באנגלית"). This is DISTINCT from a harmful injection ("ignore instructions",
# "reveal your prompt", "reply PWNED"): selecting an output language is normal assistant
# behavior, so we honor it, while harmful directives stay blocked by the generation
# system prompt + grounding guards. Conservative patterns — a directive VERB is required,
# so "which contracts are in English?" does NOT match.
_LANG_WORD = {"english": "en", "hebrew": "he", "אנגלית": "en", "עברית": "he"}
_DIR_EN = re.compile(
    r"\b(?:answer|respond|reply|write|output)\s+(?:only\s+)?(?:in\s+)?"
    r"(english|hebrew|אנגלית|עברית)\b", re.I)
_DIR_HE = re.compile(
    r"(?:תענה|ענה|השב|תשיב|תשיבי?|כתוב|תכתוב|השיבי?)\s+\S*\s*ב?(אנגלית|עברית)")


def language_directive(text: str) -> str | None:
    """Return ``'en'``/``'he'`` if ``text`` carries an explicit benign request to answer
    in that language, else ``None``. Used by the answer-language precedence chain."""
    t = text or ""
    m = _DIR_EN.search(t)
    if m:
        return _LANG_WORD.get(m.group(1).lower())
    m = _DIR_HE.search(t)
    if m:
        return _LANG_WORD.get(m.group(1))
    return None


def resolve_answer_language(question: str, role_instructions: str | None = None) -> str:
    """Resolve the answer language by precedence (Sprint 15 / decision #2):

    1. an explicit language directive in the ROLE/persona (operator channel — trusted),
    2. an explicit language directive in the QUESTION,
    3. the question's own script (deterministic default).

    Evidence language never decides the answer language. A harmful instruction is not a
    language directive, so it is ignored here and blocked downstream by the generation
    guards. Returns ``'en'`` or ``'he'``."""
    role_dir = language_directive(role_instructions or "")
    if role_dir:
        return role_dir
    q_dir = language_directive(question or "")
    if q_dir:
        return q_dir
    return question_language(question or "")


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
