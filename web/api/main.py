"""FastAPI application for agent management."""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bot.storage.db import ensure_schema
from web.api.db import close_pool, get_pool
from web.api.routes.agents import router as agents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    await get_pool()
    await ensure_schema()
    yield
    await close_pool()


app = FastAPI(title="MiniClaw Agent Management API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router)
