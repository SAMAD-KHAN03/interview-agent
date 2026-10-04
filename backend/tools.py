"""
Tools for the interview agent.
Provides resume search (RAG) for a given interview room.
"""

import logging
from typing import Annotated

from livekit.agents import function_tool

from backend_client import search_resume as backend_search_resume

logger = logging.getLogger(__name__)


def build_tools(room_name: str) -> list:
    """Create the agent's tools, bound to one interview room."""

    @function_tool
    async def search_resume(
        query: Annotated[
            str,
            "What to look up in the candidate's resume (a project, technology, role, or claim)",
        ],
    ) -> str:
        """
        Search the candidate's resume for relevant details.

        Use this to look up specifics about the candidate's projects, roles and
        technologies so you can ask informed, specific interview questions.
        """
        try:
            logger.info(f"Searching resume: {query}")
            context = await backend_search_resume(room_name, query, k=4)
            if not context.strip():
                return f"No relevant information found in the resume for: {query}"
            return f"Resume excerpts:\n\n{context}"
        except Exception as e:
            logger.error(f"Error searching resume: {e}")
            return f"Error searching resume: {e}"

    return [search_resume]
