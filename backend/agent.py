import logging
import asyncio
import time
from typing import Optional
from dotenv import load_dotenv

load_dotenv(".env.local")  # must run before the local imports below read env vars

from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io
from livekit.plugins import google, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from backend_client import fetch_resume, post_report
from gemini import GEMINI_MODEL, evaluate_interview
from prompts import build_interviewer_prompt, INTERVIEWER_GREETING_INSTRUCTIONS
from schemas import ReportSubmission, ResumeProfile
from tools import build_tools

# Configure logging to show INFO level and above
# This ensures tool call logs are visible
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Concurrency tracking (thread-safe using asyncio)
active_sessions = 0
MAX_CONCURRENT_SESSIONS = 5
sessions_lock = asyncio.Lock()

# Idle timeout settings (in seconds)
IDLE_TIMEOUT = 900  # 15 minutes
ACTIVITY_CHECK_INTERVAL = 60  # Check every 60 seconds
EMPTY_ROOM_GRACE_PERIOD = 3  # Wait 3 seconds before cleanup to avoid race conditions

# An interview needs at least this many candidate turns to be worth evaluating
MIN_CANDIDATE_TURNS = 2


class Assistant(Agent):
    def __init__(self, room_name: str, profile: ResumeProfile) -> None:
        super().__init__(
            instructions=build_interviewer_prompt(profile),
            tools=build_tools(room_name),
        )


def build_transcript(session: AgentSession) -> tuple[str, int]:
    """
    Turn the session's chat history into a plain-text transcript.
    Returns (transcript, number_of_candidate_turns).
    """
    lines: list[str] = []
    candidate_turns = 0
    for item in session.history.items:
        if item.type != "message" or item.role not in ("user", "assistant"):
            continue
        text = (item.text_content or "").strip()
        if not text:
            continue
        if item.role == "user":
            candidate_turns += 1
            lines.append(f"Candidate: {text}")
        else:
            lines.append(f"Interviewer: {text}")
    return "\n".join(lines), candidate_turns


async def finalize_interview(
    room_name: str, session: AgentSession, profile: ResumeProfile
) -> None:
    """Evaluate the finished interview with Gemini and hand the result to the backend."""
    try:
        await session.aclose()  # make sure the last turns are committed to history
    except Exception as e:
        logger.warning(f"Session close raised for {room_name}: {e}")

    transcript, candidate_turns = build_transcript(session)

    if candidate_turns < MIN_CANDIDATE_TURNS:
        submission = ReportSubmission(
            error="The interview was too short to evaluate. Answer a few questions and try again."
        )
    else:
        try:
            report = await evaluate_interview(profile, transcript)
            submission = ReportSubmission(report=report)
            logger.info(f"Evaluation for {room_name}: overall {report.overall_rating}/10")
        except Exception as e:
            logger.error(f"Evaluation failed for {room_name}: {e}", exc_info=True)
            submission = ReportSubmission(error=f"Could not generate the evaluation ({GEMINI_MODEL}): {e}")

    try:
        await post_report(room_name, submission)
    except Exception as e:
        logger.error(f"Failed to post report for {room_name}: {e}", exc_info=True)

server = AgentServer()


async def increment_session_count() -> bool:
    """
    Try to increment active session count.
    Returns True if successful (under limit), False if at capacity.
    """
    global active_sessions
    async with sessions_lock:
        if active_sessions >= MAX_CONCURRENT_SESSIONS:
            logger.warning(
                f"Session limit reached: {active_sessions}/{MAX_CONCURRENT_SESSIONS}"
            )
            return False
        active_sessions += 1
        logger.info(
            f"Session started. Active sessions: {active_sessions}/{MAX_CONCURRENT_SESSIONS}"
        )
        return True


async def decrement_session_count():
    """Decrement active session count."""
    global active_sessions
    async with sessions_lock:
        active_sessions = max(0, active_sessions - 1)
        logger.info(
            f"Session ended. Active sessions: {active_sessions}/{MAX_CONCURRENT_SESSIONS}"
        )


async def monitor_room_activity(
    room: rtc.Room,
    session: AgentSession,
    last_activity_time: list[float]
):
    """
    Monitor room for:
    1. Empty room (no non-agent participants)
    2. Idle timeout (no user activity for IDLE_TIMEOUT seconds)
    """
    try:
        while True:
            await asyncio.sleep(ACTIVITY_CHECK_INTERVAL)
            
            # Check for non-agent participants
            has_real_participants = False
            for participant in room.remote_participants.values():
                if not (participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT):
                    has_real_participants = True
                    break
            
            # If no real participants, wait grace period and check again
            if not has_real_participants:
                await asyncio.sleep(EMPTY_ROOM_GRACE_PERIOD)
                
                # Re-check after grace period
                has_real_participants = False
                for participant in room.remote_participants.values():
                    if not (participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT):
                        has_real_participants = True
                        break
                
                if not has_real_participants:
                    logger.info(f"Room {room.name} empty - cleaning up session")
                    break
            
            # Check for idle timeout
            time_since_activity = time.time() - last_activity_time[0]
            if time_since_activity > IDLE_TIMEOUT:
                logger.info(f"Session idle timeout in room {room.name}")
                break
    
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error in activity monitor for room {room.name}: {e}", exc_info=True)


@server.rtc_session()
async def my_agent(ctx: agents.JobContext):
    """
    Main agent session handler with cleanup and concurrency management.
    """
    session_id = f"{ctx.room.name}-{time.time()}"
    logger.info(f"Session starting: {session_id}")
    
    # Check concurrency limit
    if not await increment_session_count():
        logger.warning(f"Rejecting session {session_id}: capacity limit reached")
        try:
            await post_report(
                ctx.room.name,
                ReportSubmission(error="The interview service is at capacity. Please try again later."),
            )
        except Exception as e:
            logger.warning(f"Could not report capacity rejection for {ctx.room.name}: {e}")
        return
    
    room_name = ctx.room.name
    session: Optional[AgentSession] = None
    monitor_task: Optional[asyncio.Task] = None
    left_task: Optional[asyncio.Task] = None
    
    try:
        # Load the candidate's parsed resume (uploaded to the token server before the call)
        try:
            profile = await fetch_resume(room_name)
        except Exception as e:
            logger.error(f"Could not load resume for {room_name}: {e}", exc_info=True)
            try:
                await post_report(
                    room_name,
                    ReportSubmission(error="The interviewer could not load your resume. Please start again."),
                )
            except Exception as post_err:
                logger.warning(f"Could not report resume failure for {room_name}: {post_err}")
            return

        # Track last activity time (using list to allow modification in nested function)
        last_activity_time = [time.time()]
        
        # Define event handler to update last activity time
        def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
            """Update activity time when receiving audio from user."""
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                if participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
                    last_activity_time[0] = time.time()
        
        # Register event handler
        ctx.room.on("track_subscribed", on_track_subscribed)

        # Signal as soon as the candidate leaves, so the result is produced right away
        # instead of waiting for the periodic activity check.
        candidate_left = asyncio.Event()

        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            if participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
                candidate_left.set()

        ctx.room.on("participant_disconnected", on_participant_disconnected)
        
        # Initialize session
        try:
            session = AgentSession(
                stt="assemblyai/universal-streaming:en",
                llm=google.LLM(model=GEMINI_MODEL),
                tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
                vad=silero.VAD.load(),
                turn_detection=MultilingualModel(),
            )
        except Exception as e:
            logger.error(f"Failed to initialize session {session_id}: {e}", exc_info=True)
            raise

        try:
            await session.start(
                room=ctx.room,
                agent=Assistant(room_name, profile),
                room_options=room_io.RoomOptions(
                    audio_input=room_io.AudioInputOptions(
                        noise_cancellation=lambda params: noise_cancellation.BVCTelephony() 
                        if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP 
                        else noise_cancellation.BVC(),
                    ),
                ),
            )
        except Exception as e:
            logger.error(f"Failed to start session {session_id}: {e}", exc_info=True)
            raise

        try:
            await session.generate_reply(instructions=INTERVIEWER_GREETING_INSTRUCTIONS)
            logger.info(f"Session {session_id} ready")
        except Exception as e:
            logger.error(f"Failed to generate greeting for {session_id}: {e}", exc_info=True)
        
        # Start monitoring room activity
        monitor_task = asyncio.create_task(
            monitor_room_activity(ctx.room, session, last_activity_time)
        )
        
        # Wait until the candidate leaves or the monitor decides to clean up
        left_task = asyncio.create_task(candidate_left.wait())
        await asyncio.wait({monitor_task, left_task}, return_when=asyncio.FIRST_COMPLETED)

        # Evaluate the interview and hand the result to the backend
        await finalize_interview(room_name, session, profile)
        
    except asyncio.CancelledError:
        logger.info(f"Session {session_id} cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in session {session_id}: {e}", exc_info=True)
    finally:
        # Cleanup
        for task in (monitor_task, left_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Decrement active session count
        await decrement_session_count()
        
        logger.info(f"Session {session_id} ended")


if __name__ == "__main__":
    import os
    livekit_url = os.getenv("LIVEKIT_URL", "Not configured")
    print("\n" + "="*60)
    print("Agent Server Starting...")
    print("="*60)
    print(f"LiveKit URL: {livekit_url}")
    print("Token Server: http://localhost:8000/token?room=<room>&username=<user>")
    print("Connect at: https://meet.livekit.io")
    print("="*60 + "\n")
    agents.cli.run_app(server)

    