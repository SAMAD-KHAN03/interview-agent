import { useEffect, useState } from 'react'
import { deleteSession, fetchReport } from '../api'
import type { InterviewReport, Metric } from '../types'

interface ResultScreenProps {
  room: string
  onRestart: () => void
}

const POLL_INTERVAL_MS = 2000
const MAX_WAIT_MS = 90_000

type ViewState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; report: InterviewReport }

function scoreLevel(score: number): 'low' | 'mid' | 'high' {
  if (score >= 8) return 'high'
  if (score >= 5) return 'mid'
  return 'low'
}

function ScoreRing({ score }: { score: number }) {
  const radius = 54
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - score / 10)
  return (
    <div className={`score-ring ${scoreLevel(score)}`} role="img" aria-label={`Overall rating ${score} out of 10`}>
      <svg viewBox="0 0 128 128">
        <circle className="score-ring-track" cx="64" cy="64" r={radius} />
        <circle
          className="score-ring-value"
          cx="64"
          cy="64"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="score-ring-label">
        <span className="score-ring-number">{score}</span>
        <span className="score-ring-max">/ 10</span>
      </div>
    </div>
  )
}

function MetricCard({ title, metric }: { title: string; metric: Metric }) {
  return (
    <div className="metric-card">
      <div className="metric-header">
        <h3>{title}</h3>
        <span className={`metric-score ${scoreLevel(metric.score)}`}>{metric.score}/10</span>
      </div>
      <div className="bar-track">
        <div className={`bar-fill ${scoreLevel(metric.score)}`} style={{ width: `${metric.score * 10}%` }} />
      </div>
      <p>{metric.explanation}</p>
    </div>
  )
}

export function ResultScreen({ room, onRestart }: ResultScreenProps) {
  const [view, setView] = useState<ViewState>({ kind: 'loading' })

  // Poll until the agent has posted the evaluation (or it failed / timed out)
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const startedAt = Date.now()

    const poll = async () => {
      try {
        const result = await fetchReport(room)
        if (cancelled) return
        if (result.status === 'ready' && result.report) {
          setView({ kind: 'ready', report: result.report })
          return
        }
        if (result.status === 'failed') {
          setView({ kind: 'error', message: result.error || 'The evaluation failed.' })
          return
        }
      } catch (err) {
        if (cancelled) return
        setView({ kind: 'error', message: err instanceof Error ? err.message : 'Could not load your results' })
        return
      }
      if (Date.now() - startedAt > MAX_WAIT_MS) {
        setView({ kind: 'error', message: 'The evaluation is taking too long. Please try another interview.' })
        return
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS)
    }

    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [room])

  // The backend keeps the result only until the user has seen it. Closing the tab counts too.
  useEffect(() => {
    const cleanup = () => deleteSession(room)
    window.addEventListener('pagehide', cleanup)
    return () => window.removeEventListener('pagehide', cleanup)
  }, [room])

  const handleRestart = () => {
    deleteSession(room)
    onRestart()
  }

  if (view.kind === 'loading') {
    return (
      <div className="result-screen result-center">
        <div className="spinner" aria-hidden="true" />
        <h2>Evaluating your interview…</h2>
        <p>This usually takes a few seconds.</p>
      </div>
    )
  }

  if (view.kind === 'error') {
    return (
      <div className="result-screen result-center">
        <h2>We couldn’t produce your results</h2>
        <div className="error-message">
          <p>❌ {view.message}</p>
        </div>
        <button className="start-button" onClick={handleRestart}>
          Start a new interview
        </button>
      </div>
    )
  }

  const { report } = view
  return (
    <div className="result-screen">
      <header className="result-hero">
        <ScoreRing score={report.overall_rating} />
        <div className="result-hero-text">
          <h1>Interview results</h1>
          <p>{report.summary}</p>
        </div>
      </header>

      <section className="metric-grid" aria-label="Performance breakdown">
        <MetricCard title="Clarity of explanation" metric={report.clarity} />
        <MetricCard title="Responsiveness" metric={report.responsiveness} />
        <MetricCard title="Technical depth" metric={report.technical_depth} />
        <MetricCard title="Resume consistency" metric={report.resume_consistency} />
      </section>

      {report.topics.length > 0 && (
        <section className="result-card" aria-label="Topics discussed">
          <h2>Topics discussed</h2>
          <ul className="topic-list">
            {report.topics.map((t) => (
              <li key={t.topic}>
                <div className="topic-row">
                  <span className="topic-name">{t.topic}</span>
                  <span className={`metric-score ${scoreLevel(t.score)}`}>{t.score}/10</span>
                </div>
                <div className="bar-track">
                  <div className={`bar-fill ${scoreLevel(t.score)}`} style={{ width: `${t.score * 10}%` }} />
                </div>
                <p>{t.comment}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="two-col">
        <section className="result-card strengths">
          <h2>Strengths</h2>
          <ul>
            {report.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
        <section className="result-card improvements">
          <h2>Areas to improve</h2>
          <ul>
            {report.improvements.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      </div>

      {report.practice_suggestions.length > 0 && (
        <section className="result-card">
          <h2>What to practise next</h2>
          <ul>
            {report.practice_suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="result-actions">
        <p className="result-note">These results are not saved. They are removed once you leave this screen.</p>
        <button className="start-button" onClick={handleRestart}>
          Start a new interview
        </button>
      </div>
    </div>
  )
}
