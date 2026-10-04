"""
HTTP client the agent uses to talk to the token server (resume, search, report).

The agent and the token server are separate processes, so per-interview state
lives in the token server and the agent reaches it over localhost.
"""

import os

import aiohttp

from schemas import ReportSubmission, ResumeProfile

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def fetch_resume(room: str) -> ResumeProfile:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as http:
        async with http.get(f"{BACKEND_URL}/sessions/{room}/resume") as resp:
            resp.raise_for_status()
            return ResumeProfile.model_validate(await resp.json())


async def search_resume(room: str, query: str, k: int = 4) -> str:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as http:
        async with http.get(
            f"{BACKEND_URL}/sessions/{room}/search", params={"q": query, "k": k}
        ) as resp:
            resp.raise_for_status()
            return (await resp.json()).get("context", "")


async def post_report(room: str, submission: ReportSubmission) -> None:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as http:
        async with http.post(
            f"{BACKEND_URL}/sessions/{room}/report",
            json=submission.model_dump(mode="json"),
        ) as resp:
            resp.raise_for_status()
