// API Types for Aegra/LangGraph integration

export interface Thread {
  thread_id: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
  status: 'idle' | 'busy' | 'interrupted' | 'error'
}

export interface Run {
  run_id: string
  thread_id: string
  assistant_id: string
  created_at: string
  updated_at: string
  status: 'pending' | 'running' | 'success' | 'error' | 'interrupted'
  metadata: Record<string, unknown>
}

export interface Message {
  id: string
  type: 'human' | 'ai' | 'system'
  content: string
  name?: string
  created_at: string
}

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
  messages: Message[]
  
  // Control
  current_agent: string
  needs_clarification: boolean
  clarification_question?: string
  clarification_context?: string
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

// Task creation form
export interface CreateTaskInput {
  task: string
  repository?: string
  context?: string
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
