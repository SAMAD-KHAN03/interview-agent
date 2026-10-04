import type { ReportResponse, ResumeSummary } from './types'

// URL of the token server (also hosts the resume + report endpoints)
export const TOKEN_SERVER_URL = 'http://localhost:8000'

export const MAX_RESUME_BYTES = 5 * 1024 * 1024

// FastAPI returns `detail` as a string (HTTPException) or a list (validation errors)
async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg
  } catch {
    // body was not JSON
  }
  return `${fallback} (${response.status})`
}

export async function uploadResume(room: string, file: File): Promise<ResumeSummary> {
  const form = new FormData()
  form.append('room', room)
  form.append('file', file)

  let response: Response
  try {
    response = await fetch(`${TOKEN_SERVER_URL}/resume`, { method: 'POST', body: form })
  } catch {
    throw new Error(`Cannot connect to token server at ${TOKEN_SERVER_URL}.`)
  }
  if (!response.ok) {
    throw new Error(await readError(response, 'Resume upload failed'))
  }
  return response.json()
}

export async function fetchReport(room: string): Promise<ReportResponse> {
  const response = await fetch(`${TOKEN_SERVER_URL}/sessions/${room}/report`)
  if (!response.ok) {
    throw new Error(await readError(response, 'Could not load your results'))
  }
  return response.json()
}

// Tells the backend the user has seen the result so it can drop everything.
// `keepalive` lets this still go out while the tab is closing.
export function deleteSession(room: string): void {
  fetch(`${TOKEN_SERVER_URL}/sessions/${room}`, { method: 'DELETE', keepalive: true }).catch(() => {
    // Best effort: the backend also sweeps expired sessions on its own.
  })
}
