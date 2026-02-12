import { useState, useCallback, useRef } from 'react'
import { useAuthStore } from '../store/authStore'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8081'

interface DevTeamState {
  task?: string
  current_agent?: string
  requirements?: string[]
  architecture?: Record<string, unknown>
  tech_stack?: string[]
  code_files?: Array<{ path: string; content: string; language: string }>
  review_comments?: string[]
  issues_found?: string[]
  pr_url?: string
  summary?: string
  needs_clarification?: boolean
  clarification_question?: string
  messages?: Array<{ type: string; content: string; name?: string }>
  [key: string]: unknown
}

export function useStreamingTask(threadId: string | null) {
  const [state, setState] = useState<DevTeamState | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const startStream = useCallback(async (assistantId: string = 'dev_team') => {
    if (!threadId) return

    setIsStreaming(true)
    setError(null)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const token = useAuthStore.getState().accessToken
      const response = await fetch(
        `${API_URL}/threads/${threadId}/runs/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ assistant_id: assistantId }),
          signal: controller.signal,
        }
      )

      if (!response.ok) {
        throw new Error(`Stream failed: ${response.status} ${response.statusText}`)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
            continue
          }
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              // Handle error events from Aegra
              if (currentEvent === 'error' || data.error) {
                setError(new Error(data.message || data.error || 'Unknown error'))
                return
              }
              if (data && typeof data === 'object') {
                setState(prev => ({ ...prev, ...data }))
              }
            } catch {
              // Skip non-JSON data lines
            }
            currentEvent = ''
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError(err as Error)
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }, [threadId])

  const stopStream = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { state, isStreaming, error, startStream, stopStream }
}
