"""Vercel function with the whole REST API: vercel.json rewrites /api/* here."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from starshop.serverless import create_app  # noqa: E402

app = create_app()
