from __future__ import annotations

from fastapi import FastAPI

from app.routers.industry import pack_router, router as industry_router
from app.routers.me import router as me_router

app = FastAPI(title="AINews Cloud", version="0.1.0")

app.include_router(me_router)
app.include_router(industry_router)
app.include_router(pack_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
