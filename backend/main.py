from __future__ import annotations

from pathlib import Path
import sys

import uvicorn
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.current_web import router


app = FastAPI(
    title="MyInvestTAA",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8025, reload=False)
