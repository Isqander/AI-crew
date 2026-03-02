import { clsx } from 'clsx'
import { useTranslation } from 'react-i18next'
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

export interface Stage {
  id: string
  nameKey: string
  agent: AgentName
  icon: React.ReactNode
  detail?: string
}

function useDevTeamStages(): Stage[] {
  const { t } = useTranslation()
  return [
    { id: 'pm', nameKey: t('progress.pm'), agent: 'pm', icon: <User className="w-4 h-4" /> },
    { id: 'analyst', nameKey: t('progress.analyst'), agent: 'analyst', icon: <FileSearch className="w-4 h-4" /> },
    { id: 'architect', nameKey: t('progress.architect'), agent: 'architect', icon: <Layers className="w-4 h-4" /> },
    { id: 'developer', nameKey: t('progress.developer'), agent: 'developer', icon: <Code className="w-4 h-4" /> },
    { id: 'qa', nameKey: t('progress.qa'), agent: 'qa', icon: <TestTube className="w-4 h-4" /> },
    { id: 'complete', nameKey: t('progress.complete'), agent: 'complete', icon: <GitPullRequest className="w-4 h-4" /> },
  ]
}

interface ProgressTrackerProps {
  currentAgent: AgentName
  stages?: Stage[]
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
  stages,
  stageDetails,
  error,
}: ProgressTrackerProps) {
  const { t } = useTranslation()
  const defaultStages = useDevTeamStages()
  const effectiveStages = stages ?? defaultStages
  const currentIndex = effectiveStages.findIndex(s => s.agent === currentAgent)

  return (
    <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
      <h3 className="text-sm font-mono text-midnight-300 mb-4 uppercase tracking-wider">
        {t('progress.title')}
      </h3>
      
      <div className="space-y-3">
        {effectiveStages.map((stage, index) => {
          const status = getStageStatus(index, currentIndex, currentAgent, error)
          const detail = stage.detail || stageDetails?.[stage.id]
          
          return (
            <div key={stage.id} className="flex items-center gap-3">
              <div className={clsx(
                'w-8 h-8 rounded-lg flex items-center justify-center border transition-all',
                statusBoxCls[status],
              )}>
                {statusIcon[status]}
              </div>
              
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={clsx('font-mono text-sm', statusTextCls[status])}>
                    {stage.nameKey}
                  </span>
                  {stage.icon}
                </div>
                
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
