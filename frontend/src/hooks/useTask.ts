import { useState, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { aegraClient } from '../api/aegra'
import type { CreateTaskInput, ThreadState, Message, Thread } from '../types'

interface UseTaskReturn {
  // State
  thread: Thread | null
  threadState: ThreadState | null
  messages: Message[]
  isLoading: boolean
  isCreating: boolean
  error: Error | null
  
  // Actions
  createTask: (input: CreateTaskInput) => Promise<void>
  sendClarification: (response: string) => Promise<void>
  refreshState: () => void
}

export function useTask(threadId?: string): UseTaskReturn {
  const queryClient = useQueryClient()
  const [activeThread, setActiveThread] = useState<Thread | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  // Get thread
  const { data: thread } = useQuery({
    queryKey: ['thread', threadId],
    queryFn: () => aegraClient.getThread(threadId!),
    enabled: !!threadId,
  })

  // Get thread state
  const { 
    data: threadState, 
    isLoading: isLoadingState,
    refetch: refetchState,
  } = useQuery({
    queryKey: ['threadState', threadId || activeThread?.thread_id],
    queryFn: () => aegraClient.getThreadState(threadId || activeThread!.thread_id),
    enabled: !!(threadId || activeThread),
    refetchInterval: (data) => {
      // Auto-refresh while task is running
      const state = data as ThreadState | undefined
      if (state?.values?.current_agent && 
          state.values.current_agent !== 'complete' &&
          state.values.current_agent !== 'waiting_for_user') {
        return 2000 // Poll every 2 seconds
      }
      return false
    },
  })

  // Extract messages from state
  const messages: Message[] = (threadState?.values?.messages || []).map((msg: any, idx: number) => ({
    id: `msg-${idx}`,
    type: msg.type === 'human' ? 'human' : 'ai',
    content: typeof msg === 'string' ? msg : (msg.content || ''),
    name: msg.name,
    created_at: new Date().toISOString(),
  }))

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
      setActiveRunId(result.run_id)

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
      setActiveRunId(run.run_id)
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
