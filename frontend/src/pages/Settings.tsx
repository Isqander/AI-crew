import { useState, useEffect } from 'react'
import {
  Settings as SettingsIcon,
  User,
  Server,
  Cpu,
  Network,
  CheckCircle,
  XCircle,
  Loader2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Info,
} from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { aegraClient } from '../api/aegra'
import type { GraphListItem, AgentConfig } from '../types'

interface HealthStatus {
  status: string
  aegra: string
}

interface GraphConfig {
  graph_id: string
  agents: Record<string, AgentConfig>
}

export function Settings() {
  const { user } = useAuthStore()
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [graphs, setGraphs] = useState<GraphListItem[]>([])
  const [graphConfigs, setGraphConfigs] = useState<Record<string, GraphConfig>>({})
  const [expandedGraph, setExpandedGraph] = useState<string | null>(null)
  const [loadingGraphs, setLoadingGraphs] = useState(true)

  // Fetch health status
  const checkHealth = async () => {
    setHealthLoading(true)
    try {
      const data = await aegraClient.health()
      setHealth(data as HealthStatus)
    } catch {
      setHealth({ status: 'error', aegra: 'error' })
    } finally {
      setHealthLoading(false)
    }
  }

  // Fetch available graphs
  const loadGraphs = async () => {
    setLoadingGraphs(true)
    try {
      const list = await aegraClient.getGraphList()
      setGraphs(list)

      // Load config for each graph
      const configs: Record<string, GraphConfig> = {}
      for (const g of list) {
        try {
          const config = await aegraClient.getGraphConfig(g.graph_id)
          configs[g.graph_id] = config as GraphConfig
        } catch {
          // skip
        }
      }
      setGraphConfigs(configs)
    } catch {
      // skip
    } finally {
      setLoadingGraphs(false)
    }
  }

  useEffect(() => {
    checkHealth()
    loadGraphs()
  }, [])

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <SettingsIcon className="w-6 h-6 text-accent-cyan" />
        <h1 className="text-2xl font-mono font-semibold text-midnight-100">
          Настройки
        </h1>
      </div>

      <div className="space-y-6">
        {/* ── Profile ── */}
        <SettingsSection
          icon={<User className="w-5 h-5" />}
          title="Профиль"
          description="Информация о вашем аккаунте"
        >
          <div className="grid sm:grid-cols-2 gap-4">
            <InfoField label="Имя" value={user?.display_name || '—'} />
            <InfoField label="Email" value={user?.email || '—'} />
            <InfoField label="ID" value={user?.id?.slice(0, 8) + '...' || '—'} mono />
            <InfoField
              label="Создан"
              value={user?.created_at ? new Date(user.created_at).toLocaleString('ru-RU') : '—'}
            />
          </div>
        </SettingsSection>

        {/* ── System Status ── */}
        <SettingsSection
          icon={<Server className="w-5 h-5" />}
          title="Статус системы"
          description="Состояние сервисов платформы"
          action={
            <button
              onClick={checkHealth}
              disabled={healthLoading}
              className="flex items-center gap-2 px-3 py-1.5 bg-midnight-800 border border-midnight-700
                         rounded-lg text-midnight-300 hover:text-accent-cyan hover:border-accent-cyan/30
                         transition-colors font-mono text-xs disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${healthLoading ? 'animate-spin' : ''}`} />
              Обновить
            </button>
          }
        >
          <div className="grid sm:grid-cols-3 gap-4">
            <StatusCard
              name="Gateway"
              status={health?.status === 'ok' ? 'ok' : health ? 'error' : 'loading'}
            />
            <StatusCard
              name="Aegra (LangGraph)"
              status={health?.aegra === 'ok' ? 'ok' : health ? 'error' : 'loading'}
            />
            <StatusCard
              name="API"
              status={health ? 'ok' : 'loading'}
              detail={aegraClient.getBaseUrl()}
            />
          </div>
        </SettingsSection>

        {/* ── Graphs & LLM Config ── */}
        <SettingsSection
          icon={<Cpu className="w-5 h-5" />}
          title="Графы и модели"
          description="Доступные графы и конфигурация LLM моделей"
        >
          {loadingGraphs ? (
            <div className="flex items-center gap-2 text-midnight-400 py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="font-mono text-sm">Загрузка...</span>
            </div>
          ) : graphs.length === 0 ? (
            <p className="text-midnight-500 font-mono text-sm py-4">Графы не найдены</p>
          ) : (
            <div className="space-y-3">
              {graphs.map((g) => {
                const isExpanded = expandedGraph === g.graph_id
                const config = graphConfigs[g.graph_id]

                return (
                  <div
                    key={g.graph_id}
                    className="bg-midnight-800/50 border border-midnight-700 rounded-lg overflow-hidden"
                  >
                    <button
                      onClick={() => setExpandedGraph(isExpanded ? null : g.graph_id)}
                      className="w-full flex items-center justify-between p-4 text-left
                                 hover:bg-midnight-800/80 transition-colors"
                    >
                      <div>
                        <div className="flex items-center gap-3">
                          <Network className="w-4 h-4 text-accent-cyan" />
                          <span className="font-mono text-midnight-200 font-semibold text-sm">
                            {g.display_name}
                          </span>
                          <span className="px-2 py-0.5 bg-accent-cyan/10 text-accent-cyan text-xs font-mono rounded-full">
                            v{g.version}
                          </span>
                        </div>
                        <p className="text-midnight-400 text-xs font-mono mt-1 ml-7">
                          {g.description}
                        </p>
                      </div>
                      {isExpanded
                        ? <ChevronUp className="w-4 h-4 text-midnight-500" />
                        : <ChevronDown className="w-4 h-4 text-midnight-500" />
                      }
                    </button>

                    {isExpanded && (
                      <div className="border-t border-midnight-700 p-4 space-y-4">
                        {/* Agents */}
                        <div>
                          <h4 className="text-xs font-mono text-midnight-400 uppercase tracking-wider mb-2">
                            Агенты
                          </h4>
                          <div className="space-y-2">
                            {g.agents.map((a) => {
                              const agentConfig = config?.agents?.[a.id]
                              return (
                                <div key={a.id} className="flex items-center justify-between bg-midnight-900/50 rounded-lg px-3 py-2">
                                  <div className="flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-accent-cyan" />
                                    <span className="font-mono text-midnight-200 text-sm">
                                      {a.display_name}
                                    </span>
                                  </div>
                                  {agentConfig && (
                                    <div className="flex items-center gap-3 text-xs font-mono">
                                      <span className="px-2 py-0.5 bg-accent-cyan/10 text-accent-cyan rounded">
                                        {agentConfig.model}
                                      </span>
                                      <span className="text-midnight-500">
                                        t={agentConfig.temperature}
                                      </span>
                                      {agentConfig.fallback_model && (
                                        <span className="text-amber-400/70">
                                          fallback: {agentConfig.fallback_model}
                                        </span>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        </div>

                        {/* Task types */}
                        <div>
                          <h4 className="text-xs font-mono text-midnight-400 uppercase tracking-wider mb-2">
                            Типы задач
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {g.task_types.map((t) => (
                              <span key={t} className="px-2 py-1 bg-midnight-800 text-midnight-300 text-xs font-mono rounded">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>

                        {/* Features */}
                        {g.features.length > 0 && (
                          <div>
                            <h4 className="text-xs font-mono text-midnight-400 uppercase tracking-wider mb-2">
                              Возможности
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {g.features.map((f) => (
                                <span key={f} className="px-2 py-1 bg-accent-lime/10 text-accent-lime text-xs font-mono rounded">
                                  {f}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </SettingsSection>

        {/* ── About ── */}
        <SettingsSection
          icon={<Info className="w-5 h-5" />}
          title="О системе"
          description="Информация о платформе AI-crew"
        >
          <div className="grid sm:grid-cols-2 gap-4">
            <InfoField label="Платформа" value="AI-crew" />
            <InfoField label="Версия" value="1.0.0 (Wave 2)" />
            <InfoField label="Runtime" value="LangGraph + Aegra" />
            <InfoField label="Gateway" value="FastAPI" />
          </div>
          <div className="mt-4 p-3 bg-midnight-800/50 border border-midnight-700/50 rounded-lg">
            <p className="text-midnight-400 text-xs font-mono leading-relaxed">
              <strong className="text-midnight-300">Примечание:</strong> Конфигурация LLM-моделей задаётся 
              в <code className="text-accent-cyan">config/agents.yaml</code> и переменных окружения. 
              Изменение моделей требует перезапуска контейнеров. 
              Перезапуск с сайта пока не поддерживается — используйте{' '}
              <code className="text-accent-cyan">docker-compose restart</code>.
            </p>
          </div>
        </SettingsSection>
      </div>
    </div>
  )
}

// ────────────────── Shared Components ──────────────────

interface SettingsSectionProps {
  icon: React.ReactNode
  title: string
  description: string
  children: React.ReactNode
  action?: React.ReactNode
}

function SettingsSection({ icon, title, description, children, action }: SettingsSectionProps) {
  return (
    <div className="bg-midnight-900/50 rounded-xl border border-midnight-800 p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="text-accent-cyan">{icon}</div>
          <div>
            <h2 className="font-mono font-semibold text-midnight-200">{title}</h2>
            <p className="text-midnight-500 text-xs font-mono">{description}</p>
          </div>
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

interface InfoFieldProps {
  label: string
  value: string
  mono?: boolean
}

function InfoField({ label, value, mono }: InfoFieldProps) {
  return (
    <div className="bg-midnight-800/50 border border-midnight-700/50 rounded-lg px-4 py-3">
      <div className="text-midnight-500 text-xs font-mono mb-1">{label}</div>
      <div className={`text-midnight-200 text-sm ${mono ? 'font-mono' : ''}`}>{value}</div>
    </div>
  )
}

interface StatusCardProps {
  name: string
  status: 'ok' | 'error' | 'loading'
  detail?: string
}

function StatusCard({ name, status, detail }: StatusCardProps) {
  return (
    <div className="bg-midnight-800/50 border border-midnight-700/50 rounded-lg px-4 py-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-midnight-300 text-sm font-mono">{name}</span>
        {status === 'loading' ? (
          <Loader2 className="w-4 h-4 text-midnight-500 animate-spin" />
        ) : status === 'ok' ? (
          <CheckCircle className="w-4 h-4 text-accent-lime" />
        ) : (
          <XCircle className="w-4 h-4 text-red-400" />
        )}
      </div>
      {detail && (
        <div className="text-midnight-500 text-xs font-mono truncate">{detail}</div>
      )}
    </div>
  )
}
