"""AI Integration Center (Phase 7).

AI is NOT part of the trading engine. It is only an optional external
assistant used to help import/parse strategy and lesson documents (PDF,
DOCX, pasted text, YouTube transcripts) before handing them to the
existing, fully deterministic knowledge_compiler pipeline.

Hard rule, enforced by import structure alone (not just convention):
backtest_engine, paper_trading, and engine.py must NEVER import anything
from this package. If AI is unavailable (no key, disabled, network/API
failure), every workflow that uses this package must keep working exactly
as it did before this package existed, via a rule-based fallback.
"""
