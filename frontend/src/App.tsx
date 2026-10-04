import { useState, useRef } from 'react'
import { LiveKitRoom, RoomAudioRenderer } from '@livekit/components-react'
import { CallInterface } from './components/CallInterface'
import { ResultScreen } from './components/ResultScreen'
import { MAX_RESUME_BYTES, TOKEN_SERVER_URL, deleteSession, uploadResume } from './api'
import type { ConnectionDetails } from './types'
import './App.css'

function App() {
  const [connectionDetails, setConnectionDetails] = useState<ConnectionDetails | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [resultRoom, setResultRoom] = useState<string | null>(null) // room whose result screen is showing
  const isStartingRef = useRef(false) // Prevent multiple simultaneous starts

  const handleResumeChange = (file: File | null) => {
    setError(null)
    if (!file) {
      setResumeFile(null)
      return
    }
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setResumeFile(null)
      setError('Please choose a PDF file.')
      return
    }
    if (file.size > MAX_RESUME_BYTES) {
      setResumeFile(null)
      setError('Resume is too large (max 5 MB).')
      return
    }
    setResumeFile(file)
  }

  const startInterview = async () => {
    // Prevent multiple simultaneous connection attempts
    if (isStartingRef.current || isConnecting || connectionDetails) {
      return
    }
    if (!resumeFile) {
      setError('Please upload your resume (PDF) first.')
      return
    }

    isStartingRef.current = true
    setIsConnecting(true)
    setError(null)

    let uploadedRoom: string | null = null

    try {
      // Check capacity before starting
      let capacityResponse
      try {
        capacityResponse = await fetch(`${TOKEN_SERVER_URL}/capacity-check`)
      } catch (fetchError) {
        throw new Error(
          `Cannot connect to token server at ${TOKEN_SERVER_URL}. ` +
          `Make sure the token server is running on port 8000.`
        )
      }
      
      if (!capacityResponse.ok) {
        throw new Error(`Token server returned error: ${capacityResponse.status} ${capacityResponse.statusText}`)
      }
      
      const capacityData = await capacityResponse.json()

      if (!capacityData.has_capacity) {
        throw new Error(
          capacityData.message || 
          'Maximum number of interviews reached. Please try again later.'
        )
      }

      // Generate a unique room name for this interview
      const roomName = `interview-${Date.now()}`
      const username = 'candidate'

      // Upload + parse the resume. The agent reads it from the backend when it joins the room.
      await uploadResume(roomName, resumeFile)
      uploadedRoom = roomName

      // Fetch LiveKit URL
      let urlResponse
      try {
        urlResponse = await fetch(`${TOKEN_SERVER_URL}/livekit-url`)
      } catch (fetchError) {
        throw new Error('Cannot connect to token server to get LiveKit URL')
      }
      
      if (!urlResponse.ok) {
        throw new Error(`Failed to get LiveKit URL: ${urlResponse.status}`)
      }
      
      const urlData = await urlResponse.json()

      if (urlData.error) {
        throw new Error(urlData.error)
      }

      // Fetch access token (this will also check capacity server-side)
      const tokenResponse = await fetch(
        `${TOKEN_SERVER_URL}/token?room=${roomName}&username=${username}`
      )
      
      if (!tokenResponse.ok) {
        const errorData = await tokenResponse.json()
        throw new Error(errorData.detail || 'Failed to get access token')
      }

      const tokenData = await tokenResponse.json()

      if (tokenData.error) {
        throw new Error(tokenData.error)
      }

      // Set connection details to trigger LiveKitRoom render
      setConnectionDetails({
        url: urlData.url,
        token: tokenData.token,
        roomName: roomName,
      })
      
      // Note: isConnecting stays true until connection is established
      // It will be reset in endInterview or if there's an error
    } catch (err) {
      console.error('Failed to start interview:', err)
      // Don't leave a parsed resume behind if we never got into the room
      if (uploadedRoom) deleteSession(uploadedRoom)
      setError(err instanceof Error ? err.message : 'Failed to connect')
      setIsConnecting(false)
      isStartingRef.current = false
    }
  }

  const endInterview = () => {
    // Show the result screen for the interview that just ended
    if (connectionDetails) {
      setResultRoom(connectionDetails.roomName)
    }
    setConnectionDetails(null)
    setIsConnecting(false)
    isStartingRef.current = false
    setError(null)
  }

  // Show the result screen once an interview has ended
  if (!connectionDetails && resultRoom) {
    return (
      <div className="app app-scroll">
        <ResultScreen
          room={resultRoom}
          onRestart={() => {
            setResultRoom(null)
            setResumeFile(null)
          }}
        />
      </div>
    )
  }

  // Show start screen if not connected
  if (!connectionDetails) {
    return (
      <div className="app">
        <div className="start-screen">
          <h1>Project Interview Coach</h1>
          <p>Upload your resume and discuss it with an AI interviewer</p>
          <label className={`resume-upload ${resumeFile ? 'has-file' : ''}`}>
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={isConnecting}
              onChange={(e) => handleResumeChange(e.target.files?.[0] ?? null)}
            />
            <span className="resume-upload-title">
              {resumeFile ? resumeFile.name : 'Choose your resume (PDF, max 5 MB)'}
            </span>
            <span className="resume-upload-hint">
              {resumeFile ? 'Click to choose a different file' : 'The interviewer will ask questions based on it'}
            </span>
          </label>
          {error && (
            <div className="error-message">
              <p>❌ Error: {error}</p>
            </div>
          )}
          <button
            className="start-button"
            onClick={startInterview}
            disabled={isConnecting || !resumeFile}
          >
            {isConnecting ? 'Preparing interview...' : 'Start Interview'}
          </button>
        </div>
      </div>
    )
  }

  // Show LiveKit room when connected
  return (
    <div className="app">
      <LiveKitRoom
        serverUrl={connectionDetails.url}
        token={connectionDetails.token}
        connect={true}
        connectOptions={{
          autoSubscribe: true,
        }}
        options={{
          audioCaptureDefaults: {
            autoGainControl: true,
            echoCancellation: true,
            noiseSuppression: true,
          },
          publishDefaults: {
            dtx: true,
            red: true,
            stopMicTrackOnMute: true,
          },
        }}
        onDisconnected={endInterview}
      >
        <CallInterface onEndInterview={endInterview} />
        <RoomAudioRenderer />
      </LiveKitRoom>
    </div>
  )
}

export default App
