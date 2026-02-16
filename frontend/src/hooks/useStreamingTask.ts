import { useState, useCallback, useRef } from 'react'
import { aegraClient } from '../api/aegra'
import type { DevTeamState } from '../types'

export function useStreamingTask(threadId: string | null) {
  const [state, setState] = useState<Partial<DevTeamState> | null>(null)
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
      const response = await aegraClient.createStreamResponse(
        threadId,
        { assistant_id: assistantId },
        controller.signal,
      )

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
                const node = data.node ? `[${data.node}] ` : ''
                setError(new Error(`${node}${data.message || data.error || 'Unknown error'}`))
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
