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

/** A single pipeline stage definition. */
export interface Stage {
  id: string
  name: string
  agent: AgentName
  icon: React.ReactNode
  /** Optional detail text shown when the stage is complete or active. */
  detail?: string
}

/** Default stages for the dev_team graph. */
export const DEV_TEAM_STAGES: Stage[] = [
  { id: 'pm', name: 'Декомпозиция', agent: 'pm', icon: <User className="w-4 h-4" /> },
  { id: 'analyst', name: 'Требования', agent: 'analyst', icon: <FileSearch className="w-4 h-4" /> },
  { id: 'architect', name: 'Архитектура', agent: 'architect', icon: <Layers className="w-4 h-4" /> },
  { id: 'developer', name: 'Разработка', agent: 'developer', icon: <Code className="w-4 h-4" /> },
  { id: 'qa', name: 'Тестирование', agent: 'qa', icon: <TestTube className="w-4 h-4" /> },
  { id: 'complete', name: 'Готово', agent: 'complete', icon: <GitPullRequest className="w-4 h-4" /> },
]

interface ProgressTrackerProps {
  currentAgent: AgentName
  /** Pipeline stages to display. Defaults to DEV_TEAM_STAGES. */
  stages?: Stage[]
  /** Map of stageId → detail text (e.g. "3 требований", "PR создан"). */
  stageDetails?: Record<string, string>
  error?: string
}

type StageStatus = 'complete' | 'active' | 'pending' | 'error'

function getStageStatus(
  stageIndex: number,
  currentIndex: number,
  currentAgent: string,
  error?: string,
): StageStatus {
  if (error) {
    if (stageIndex < currentIndex) return 'complete'
    if (stageIndex === currentIndex) return 'error'
    return 'pending'
  }

  if (currentAgent === 'waiting_for_user') {
    if (stageIndex < currentIndex) return 'complete'
    if (stageIndex === currentIndex) return 'active'
    return 'pending'
  }

  if (stageIndex < currentIndex) return 'complete'
  if (stageIndex === currentIndex) return 'active'
  return 'pending'
}

const statusIcon: Record<StageStatus, React.ReactNode> = {
  complete: <CheckCircle className="w-4 h-4" />,
  active: <Loader2 className="w-4 h-4 animate-spin" />,
  pending: <Circle className="w-4 h-4" />,
  error: <AlertCircle className="w-4 h-4" />,
}

const statusBoxCls: Record<StageStatus, string> = {
  complete: 'bg-accent-lime/20 border-accent-lime text-accent-lime',
  active: 'bg-accent-cyan/20 border-accent-cyan text-accent-cyan animate-pulse',
  pending: 'bg-midnight-800 border-midnight-700 text-midnight-500',
  error: 'bg-red-500/20 border-red-500 text-red-500',
}

const statusTextCls: Record<StageStatus, string> = {
  complete: 'text-accent-lime',
  active: 'text-accent-cyan',
  pending: 'text-midnight-500',
  error: 'text-red-500',
}

export function ProgressTracker({
  currentAgent,
  stages = DEV_TEAM_STAGES,
  stageDetails,
  error,
}: ProgressTrackerProps) {
  const currentIndex = stages.findIndex(s => s.agent === currentAgent)

  return (
    <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
      <h3 className="text-sm font-mono text-midnight-300 mb-4 uppercase tracking-wider">
        Прогресс выполнения
      </h3>
      
      <div className="space-y-3">
        {stages.map((stage, index) => {
          const status = getStageStatus(index, currentIndex, currentAgent, error)
          const detail = stage.detail || stageDetails?.[stage.id]
          
          return (
            <div key={stage.id} className="flex items-center gap-3">
              {/* Status icon */}
              <div className={clsx(
                'w-8 h-8 rounded-lg flex items-center justify-center border transition-all',
                statusBoxCls[status],
              )}>
                {statusIcon[status]}
              </div>
              
              {/* Stage info */}
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={clsx('font-mono text-sm', statusTextCls[status])}>
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
                {detail && status !== 'pending' && status !== 'error' && (
                  <p className="text-xs text-midnight-500 font-mono mt-0.5">
                    {detail}
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
