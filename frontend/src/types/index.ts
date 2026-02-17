// API Types for Aegra/LangGraph integration

// ── User ──

export interface User {
  id: string
  email: string
  display_name: string
  created_at: string
  is_active: boolean
}

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

/** Convert raw LangGraph state messages to frontend Message format. */
export function mapStateMessages(messages: StateMessage[]): Message[] {
  return messages.map((msg, idx) => ({
    id: `msg-${idx}`,
    type: msg.type === 'human' ? 'human' as const : 'ai' as const,
    content: (typeof msg === 'string' ? msg : msg.content) || '',
    name: msg.name,
    created_at: new Date().toISOString(),
  }))
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

  // Task classification (Wave 1)
  task_type?: string
  task_complexity?: number

  // Progress
  requirements: string[]
  user_stories: UserStory[]
  architecture: Record<string, unknown>
  tech_stack: string[]
  architecture_decisions?: ArchitectureDecision[]
  code_files: CodeFile[]
  implementation_notes?: string
  review_comments: string[]
  issues_found: string[]

  // Test & QA results
  test_results?: Record<string, unknown>

  // Output
  pr_url?: string
  commit_sha?: string
  summary: string

  // Messages
  messages: StateMessage[]

  // Error
  error?: string

  // Control
  current_agent: string
  next_agent?: string
  needs_clarification: boolean
  clarification_question?: string
  clarification_context?: string
  clarification_response?: string
  review_iteration_count?: number
  architect_escalated?: boolean
  retry_count?: number

  // Wave 2: Git-based workflow
  working_branch?: string
  working_repo?: string
  file_manifest?: string[]

  // Wave 2: Sandbox
  sandbox_results?: {
    stdout: string
    stderr: string
    exit_code: number
    tests_passed?: boolean
  }

  // Wave 2: Security
  security_review?: {
    risk_level?: string
    critical: string[]
    warnings: string[]
    info: string[]
  }

  // Wave 2: Deploy & CLI
  deploy_url?: string
  execution_mode?: 'auto' | 'internal' | 'cli'

  // Visual QA
  browser_test_results?: Record<string, unknown>

  // Lint & CI
  lint_status?: string
  lint_log?: string
  ci_status?: string
  ci_log?: string
  ci_run_url?: string
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

export interface GraphConfig {
  graph_id: string
  agents: Record<string, AgentConfig>
}

export interface UserStory {
  id: string
  title: string
  description: string
  acceptance_criteria: string[]
  priority: 'high' | 'medium' | 'low'
}

export interface ArchitectureDecision {
  title: string
  decision: string
  rationale: string
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
export type AgentName =
  | 'pm'
  | 'analyst'
  | 'architect'
  | 'developer'
  | 'reviewer'
  | 'qa'
  | 'security'
  | 'lint_check'
  | 'ci_check'
  | 'git_commit'
  | 'waiting_for_user'
  | 'complete'

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
  reviewer: {
    name: 'reviewer',
    displayName: 'Ревьюер',
    description: 'Код-ревью и проверка качества',
    color: 'violet',
  },
  qa: {
    name: 'qa',
    displayName: 'QA Инженер',
    description: 'Тестирование в sandbox',
    color: 'teal',
  },
  security: {
    name: 'security',
    displayName: 'Security Engineer',
    description: 'Анализ безопасности кода',
    color: 'red',
  },
  lint_check: {
    name: 'lint_check',
    displayName: 'Lint Check',
    description: 'Проверка стиля и синтаксиса кода',
    color: 'orange',
  },
  ci_check: {
    name: 'ci_check',
    displayName: 'CI Check',
    description: 'Проверка CI/CD pipeline',
    color: 'blue',
  },
  git_commit: {
    name: 'git_commit',
    displayName: 'Git Commit',
    description: 'Коммит и создание PR',
    color: 'green',
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
