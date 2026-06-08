"""Tiny retrieval/routing eval + smoke test.

Runs every scripted demo question through the full engine and checks:
- the route matches the expected route,
- answerable questions retrieve evidence and pass citation verification,
- the out-of-scope question is correctly flagged 'insufficient'.

Works fully offline (deterministic fallbacks). With ANTHROPIC_API_KEY set, it
exercises the live Claude path instead.
"""
from __future__ import annotations

import sys

from app.engine import get_engine


def main() -> int:
    eng = get_engine()
    cfg_mode = "live" if eng.settings.use_live_llm else "offline"
    print(f"\nMode: {cfg_mode} | embeddings: {eng.document_source.index.embedder.backend} | "
          f"vector: {eng.document_source.index.store.backend}\n")
    print(f"{'expect':>7} {'got':>7}  ok   ev  cite  question")
    print("-" * 100)

    passed = 0
    for ex in eng.examples:
        resp = eng.ask(ex.question)
        route = resp.trace.route.route if resp.trace.route else "?"
        route_ok = route == ex.route
        ev = len(resp.trace.evidence)
        cited = resp.trace.citation_check.verified if resp.trace.citation_check else False

        if ex.route == "NONE":
            ok = route_ok and resp.insufficient
        else:
            ok = route_ok and ev > 0 and cited and not resp.insufficient
        passed += ok
        flag = "✓" if ok else "✗"
        print(f"{ex.route:>7} {route:>7}  {flag:>2}  {ev:>3}  {str(cited):>5}  {ex.question[:64]}")

    total = len(eng.examples)
    print("-" * 100)
    print(f"{passed}/{total} passed\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
