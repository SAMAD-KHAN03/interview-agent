# Project Interview Coach

An AI-powered technical interviewer that conducts voice-based interviews about your project. Built with LiveKit for real-time voice communication and RAG (Retrieval Augmented Generation) for context-aware questioning.

## 📹 Video Walkthrough

**Full technical walkthrough:** [Watch on YouTube](https://www.youtube.com/watch?v=WAVZ7pkXPE8)

The video covers:
- Token generation with capacity management
- Function calling for on-demand RAG
- RAG setup with ChromaDB
- Trade-offs discussion
- Live demo showing the voice interview in action

## Features

- 🎤 **Real-time Voice Interview:** Natural conversation with AI interviewer using LiveKit's voice pipeline
- 📄 **Resume-Powered Questions:** Upload your PDF resume; Gemini parses it and the interviewer asks specific questions about your roles, projects and claims
- 🧾 **Results Screen:** After the interview you get a visual report: overall rating, clarity, responsiveness, technical depth, resume consistency, per-topic scores, strengths and improvements (kept in memory only, removed once you leave the screen)
- 📝 **Live Transcription:** See conversation transcript in real-time as you speak
- 🎯 **Intelligent Follow-ups:** Agent challenges vague answers and probes for technical depth
- 🔒 **Capacity Management:** Controlled concurrency to manage costs (max 5 concurrent sessions)

---

## Quick Start

### Prerequisites

- **Python 3.11+** with `uv` package manager ([install uv](https://github.com/astral-sh/uv))
- **Node.js 18+** and npm
- **LiveKit Cloud Account** ([sign up free](https://cloud.livekit.io))
- **API Keys:**
  - Google AI Studio API key (Gemini LLM, resume parsing, evaluation) - [Get your API key](https://aistudio.google.com/apikey)
  - LiveKit credentials (URL, API key, API secret) - [Sign up free](https://cloud.livekit.io)

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd backend

# Install backend dependencies
uv sync

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Configuration

Create `.env.local` in the `backend/` directory:

```bash
# LiveKit Configuration
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
# Google AI Studio (Gemini)
GOOGLE_API_KEY=your-google-api-key

# Optional overrides (defaults shown)
# GEMINI_MODEL=gemini-3.5-flash-lite
# EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
# BACKEND_URL=http://localhost:8000
```

> The embedding model runs locally. The first token-server start downloads it from Hugging Face (about 130 MB), so it needs internet access once.

> **Note:** See `.env.example` for a template.

### Your Resume

There is no ingestion step any more. You upload a PDF resume on the start screen. The token server extracts its text, Gemini turns it into a structured profile, and the text is indexed in an **in-memory** vector store for that interview. Scanned (image-only) PDFs are not supported.

---

## Running the Application

You need **three terminals** running simultaneously:

### Terminal 1: Token Server

```bash
cd backend
uv run token_server.py
```

**Expected output:**
```
Token Server Started!
```

### Terminal 2: AI Agent

```bash
cd backend
uv run agent.py dev
```

**Expected output:**
```
Agent Server Starting...
============================================================
LiveKit URL: wss://your-project.livekit.cloud
Connect at: https://meet.livekit.io
============================================================
```

### Terminal 3: Frontend

```bash
cd frontend
npm run dev
```

**Expected output:**
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

---

## Usage

1. **Open the app:** Navigate to `http://localhost:5173` in your browser
2. **Upload your resume:** Choose a PDF (max 5 MB)
3. **Start interview:** Click the "Start Interview" button
4. **Grant permissions:** Allow microphone access when prompted
5. **Wait for greeting:** The AI interviewer will introduce itself (2-5 seconds)
6. **Speak naturally:** Answer questions as you would in a real interview
7. **View transcript:** Click "Transcript" button to see live conversation text
8. **End interview:** Click "End Interview" when finished
9. **See your results:** The result screen appears once Gemini has evaluated the interview (usually a few seconds). Click "Start a new interview" when done; the results are then deleted

### Tips for Best Experience

- **Speak clearly:** Use a good microphone in a quiet environment
- **Be specific:** Vague answers will trigger follow-up questions
- **Pause naturally:** VAD detects when you stop speaking (~500ms silence)
- **Check browser:** Chrome and Edge have best WebRTC support

---

## Project Structure

```
interview-agent/
├── backend/                # Backend Python code
│   ├── agent.py           # Main AI agent with voice pipeline + end-of-interview evaluation
│   ├── token_server.py    # FastAPI: LiveKit tokens, resume upload, session + report endpoints
│   ├── tools.py           # Function tool (resume search)
│   ├── rag.py             # PDF text extraction, HF embeddings, in-memory Chroma
│   ├── gemini.py          # Gemini calls: resume parsing, interview evaluation
│   ├── schemas.py         # Pydantic models (resume profile, interview report)
│   ├── session_store.py   # In-memory per-interview state + expiry sweeper
│   ├── backend_client.py  # Agent -> token server HTTP client
│   ├── prompts.py         # System prompts for interviewer
│   └── .env.local         # API keys and configuration
├── frontend/              # React frontend
│   ├── src/
│   │   ├── App.tsx              # Main app with connection logic
│   │   ├── api.ts               # Token-server calls (resume upload, report, cleanup)
│   │   ├── components/
│   │   │   ├── ResultScreen.tsx     # Post-interview results
│   │   │   ├── CallInterface.tsx    # Call UI and controls
│   │   │   ├── Transcript.tsx       # Live transcription display
│   │   │   ├── AudioVisualizer.tsx  # Audio waveform visualization
│   │   │   └── VideoRenderer.tsx    # Video track rendering
│   │   ├── types.ts             # TypeScript type definitions
│   │   └── index.css            # Global styles
│   └── package.json
├── DESIGN.md              # Architecture and design decisions
└── README.md              # This file
```

---

## How It Works

### Voice Pipeline

```
User speaks → VAD detects speech → STT transcribes → LLM processes → TTS speaks → User hears
     ↓                                                      ↓
   LiveKit                                        Resume search (RAG)
```

1. **Voice Activity Detection (VAD):** Silero model detects when you start/stop speaking
2. **Speech-to-Text (STT):** AssemblyAI transcribes your speech to text
3. **Resume search:** Agent searches your resume using semantic search (in-memory ChromaDB + local Hugging Face embeddings)
4. **LLM Processing:** Gemini (`gemini-3.5-flash-lite` by default) generates contextual follow-up questions
5. **Text-to-Speech (TTS):** Cartesia Sonic synthesizes agent's response
6. **Audio Delivery:** LiveKit streams audio back to your browser

### Resume Flow

```
Start screen: PDF ──► POST /resume ──► pypdf text ──► Gemini ──► structured profile ─┐
                                          └──► chunks (1000 chars, 200 overlap) ──► Chroma (in memory)
                                                                                    │
Agent joins room ──► GET /sessions/{room}/resume  (profile goes into the interviewer prompt)
Agent tool search_resume(query) ──► GET /sessions/{room}/search ──► relevant chunks
```

**Deduplication:** Uses content fingerprinting (first 150 chars) to remove duplicate chunks from retrieval results.

### Results Flow

```
Candidate clicks End ──► agent builds transcript ──► Gemini scores it against the resume
      ──► POST /sessions/{room}/report ──► frontend polls GET /sessions/{room}/report
      ──► result screen ──► DELETE /sessions/{room} (button, tab close, or 2-hour expiry)
```

Interviews with fewer than 2 candidate turns are not evaluated; the result screen says so instead of inventing a score.

---

## Tools & Frameworks

### Backend
- **LiveKit Agents SDK:** Voice pipeline, WebRTC handling, STT/TTS integration
- **Google Gemini (`gemini-3.5-flash-lite`):** LLM for conversation, resume parsing and interview evaluation (via `livekit-plugins-google` and `google-genai`)
- **Hugging Face `BAAI/bge-small-en-v1.5`:** open-source embeddings, run locally with `sentence-transformers`
- **AssemblyAI:** Speech-to-text transcription
- **Cartesia Sonic:** Text-to-speech synthesis
- **LangChain:** Document processing and RAG utilities
- **ChromaDB:** In-memory vector database for semantic search over the resume
- **FastAPI:** Token server, resume upload and report endpoints
- **Silero VAD:** Voice activity detection

### Frontend
- **React + TypeScript:** UI framework
- **Vite:** Build tool and dev server
- **LiveKit React SDK:** WebRTC components and hooks

For detailed design decisions and trade-offs, see [DESIGN.md](DESIGN.md).

---

## Design Decisions & Assumptions

> **Note:** This is a summary. For detailed analysis of trade-offs, limitations, and alternatives considered, see [DESIGN.md](DESIGN.md).

### Key Assumptions
- **Hosting:** Local development setup; production deployment requires infrastructure changes (see [DESIGN.md - Deployment Recommendations](DESIGN.md#deployment-recommendations))
- **RAG:** One short resume per interview, held in an in-memory Chroma collection
- **Concurrency:** 5 concurrent sessions limit for cost control
- **Voice Pipeline:** LiveKit handles all WebRTC complexity

### Quick Reference
- **RAG Chunking:** 1000 chars, 200 overlap (see [DESIGN.md - RAG Chunk Size](DESIGN.md#2-rag-chunk-size-1000-characters-with-200-overlap))
- **Vector DB:** ChromaDB (in memory, per interview) - see [DESIGN.md - Vector Store](DESIGN.md#9-vector-store-chromadb-not-pineconeweaviate) for production alternatives
- **LLM:** Gemini `gemini-3.5-flash-lite` (see the update note at the top of [DESIGN.md](DESIGN.md))
- **Session Management:** 15-minute idle timeout, 3-second empty room grace period

### Limitations
- Maximum 5 concurrent sessions (configurable)
- ChromaDB not suitable for production scale (thousands of docs)
- No authentication in current setup (development only)
- See [DESIGN.md](DESIGN.md) for complete trade-offs and limitations

---

## API Endpoints

### Token Server (FastAPI)

**Base URL:** `http://localhost:8000`

#### `GET /livekit-url`
Returns the LiveKit WebSocket URL.

**Response:**
```json
{
  "url": "wss://your-project.livekit.cloud"
}
```

#### `GET /token?room=<room>&username=<user>`
Generates a LiveKit access token for the specified room and username.

**Parameters:**
- `room` (string): Room name
- `username` (string): Participant identity

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Error (429):**
```json
{
  "detail": "Maximum number of interviews reached. Please try again later."
}
```

#### `POST /resume`
Multipart form: `room` (string, `interview-...`) and `file` (PDF, max 5 MB). Parses the resume and stores it for that room.

**Response:** `{ "room", "candidate_name", "skills": [...], "projects": [...] }`
**Errors:** `413` too large, `415` not a PDF, `422` unreadable / no text layer, `502` Gemini failure.

#### `GET /sessions/{room}/resume`, `GET /sessions/{room}/search?q=&k=`
Used by the agent: structured profile and semantic search over the resume text.

#### `POST /sessions/{room}/report`, `GET /sessions/{room}/report`
The agent posts the evaluation (or an error) when the interview ends; the frontend polls `GET` until `status` is `ready` or `failed` (`pending` while waiting).

#### `DELETE /sessions/{room}`
Drops the resume, vector store and result for that room. Called by the frontend after the user has seen the results.

#### `GET /capacity-check`
Checks if there's capacity for a new session.

**Response:**
```json
{
  "has_capacity": true,
  "active_sessions": 2,
  "max_sessions": 5,
  "message": "Capacity available"
}
```

---

## Configuration Options

### Concurrency Settings (agent.py)

```python
MAX_CONCURRENT_SESSIONS = 5  # Maximum simultaneous interviews
IDLE_TIMEOUT = 900           # 15 minutes - auto-cleanup idle sessions
ACTIVITY_CHECK_INTERVAL = 60 # Check every 60 seconds
EMPTY_ROOM_GRACE_PERIOD = 3  # Wait 3 seconds before cleanup
```

### RAG Settings (rag.py)

```python
chunk_size = 1000      # Characters per chunk
chunk_overlap = 200    # Overlap between chunks
k = 4                  # Number of chunks to retrieve
deduplicate = True     # Remove duplicate chunks
```

### Voice Models (agent.py)

```python
AgentSession(
    stt="assemblyai/universal-streaming:en",  # Speech-to-Text
    llm=google.LLM(model="gemini-3.5-flash-lite"),  # Language Model (GEMINI_MODEL)
    tts="cartesia/sonic-3:9626c31c-...",       # Text-to-Speech (British male)
    vad=silero.VAD.load(),                     # Voice Activity Detection
)
```

---

## Troubleshooting

### "Failed to connect to token server"
- **Check:** Is the token server running on port 8000?
- **Fix:** Run `cd backend && uv run token_server.py` in a separate terminal

### "No audio from agent"
- **Check:** Is the agent server running?
- **Check:** Browser microphone permissions granted?
- **Fix:** Open browser console (F12) and check for WebRTC errors

### "Resume upload fails"
- **422:** The PDF has no text layer (scanned image) or is password protected. Export a text PDF.
- **502:** Gemini call failed. Check `GOOGLE_API_KEY` and `GEMINI_MODEL` in `backend/.env.local`.
- **Slow first upload / start:** The embedding model downloads on first run.

### "Results screen shows an error"
- **"too short to evaluate":** Answer at least two questions before ending.
- **"Could not generate the evaluation":** Check the agent terminal logs; usually a Gemini quota or key problem.

### "Maximum concurrent sessions reached"
- **Cause:** 5 other interviews are active
- **Fix:** Wait for sessions to end, or increase `MAX_CONCURRENT_SESSIONS` in `agent.py`

### "Transcript not showing"
- **Wait:** First transcription may take 5-10 seconds
- **Check:** Open browser console (F12) for errors
- **Note:** Transcriptions appear after you **stop** speaking (VAD detects end-of-speech)

### "Rate limit errors"
- **Cause:** Google/AssemblyAI API quota exceeded
- **Fix:** Check your API key usage dashboards
- **Prevention:** Reduce `MAX_CONCURRENT_SESSIONS` to control costs

---

## Development

### Development Tools

This project was built using **AI-assisted development**:
- **IDE:** [Cursor](https://cursor.com) - AI-powered code editor
- **AI Model:** Claude Sonnet 4.5 for code generation, architecture design, and iterative development
- **Workflow:** Iterative development with AI pair programming for rapid prototyping and refinement

### Code Quality

```bash
# Frontend linting
cd frontend
npm run lint

# Python formatting (if using black/ruff)
cd backend
uv run ruff format .
```

### Hot Reload

- **Frontend:** Vite provides instant HMR (Hot Module Replacement)
- **Backend:** Restart agent/token server manually after code changes

---

## Security Notes

⚠️ **This is a development setup. Do NOT use in production without:**

1. **Authentication:** Add OAuth/JWT to token server
2. **Rate limiting:** Prevent token farming
3. **CORS restriction:** Change from `*` to specific domains
4. **Input validation:** Sanitize room names, usernames
5. **Secrets management:** Use AWS Secrets Manager, GCP Secret Manager, or HashiCorp Vault
6. **HTTPS only:** Force SSL for all connections

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is for educational purposes. Check with LiveKit, Google, Hugging Face, AssemblyAI, and Cartesia for their respective license terms.

---

## Acknowledgments

- **LiveKit:** Real-time voice infrastructure and Agents SDK
- **Google:** Gemini for conversation, resume parsing and evaluation
- **Hugging Face / BAAI:** bge embedding model
- **AssemblyAI:** High-quality speech-to-text
- **Cartesia:** Ultra-low latency text-to-speech
- **LangChain:** RAG and document processing utilities
- **ChromaDB:** Vector database for semantic search

---

## Support

- **Architecture & Design:** See [DESIGN.md](DESIGN.md) for detailed design decisions, trade-offs, and system architecture
- **Quick Reference:** See [Configuration Options](#configuration-options) for runtime settings
- **Troubleshooting:** See [Troubleshooting](#troubleshooting) for common issues

---

## Roadmap

- [x] Post-interview results screen (in-memory, not persisted)
- [ ] Persistent interview history (database integration)
- [x] Resume parsing for better context
- [ ] Multi-language support
- [ ] Video analysis (body language, eye contact)
- [ ] Custom interviewer voices
- [ ] Screen sharing for code walkthroughs


---

**Built with ❤️ using LiveKit, Gemini, and modern web technologies**

