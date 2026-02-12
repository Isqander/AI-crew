/**
 * Aegra API Client
 * 
 * Provides methods for interacting with the Aegra/LangGraph backend via Gateway.
 */

import { useAuthStore } from '../store/authStore'
import type { 
  Thread, 
  Run, 
  ThreadState, 
  CreateTaskInput,
  Message,
  GraphListItem,
} from '../types'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8081'

class AegraClient {
  private baseUrl: string
  private assistantId: string = 'dev_team'

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl
  }

  private getAuthHeaders(): Record<string, string> {
    const token = useAuthStore.getState().accessToken
    if (token) {
      return { Authorization: `Bearer ${token}` }
    }
    return {}
  }

  private async fetch<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...this.getAuthHeaders(),
        ...options.headers,
      },
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`API Error: ${response.status} - ${error}`)
    }

    return response.json()
  }

  // ==========================================
  // Threads
  // ==========================================

  /**
   * Create a new thread for a task
   */
  async createThread(metadata?: Record<string, unknown>): Promise<Thread> {
    return this.fetch<Thread>('/threads', {
      method: 'POST',
      body: JSON.stringify({ metadata }),
    })
  }

  /**
   * Get thread by ID
   */
  async getThread(threadId: string): Promise<Thread> {
    return this.fetch<Thread>(`/threads/${threadId}`)
  }

  /**
   * List all threads
   */
  async listThreads(): Promise<Thread[]> {
    const response = await this.fetch<{ threads: Thread[] }>('/threads')
    return response.threads || []
  }

  /**
   * Get thread state
   */
  async getThreadState(threadId: string): Promise<ThreadState> {
    return this.fetch<ThreadState>(`/threads/${threadId}/state`)
  }

  /**
   * Update thread state (for HITL responses)
   */
  async updateThreadState(
    threadId: string,
    values: Record<string, unknown>
  ): Promise<ThreadState> {
    return this.fetch<ThreadState>(`/threads/${threadId}/state`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
  }

  // ==========================================
  // Runs
  // ==========================================

  /**
   * Create a new run (start processing a task)
   */
  async createRun(
    threadId: string,
    input: CreateTaskInput
  ): Promise<Run> {
    return this.fetch<Run>(`/threads/${threadId}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        assistant_id: this.assistantId,
        input: {
          task: input.task,
          repository: input.repository || null,
          context: input.context || null,
        },
      }),
    })
  }

  /**
   * Get run status
   */
  async getRun(threadId: string, runId: string): Promise<Run> {
    return this.fetch<Run>(`/threads/${threadId}/runs/${runId}`)
  }

  /**
   * Resume a run after HITL interrupt
   */
  async resumeRun(
    threadId: string,
    runId: string,
    input: Record<string, unknown>
  ): Promise<Run> {
    return this.fetch<Run>(`/threads/${threadId}/runs/${runId}/resume`, {
      method: 'POST',
      body: JSON.stringify({ input }),
    })
  }

  /**
   * Continue a thread after an interrupt (e.g., after clarification).
   *
   * If a `stateUpdate` is provided, the run is created with
   * `command: { update: stateUpdate }` which applies the update to
   * the checkpointed state **and** resumes graph execution in a
   * single API call.
   *
   * If no stateUpdate is given, an empty input `{}` is sent which
   * tells LangGraph to resume from the last checkpoint as-is.
   */
  async continueThread(
    threadId: string,
    stateUpdate?: Record<string, unknown>,
  ): Promise<Run> {
    const body: Record<string, unknown> = {
      assistant_id: this.assistantId,
    }

    if (stateUpdate && Object.keys(stateUpdate).length > 0) {
      // Use command.update to patch state and resume in one call
      body.command = { update: stateUpdate }
    } else {
      // Empty input → continue from the last checkpoint unchanged
      body.input = {}
    }

    return this.fetch<Run>(`/threads/${threadId}/runs`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  /**
   * List runs for a thread (most recent first)
   */
  async listRuns(threadId: string, limit: number = 10): Promise<Run[]> {
    return this.fetch<Run[]>(`/threads/${threadId}/runs?limit=${limit}`)
  }

  /**
   * Cancel a run
   */
  async cancelRun(threadId: string, runId: string): Promise<void> {
    await this.fetch(`/threads/${threadId}/runs/${runId}/cancel`, {
      method: 'POST',
    })
  }

  // ==========================================
  // Streaming
  // ==========================================

  /**
   * Stream run events
   */
  async *streamRun(
    threadId: string,
    input: CreateTaskInput
  ): AsyncGenerator<{ event: string; data: unknown }> {
    const url = `${this.baseUrl}/threads/${threadId}/runs/stream`
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...this.getAuthHeaders(),
      },
      body: JSON.stringify({
        assistant_id: this.assistantId,
        input: {
          task: input.task,
          repository: input.repository || null,
          context: input.context || null,
        },
        stream_mode: 'values',
      }),
    })

    if (!response.ok) {
      throw new Error(`Stream error: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            yield { event: 'data', data }
          } catch {
            // Skip invalid JSON
          }
        } else if (line.startsWith('event: ')) {
          yield { event: line.slice(7), data: null }
        }
      }
    }
  }

  // ==========================================
  // Messages (convenience methods)
  // ==========================================

  /**
   * Get messages from thread state
   */
  async getMessages(threadId: string): Promise<Message[]> {
    const state = await this.getThreadState(threadId)
    return (state.values?.messages || []).map((msg, idx) => ({
      id: `msg-${idx}`,
      type: msg.type || 'ai',
      content: typeof msg === 'string' ? msg : msg.content,
      name: msg.name,
      created_at: new Date().toISOString(),
    }))
  }

  // ==========================================
  // Graphs
  // ==========================================

  /**
   * Get list of available graphs
   */
  async getGraphList(): Promise<GraphListItem[]> {
    const response = await this.fetch<{ graphs: GraphListItem[] }>('/graph/list')
    return response.graphs || []
  }

  // ==========================================
  // Task creation (via /api/run with graph selection)
  // ==========================================

  /**
   * Create a task via /api/run endpoint (with optional graph selection)
   */
  async createTaskRun(input: CreateTaskInput): Promise<{
    thread_id: string
    run_id: string
    graph_id: string
    classification?: { graph_id: string; complexity: number; reasoning: string }
  }> {
    return this.fetch('/api/run', {
      method: 'POST',
      body: JSON.stringify({
        task: input.task,
        repository: input.repository || null,
        context: input.context || null,
        graph_id: input.graph_id || null,
      }),
    })
  }

  // ==========================================
  // Health
  // ==========================================

  /**
   * Check API health
   */
  async health(): Promise<{ status: string }> {
    return this.fetch<{ status: string }>('/health')
  }
}

// Export singleton instance
export const aegraClient = new AegraClient()

// Export class for custom instances
export { AegraClient }
