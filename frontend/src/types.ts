// Shared types for the application

export type AgentState = 'initializing' | 'listening' | 'thinking' | 'speaking'

export interface TranscriptSegment {
  id: string
  text: string
  participantIdentity: string
  isFinal: boolean
  timestamp: number
}

export interface ConnectionDetails {
  url: string
  token: string
  roomName: string
}

// ---- Resume upload ----
export interface ResumeSummary {
  room: string
  candidate_name: string
  skills: string[]
  projects: string[]
}

// ---- Interview report (mirrors backend/schemas.py) ----
export interface Metric {
  score: number
  explanation: string
}

export interface TopicScore {
  topic: string
  score: number
  comment: string
}

export interface InterviewReport {
  overall_rating: number
  summary: string
  clarity: Metric
  responsiveness: Metric
  technical_depth: Metric
  resume_consistency: Metric
  topics: TopicScore[]
  strengths: string[]
  improvements: string[]
  practice_suggestions: string[]
}

export interface ReportResponse {
  status: 'pending' | 'ready' | 'failed'
  report: InterviewReport | null
  error: string | null
}
