"""
In-memory per-interview state held by the token server.

Lives only as long as the process / until the user has seen their result:
- the frontend calls DELETE /sessions/{room} after showing the result screen
- a background sweeper drops anything older than SESSION_TTL_SECONDS as a safety net
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from langchain_chroma import Chroma

from rag import delete_store
from schemas import InterviewReport, ResumeProfile

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours
SWEEP_INTERVAL_SECONDS = 5 * 60


@dataclass
class InterviewSession:
    room: str
    profile: ResumeProfile
    store: Chroma
    created_at: float = field(default_factory=time.time)
    report: Optional[InterviewReport] = None
    error: Optional[str] = None


_sessions: dict[str, InterviewSession] = {}


def put_session(session: InterviewSession) -> None:
    old = _sessions.get(session.room)
    if old is not None:
        _drop(old)
    _sessions[session.room] = session


def get_session(room: str) -> Optional[InterviewSession]:
    return _sessions.get(room)


def remove_session(room: str) -> bool:
    session = _sessions.pop(room, None)
    if session is None:
        return False
    _drop(session)
    return True


def _drop(session: InterviewSession) -> None:
    try:
        delete_store(session.store)
    except Exception as e:  # collection may already be gone
        logger.warning(f"Failed to delete vector store for {session.room}: {e}")


async def sweep_expired_forever() -> None:
    """Background task: remove sessions nobody collected."""
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        cutoff = time.time() - SESSION_TTL_SECONDS
        for room in [r for r, s in _sessions.items() if s.created_at < cutoff]:
            logger.info(f"Sweeping expired session {room}")
            remove_session(room)
