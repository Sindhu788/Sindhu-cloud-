"""Knowledge Compiler -- turns free-form pasted trading knowledge (strategies,
lessons, transcripts, reports, notes) into SINDHU's internal format.

Deterministic, rule-based only -- no AI, no ML. Every extraction module here
wraps and extends the existing Strategy Engine (backtest_engine) and Lesson
Engine (knowledge_engine) rather than reimplementing them, per the "do not
rebuild previous phases" constraint every SINDHU phase has followed.
"""
