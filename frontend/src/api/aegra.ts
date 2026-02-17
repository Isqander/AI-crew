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
  GraphTopology,
  GraphConfig,
} from '../types'
import { mapStateMessages } from '../types'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8081'

class AegraClient {
  private baseUrl: string
  private assistantId: string = 'dev_team'
  /** Guard against concurrent refresh requests */
  private refreshPromise: Promise<boolean> | null = null

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl
  }

  /** Public getter for the API base URL (used in UI display) */
  getBaseUrl(): string {
    return this.baseUrl
  }

  private getAuthHeaders(): Record<string, string> {
    const token = useAuthStore.getState().accessToken
    if (token) {
      return { Authorization: `Bearer ${token}` }
    }
    return {}
  }

  /**
   * Try to refresh the access token using the stored refresh token.
   * Returns true if refresh succeeded, false otherwise.
   * Concurrent calls are coalesced into a single request.
   */
  private async tryRefreshToken(): Promise<boolean> {
    if (this.refreshPromise) return this.refreshPromise

    this.refreshPromise = (async () => {
      const { refreshToken, setAuth, user, logout } = useAuthStore.getState()
      if (!refreshToken) {
        logout()
        return false
      }

      try {
        const resp = await fetch(`${this.baseUrl}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })

        if (!resp.ok) {
          logout()
          return false
        }

        const data: { access_token: string; refresh_token: string } = await resp.json()
        if (user) {
          setAuth(user, data.access_token, data.refresh_token)
        }
        return true
      } catch {
        logout()
        return false
      } finally {
        this.refreshPromise = null
      }
    })()

    return this.refreshPromise
  }

  private async fetch<T>(
    endpoint: string,
    options: RequestInit = {},
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`

    const doFetch = () =>
      fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...this.getAuthHeaders(),
          ...options.headers,
        },
      })

    let response = await doFetch()

    // On 401 — try refresh once, then retry the original request
    if (response.status === 401) {
      const refreshed = await this.tryRefreshToken()
      if (refreshed) {
        response = await doFetch()
      }
    }

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
   * Get the latest run for a thread (for error checking)
   */
  async getLatestRun(threadId: string): Promise<Run | null> {
    const runs = await this.fetch<Run[]>(`/threads/${threadId}/runs?limit=1`)
    return runs?.[0] || null
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
   * Create a raw SSE stream response for a thread run.
   * Returns the raw Response so the caller can read the stream manually
   * (e.g., with AbortController support in hooks).
   *
   * Includes 401→refresh→retry logic (same as `fetch`).
   */
  async createStreamResponse(
    threadId: string,
    body: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<Response> {
    const url = `${this.baseUrl}/threads/${threadId}/runs/stream`

    const doFetch = () =>
      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...this.getAuthHeaders(),
        },
        body: JSON.stringify(body),
        signal,
      })

    let response = await doFetch()

    if (response.status === 401) {
      const refreshed = await this.tryRefreshToken()
      if (refreshed) {
        response = await doFetch()
      }
    }

    if (!response.ok) {
      throw new Error(`Stream failed: ${response.status} ${response.statusText}`)
    }

    return response
  }

  /**
   * Stream run events (async generator — for simple consumption)
   */
  async *streamRun(
    threadId: string,
    input: CreateTaskInput,
  ): AsyncGenerator<{ event: string; data: unknown }> {
    const response = await this.createStreamResponse(threadId, {
      assistant_id: this.assistantId,
      input: {
        task: input.task,
        repository: input.repository || null,
        context: input.context || null,
      },
      stream_mode: 'values',
    })

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
    return mapStateMessages(state.values?.messages || [])
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
  // Auth
  // ==========================================

  /**
   * Login with email and password
   */
  async login(email: string, password: string): Promise<{
    user: { id: string; email: string; display_name: string; created_at: string; is_active: boolean }
    access_token: string
    refresh_token: string
  }> {
    // Auth endpoints don't need the auth header
    const url = `${this.baseUrl}/auth/login`
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(data.detail || `Login failed: ${response.status}`)
    }
    return response.json()
  }

  /**
   * Register a new user
   */
  async register(email: string, password: string, displayName: string): Promise<{
    user: { id: string; email: string; display_name: string; created_at: string; is_active: boolean }
    access_token: string
    refresh_token: string
  }> {
    const url = `${this.baseUrl}/auth/register`
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, display_name: displayName }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({ detail: 'Registration failed' }))
      throw new Error(data.detail || `Registration failed: ${response.status}`)
    }
    return response.json()
  }

  // ==========================================
  // Graph Config (for Settings page)
  // ==========================================

  /**
   * Get agent LLM configuration for a graph
   */
  async getGraphConfig(graphId: string): Promise<GraphConfig> {
    return this.fetch<GraphConfig>(`/graph/config/${graphId}`)
  }

  /**
   * Get graph topology for visualization
   */
  async getGraphTopology(graphId: string): Promise<GraphTopology> {
    return this.fetch<GraphTopology>(`/graph/topology/${graphId}`)
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
