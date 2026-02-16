// API Types for Aegra/LangGraph integration

// ── Thread metadata (typed keys we store in thread.metadata) ──

export interface ThreadMetadata {
  task?: string
  graph_id?: string
  [key: string]: unknown
}

export interface Thread {
  thread_id: string
  created_at: string
  updated_at: string
  metadata: ThreadMetadata
  status: 'idle' | 'busy' | 'interrupted' | 'error'
}

export interface Run {
  run_id: string
  thread_id: string
  assistant_id: string
  created_at: string
  updated_at: string
  status: 'pending' | 'running' | 'success' | 'error' | 'interrupted'
  error_message?: string
  metadata: Record<string, unknown>
}

// ── Messages ──

/** Message as stored in the frontend */
export interface Message {
  id: string
  type: 'human' | 'ai' | 'system'
  content: string
  name?: string
  created_at: string
}

/** Raw message shape coming from LangGraph state (before mapping to Message) */
export interface StateMessage {
  type?: string
  content: string
  name?: string
}

// ── State ──

export interface ThreadState {
  values: DevTeamState
  next: string[]
  tasks: unknown[]
  metadata: Record<string, unknown>
}

export interface DevTeamState {
  // Input
  task: string
  repository?: string
  context?: string
  
  // Progress
  requirements: string[]
  user_stories: UserStory[]
  architecture: Record<string, unknown>
  tech_stack: string[]
  code_files: CodeFile[]
  review_comments: string[]
  issues_found: string[]
  
  // Output
  pr_url?: string
  summary: string
  
  // Messages
  messages: StateMessage[]
  
  // Error
  error?: string

  // Control
  current_agent: string
  needs_clarification: boolean
  clarification_question?: string
  clarification_context?: string
}

// ── Graph topology types (used by GraphVisualization) ──

export interface TopologyNode {
  id: string
  [key: string]: unknown
}

export interface TopologyEdge {
  source: string
  target: string
  conditional?: boolean
  data?: string
}

export interface AgentConfig {
  model: string
  temperature: number
  fallback_model: string | null
  endpoint: string
}

export interface PromptInfo {
  system: string
  templates: string[]
}

export interface GraphTopology {
  graph_id: string
  topology: { nodes: TopologyNode[]; edges: TopologyEdge[] }
  agents: Record<string, AgentConfig>
  prompts: Record<string, PromptInfo>
  manifest: {
    agents?: { id: string; display_name: string }[]
    [key: string]: unknown
  }
}

export interface UserStory {
  id: string
  title: string
  description: string
  acceptance_criteria: string[]
  priority: 'high' | 'medium' | 'low'
}

export interface CodeFile {
  path: string
  content: string
  language: string
}

// Graph selection
export interface GraphListItem {
  graph_id: string
  display_name: string
  description: string
  version: string
  task_types: string[]
  agents: { id: string; display_name: string }[]
  features: string[]
}

// Task creation form
export interface CreateTaskInput {
  task: string
  repository?: string
  context?: string
  graph_id?: string  // null/undefined → LLM auto-selects
}

// Agent types
export type AgentName = 'pm' | 'analyst' | 'architect' | 'developer' | 'qa' | 'waiting_for_user' | 'complete'

export interface AgentInfo {
  name: AgentName
  displayName: string
  description: string
  color: string
}

export const AGENTS: Record<AgentName, AgentInfo> = {
  pm: {
    name: 'pm',
    displayName: 'Project Manager',
    description: 'Координация и управление задачами',
    color: 'cyan',
  },
  analyst: {
    name: 'analyst',
    displayName: 'Аналитик',
    description: 'Сбор и уточнение требований',
    color: 'magenta',
  },
  architect: {
    name: 'architect',
    displayName: 'Архитектор',
    description: 'Проектирование системы',
    color: 'lime',
  },
  developer: {
    name: 'developer',
    displayName: 'Разработчик',
    description: 'Написание кода',
    color: 'amber',
  },
  qa: {
    name: 'qa',
    displayName: 'QA Инженер',
    description: 'Тестирование и ревью',
    color: 'cyan',
  },
  waiting_for_user: {
    name: 'waiting_for_user',
    displayName: 'Ожидание ответа',
    description: 'Требуется ваш ввод',
    color: 'amber',
  },
  complete: {
    name: 'complete',
    displayName: 'Завершено',
    description: 'Задача выполнена',
    color: 'lime',
  },
}
