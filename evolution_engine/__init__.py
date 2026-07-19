"""Evolution Core Engine (Phase 7A, Part A) -- continuously improves BOT-owned
strategies and lessons using data already collected by backtesting and paper
trading (reflection/experience/knowledge). Pure deterministic logic only: no
AI calls, no machine learning, anywhere in this package (verified by grep in
the Phase 7A test suite, the same discipline already applied to
backtest_engine and paper_trading).

Every BOT strategy/lesson this package creates lives in its own storage
(data_engine.storage.bot_strategies / bot_lessons), physically separate from
strategy_library's user-owned files and the user-authored `lessons` table --
this package has no code path into either, so the A.9 hard safety constraint
("Evolution may NEVER modify user-imported strategies or user-written
lessons") holds structurally, not just behaviorally.
"""
