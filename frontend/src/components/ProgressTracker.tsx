import { clsx } from 'clsx'
import { 
  CheckCircle, 
  Circle, 
  Loader2, 
  AlertCircle,
  User,
  FileSearch,
  Layers,
  Code,
  TestTube,
  GitPullRequest,
} from 'lucide-react'
import type { AgentName } from '../types'

interface ProgressTrackerProps {
  currentAgent: AgentName
  requirements: string[]
  architecture: Record<string, unknown>
  codeFiles: { path: string }[]
  issuesFound: string[]
  prUrl?: string
  error?: string
}

interface Stage {
  id: string
  name: string
  agent: AgentName
  icon: React.ReactNode
}

const STAGES: Stage[] = [
  { id: 'pm', name: 'Декомпозиция', agent: 'pm', icon: <User className="w-4 h-4" /> },
  { id: 'analyst', name: 'Требования', agent: 'analyst', icon: <FileSearch className="w-4 h-4" /> },
  { id: 'architect', name: 'Архитектура', agent: 'architect', icon: <Layers className="w-4 h-4" /> },
  { id: 'developer', name: 'Разработка', agent: 'developer', icon: <Code className="w-4 h-4" /> },
  { id: 'qa', name: 'Тестирование', agent: 'qa', icon: <TestTube className="w-4 h-4" /> },
  { id: 'complete', name: 'Готово', agent: 'complete', icon: <GitPullRequest className="w-4 h-4" /> },
]

export function ProgressTracker({
  currentAgent,
  requirements,
  architecture,
  codeFiles,
  issuesFound,
  prUrl,
  error,
}: ProgressTrackerProps) {
  const getStageStatus = (stage: Stage): 'complete' | 'active' | 'pending' | 'error' => {
    const currentIndex = STAGES.findIndex(s => s.agent === currentAgent)
    const stageIndex = STAGES.findIndex(s => s.id === stage.id)

    // Handle graph-level error — mark active stage as error
    if (error) {
      if (stageIndex < currentIndex) return 'complete'
      if (stageIndex === currentIndex) return 'error'
      return 'pending'
    }

    // Handle waiting for user
    if (currentAgent === 'waiting_for_user') {
      // Find the previous agent that was active
      if (stageIndex < currentIndex) return 'complete'
      if (stageIndex === currentIndex) return 'active'
      return 'pending'
    }

    if (stage.agent === 'complete' && prUrl) return 'complete'
    if (stage.id === 'qa' && issuesFound.length > 0) return 'error'

    if (stageIndex < currentIndex) return 'complete'
    if (stageIndex === currentIndex) return 'active'
    return 'pending'
  }

  return (
    <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
      <h3 className="text-sm font-mono text-midnight-300 mb-4 uppercase tracking-wider">
        Прогресс выполнения
      </h3>
      
      <div className="space-y-3">
        {STAGES.map((stage, index) => {
          const status = getStageStatus(stage)
          
          return (
            <div key={stage.id} className="flex items-center gap-3">
              {/* Status icon */}
              <div className={clsx(
                'w-8 h-8 rounded-lg flex items-center justify-center border transition-all',
                status === 'complete' && 'bg-accent-lime/20 border-accent-lime text-accent-lime',
                status === 'active' && 'bg-accent-cyan/20 border-accent-cyan text-accent-cyan animate-pulse',
                status === 'pending' && 'bg-midnight-800 border-midnight-700 text-midnight-500',
                status === 'error' && 'bg-red-500/20 border-red-500 text-red-500',
              )}>
                {status === 'complete' && <CheckCircle className="w-4 h-4" />}
                {status === 'active' && <Loader2 className="w-4 h-4 animate-spin" />}
                {status === 'pending' && <Circle className="w-4 h-4" />}
                {status === 'error' && <AlertCircle className="w-4 h-4" />}
              </div>
              
              {/* Stage info */}
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={clsx(
                    'font-mono text-sm',
                    status === 'complete' && 'text-accent-lime',
                    status === 'active' && 'text-accent-cyan',
                    status === 'pending' && 'text-midnight-500',
                    status === 'error' && 'text-red-500',
                  )}>
                    {stage.name}
                  </span>
                  {stage.icon}
                </div>
                
                {/* Stage details */}
                {status === 'error' && error && (
                  <p className="text-xs text-red-400/80 font-mono mt-0.5 break-all">
                    {error.length > 120 ? error.slice(0, 120) + '...' : error}
                  </p>
                )}
                {status !== 'pending' && status !== 'error' && (
                  <p className="text-xs text-midnight-500 font-mono mt-0.5">
                    {stage.id === 'analyst' && requirements.length > 0 &&
                      `${requirements.length} требований`}
                    {stage.id === 'architect' && Object.keys(architecture).length > 0 &&
                      'Архитектура определена'}
                    {stage.id === 'developer' && codeFiles.length > 0 &&
                      `${codeFiles.length} файлов`}
                    {stage.id === 'qa' && issuesFound.length > 0 &&
                      `${issuesFound.length} проблем`}
                    {stage.id === 'complete' && prUrl &&
                      'PR создан'}
                  </p>
                )}
              </div>
              
              {/* Connection line */}
              {index < STAGES.length - 1 && (
                <div className={clsx(
                  'absolute left-[18px] top-[40px] w-0.5 h-3',
                  status === 'complete' ? 'bg-accent-lime' : 'bg-midnight-700'
                )} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
