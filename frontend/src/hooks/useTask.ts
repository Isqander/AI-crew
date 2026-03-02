import { useState, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { aegraClient } from '../api/aegra'
import type { CreateTaskInput, ThreadState, Message, Thread } from '../types'
import { mapStateMessages } from '../types'

interface UseTaskReturn {
  // State
  thread: Thread | null
  threadState: ThreadState | null
  messages: Message[]
  isLoading: boolean
  isCreating: boolean
  error: Error | null
  runError: string | null

  // Actions
  createTask: (input: CreateTaskInput) => Promise<void>
  sendClarification: (response: string) => Promise<void>
  refreshState: () => void
}

export function useTask(threadId?: string): UseTaskReturn {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const [activeThread, setActiveThread] = useState<Thread | null>(null)

  // Get thread
  const { data: thread } = useQuery({
    queryKey: ['thread', threadId],
    queryFn: () => aegraClient.getThread(threadId!),
    enabled: !!threadId,
  })

  // Get latest run (for error detection)
  const effectiveThreadId = threadId || activeThread?.thread_id
  const { data: latestRun } = useQuery({
    queryKey: ['latestRun', effectiveThreadId],
    queryFn: () => aegraClient.getLatestRun(effectiveThreadId!),
    enabled: !!effectiveThreadId,
    refetchInterval: (query) => {
      const run = query.state.data
      if (run?.status === 'error' || run?.status === 'success') return false
      return 3000
    },
  })

  const runError = latestRun?.status === 'error'
    ? (latestRun.error_message || t('useTask.unknownRunError'))
    : null

  // Get thread state
  const {
    data: threadState,
    isLoading: isLoadingState,
    refetch: refetchState,
  } = useQuery({
    queryKey: ['threadState', effectiveThreadId],
    queryFn: () => aegraClient.getThreadState(effectiveThreadId!),
    enabled: !!effectiveThreadId,
    refetchInterval: (query) => {
      // Stop polling on run error
      if (runError) return false
      // Auto-refresh while task is running
      const state = query.state.data
      if (state?.values?.error) return false
      if (state?.values?.current_agent &&
          state.values.current_agent !== 'complete' &&
          state.values.current_agent !== 'waiting_for_user') {
        return 2000 // Poll every 2 seconds
      }
      return false
    },
  })

  // Extract messages from state
  const messages: Message[] = mapStateMessages(threadState?.values?.messages || [])

  // Create task mutation — uses /api/run for proper graph routing
  const createTaskMutation = useMutation({
    mutationFn: async (input: CreateTaskInput) => {
      // Use /api/run endpoint which handles:
      // - Switch-Agent routing (when graph_id is not specified)
      // - Thread creation (when thread_id is null)
      // - Run creation in Aegra
      const result = await aegraClient.createTaskRun(input)

      const newThread: Thread = {
        thread_id: result.thread_id,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        metadata: { task: input.task, graph_id: result.graph_id },
        status: 'busy',
      }
      setActiveThread(newThread)

      return { thread: newThread, run: result }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threads'] })
    },
  })

  // Send clarification mutation
  const clarificationMutation = useMutation({
    mutationFn: async (response: string) => {
      const tid = threadId || activeThread?.thread_id

      if (!tid) {
        throw new Error('No active thread')
      }

      // Update state and resume the graph in a single API call.
      // command: { update: {...} } patches the checkpointed state and
      // tells LangGraph to continue from the interrupt point.
      const run = await aegraClient.continueThread(tid, {
        clarification_response: response,
        needs_clarification: false,
      })
      return run
    },
    onSuccess: () => {
      refetchState()
    },
  })

  const createTask = useCallback(async (input: CreateTaskInput) => {
    await createTaskMutation.mutateAsync(input)
  }, [createTaskMutation])

  const sendClarification = useCallback(async (response: string) => {
    await clarificationMutation.mutateAsync(response)
  }, [clarificationMutation])

  const refreshState = useCallback(() => {
    refetchState()
  }, [refetchState])

  return {
    thread: thread || activeThread,
    threadState: threadState || null,
    messages,
    isLoading: isLoadingState || clarificationMutation.isPending,
    isCreating: createTaskMutation.isPending,
    error: createTaskMutation.error || clarificationMutation.error || null,
    runError,
    createTask,
    sendClarification,
    refreshState,
  }
}

// Hook for listing all threads
export function useThreads() {
  return useQuery({
    queryKey: ['threads'],
    queryFn: () => aegraClient.listThreads(),
  })
}
