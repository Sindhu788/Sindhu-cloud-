"""The lightweight, cloud-deployable half of SINDHU.

Everything under this package is additional and self-contained: it reuses
the same paper_trading/, data_engine/, and sindhu_web/ modules the local
laptop app uses, but assembles its OWN FastAPI app (cloud_runtime.app)
instead of importing sindhu_web.server, which would pull in the full
local app (backtesting, evolution, AI extraction, optimizer) as a side
effect of import. See cloud_runtime/app.py's module docstring and
DEPLOYMENT_CHECKPOINT.md for the full reasoning.
"""
