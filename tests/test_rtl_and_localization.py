"""Regression tests — language-aware decline messages and trace observability.

Client report: a Hebrew question that could not be answered produced an English wall
of text (and "some Hebrew answers rendered LTR" — the rendering half is covered by
the UI direction heuristic; this suite pins the backend half: answer language).

Run:  .venv/bin/python -m pytest tests/test_rtl_and_localization.py -q
"""
from __future__ import annotations

import re

_HEB = re.compile(r"[֐-׿]")


def test_hebrew_question_gets_hebrew_decline(sample_engine):
    resp = sample_engine.ask("מה תחזית מזג האוויר מחר בתל אביב?", scope="all")
    assert resp.insufficient
    assert _HEB.search(resp.answer), f"decline not in Hebrew: {resp.answer}"
    assert "Insufficient evidence" not in resp.answer


def test_english_question_gets_english_decline(sample_engine):
    resp = sample_engine.ask("What is our employee headcount in Berlin?", scope="all")
    assert resp.insufficient
    assert resp.answer.startswith("Insufficient evidence")
    assert not _HEB.search(resp.answer)


def test_safety_net_flag_is_machine_readable(sample_engine):
    # When the safety net supplies the evidence, trace.safety_net must be True —
    # the Inspector badge keys off this flag, not prose notes.
    resp = sample_engine.ask("Who are the parties to the Tavor agreement?", scope="all")
    fired_in_notes = any("safety net" in n.lower() and "recovered" in n.lower()
                         for n in resp.trace.notes)
    assert resp.trace.safety_net == fired_in_notes


def test_safety_net_flag_false_on_clean_route(sample_engine):
    resp = sample_engine.ask("What is the total outstanding invoice amount per customer?",
                             scope="all")
    assert resp.trace.safety_net is False
