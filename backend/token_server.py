import os
import asyncio
import logging
import aiohttp
from contextlib import asynccontextmanager
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Path, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pypdf.errors import PyPdfError

load_dotenv(".env.local")

from gemini import GEMINI_MODEL, parse_resume  # noqa: E402  (after load_dotenv)
from rag import build_resume_store, extract_pdf_text, get_embeddings, query_store  # noqa: E402
from schemas import ReportResponse, ReportSubmission, ResumeProfile  # noqa: E402
from session_store import (  # noqa: E402
    InterviewSession,
    get_session,
    put_session,
    remove_session,
    sweep_expired_forever,
)

logger = logging.getLogger(__name__)

# Resume upload limits
MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_RESUME_CHARS = 50_000
MIN_RESUME_CHARS = 100

ROOM_PATTERN = r"^interview-[A-Za-z0-9_-]{1,40}$"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load the embedding model now so the first resume upload isn't slow.
    await asyncio.to_thread(get_embeddings)
    sweeper = asyncio.create_task(sweep_expired_forever())
    try:
        yield
    finally:
        sweeper.cancel()


app = FastAPI(lifespan=lifespan)

# Enable CORS (open for dev; restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
MAX_CONCURRENT_SESSIONS = 5


async def get_active_rooms() -> list[Dict[str, Any]]:
    """
    Query LiveKit server for active rooms to count concurrent sessions.
    """
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    
    if not all([livekit_url, api_key, api_secret]):
        return []
    
    try:
        # Use HTTP API directly to list rooms
        # Parse the URL to get the host
        import re
        host = livekit_url.replace("ws://", "http://").replace("wss://", "https://")
        
        # Create auth header with token
        token = api.AccessToken(api_key, api_secret).with_grants(api.VideoGrants()).to_jwt()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{host}/twirp/livekit.RoomService/ListRooms",
                headers={"Authorization": f"Bearer {token}"},
                json={}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    rooms = data.get("rooms", [])
                    
                    # Filter for interview rooms with participants
                    interview_rooms = [
                        room for room in rooms 
                        if room.get("name", "").startswith("interview-") and room.get("numParticipants", 0) > 0
                    ]
                    
                    return interview_rooms
                else:
                    print(f"Error listing rooms: HTTP {response.status}")
                    return []
    except Exception as e:
        print(f"Error getting active rooms: {e}")
        return []


@app.get("/livekit-url")
async def get_livekit_url():
    """Return the LiveKit WebSocket URL."""
    livekit_url = os.getenv("LIVEKIT_URL")
    if not livekit_url:
        return {"error": "LIVEKIT_URL not configured"}
    return {"url": livekit_url}


@app.get("/capacity-check")
async def check_capacity():
    """
    Check if there's capacity for a new interview session.
    Returns the current number of active sessions and whether a new session can be started.
    """
    try:
        active_rooms = await get_active_rooms()
        active_count = len(active_rooms)
        has_capacity = active_count < MAX_CONCURRENT_SESSIONS
        
        return {
            "has_capacity": has_capacity,
            "active_sessions": active_count,
            "max_sessions": MAX_CONCURRENT_SESSIONS,
            "message": "Capacity available" if has_capacity else "Maximum concurrent interviews reached. Please try again later."
        }
    except Exception as e:
        print(f"Error checking capacity: {e}")
        # In case of error checking capacity, allow the connection
        # (fail open rather than fail closed)
        return {
            "has_capacity": True,
            "active_sessions": 0,
            "max_sessions": MAX_CONCURRENT_SESSIONS,
            "message": "Capacity check unavailable, proceeding",
            "error": str(e)
        }


@app.get("/token")
async def get_token(room: str, username: str):
    """
    Generate a LiveKit access token for the given room and username.
    Checks capacity before issuing token for interview rooms.
    """
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(status_code=500, detail="LiveKit credentials not configured")

    # Check capacity for interview rooms
    if room.startswith("interview-"):
        capacity_check = await check_capacity()
        if not capacity_check.get("has_capacity", True):
            raise HTTPException(
                status_code=429,
                detail=capacity_check.get("message", "Too many active sessions")
            )

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(username)
        .with_name(username)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
            )
        )
    )

    print(f"Generated token for room: {room}, user: {username}")
    return {"token": token.to_jwt()}


# --------------------------------------------------------------------------- #
# Resume upload (called by the frontend before the interview starts)
# --------------------------------------------------------------------------- #
@app.post("/resume")
async def upload_resume(
    room: str = Form(..., pattern=ROOM_PATTERN),
    file: UploadFile = File(...),
):
    """
    Parse a PDF resume for an interview room.

    1. Extract text from the PDF
    2. Gemini turns it into a structured profile
    3. The text is indexed in an in-memory vector store (HF embeddings)
    """
    data = await file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume is too large (max 5 MB).")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="Only PDF resumes are supported.")

    try:
        text = await asyncio.to_thread(extract_pdf_text, data)
    except PyPdfError:
        raise HTTPException(status_code=422, detail="Could not read this PDF. Is the file corrupted or password protected?")

    if len(text.strip()) < MIN_RESUME_CHARS:
        raise HTTPException(
            status_code=422,
            detail="No readable text found in this PDF. Scanned/image-only resumes are not supported.",
        )
    text = text[:MAX_RESUME_CHARS]

    try:
        profile = await parse_resume(text)
    except Exception as e:
        logger.error(f"Resume parsing failed ({GEMINI_MODEL}): {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Failed to parse resume with Gemini: {e}")

    try:
        store = await asyncio.to_thread(build_resume_store, room, text)
    except Exception as e:
        logger.error(f"Resume indexing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to index resume: {e}")

    put_session(InterviewSession(room=room, profile=profile, store=store))
    logger.info(f"Resume stored for {room}: {len(profile.skills)} skills, {len(profile.projects)} projects")

    return {
        "room": room,
        "candidate_name": profile.candidate_name,
        "skills": profile.skills,
        "projects": [p.name for p in profile.projects],
    }


# --------------------------------------------------------------------------- #
# Session endpoints used by the agent (same host, trusted in dev) and the frontend
# --------------------------------------------------------------------------- #
def _require_session(room: str) -> InterviewSession:
    session = get_session(room)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown or expired interview session.")
    return session


@app.get("/sessions/{room}/resume", response_model=ResumeProfile)
async def get_resume(room: str = Path(..., pattern=ROOM_PATTERN)):
    """Structured resume profile (agent uses it to build its prompt)."""
    return _require_session(room).profile


@app.get("/sessions/{room}/search")
async def search_resume(
    room: str = Path(..., pattern=ROOM_PATTERN),
    q: str = Query(..., min_length=1, max_length=500),
    k: int = Query(4, ge=1, le=10),
):
    """Semantic search over the candidate's resume (agent tool backend)."""
    session = _require_session(room)
    context = await asyncio.to_thread(query_store, session.store, q, k)
    return {"context": context}


@app.post("/sessions/{room}/report", status_code=204)
async def submit_report(submission: ReportSubmission, room: str = Path(..., pattern=ROOM_PATTERN)):
    """The agent posts the final evaluation (or an error) here when the interview ends."""
    session = _require_session(room)
    if submission.report is None and not submission.error:
        raise HTTPException(status_code=422, detail="Provide either `report` or `error`.")
    session.report = submission.report
    session.error = submission.error if submission.report is None else None


@app.get("/sessions/{room}/report", response_model=ReportResponse)
async def get_report(room: str = Path(..., pattern=ROOM_PATTERN)):
    """The frontend polls this after the interview ends."""
    session = _require_session(room)
    if session.report is not None:
        return ReportResponse(status="ready", report=session.report)
    if session.error:
        return ReportResponse(status="failed", error=session.error)
    return ReportResponse(status="pending")


@app.delete("/sessions/{room}", status_code=204)
async def delete_session(room: str = Path(..., pattern=ROOM_PATTERN)):
    """Called by the frontend once the user has seen the result. Drops everything."""
    remove_session(room)


if __name__ == "__main__":
    import uvicorn
    
    print("Token Server Started!\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)


