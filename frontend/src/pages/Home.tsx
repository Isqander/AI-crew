import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Zap, GitBranch, MessageSquare, ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { TaskForm } from '../components/TaskForm'
import { ErrorBanner } from '../components/ErrorBanner'
import { useTask, useThreads } from '../hooks/useTask'
import type { CreateTaskInput, GraphListItem } from '../types'

export function Home() {
  const navigate = useNavigate()
  const { createTask, isCreating, error, thread } = useTask()
  const { data: threads } = useThreads()
  const { t, i18n } = useTranslation()
  const [selectedGraph, setSelectedGraph] = useState<GraphListItem | null>(null)

  const handleSubmit = async (input: CreateTaskInput) => {
    await createTask(input)
  }

  // Redirect to task detail when thread is created
  if (thread) {
    navigate(`/task/${thread.thread_id}`)
  }

  const dateLocale = i18n.language === 'ru' ? 'ru-RU' : 'en-US'
  const selectedAgentsCount = selectedGraph?.agents.length

  const agentsFeatureTitle =
    selectedAgentsCount !== undefined
      ? t('home.featureAgentsWithCount', { count: selectedAgentsCount })
      : t('home.featureAgents')

  const agentsFeatureDescription = selectedGraph
    ? t('home.featureAgentsDescSelected', { graph: selectedGraph.display_name })
    : t('home.featureAgentsDesc')

  return (
    <div className="max-w-4xl mx-auto space-y-12">
      {/* Hero section */}
      <section className="text-center py-8">
        <div className="inline-flex items-center gap-2 bg-accent-cyan/10 text-accent-cyan px-4 py-2 rounded-full mb-6 font-mono text-sm">
          <Zap className="w-4 h-4" />
          Powered by LangGraph + Aegra
        </div>
        
        <h1 className="text-4xl md:text-5xl font-bold mb-4">
          <span className="text-glow-cyan text-accent-cyan">AI-crew</span>
          <br />
          <span className="text-midnight-200">{t('home.hero')}</span>
        </h1>
        
        <p className="text-midnight-400 max-w-2xl mx-auto text-lg">
          {t('home.description')}
        </p>
      </section>

      {/* Task form */}
      <section className="bg-midnight-900/50 rounded-2xl border border-midnight-800 p-6">
        <h2 className="text-xl font-mono font-semibold text-accent-cyan mb-4 flex items-center gap-2">
          <Bot className="w-5 h-5" />
          {t('home.newTask')}
        </h2>
        <TaskForm
          onSubmit={handleSubmit}
          isLoading={isCreating}
          onSelectedGraphChange={setSelectedGraph}
        />
        {error && (
          <ErrorBanner
            title={t('home.createError')}
            message={error.message}
            className="mt-4"
          />
        )}
      </section>

      {/* Features grid */}
      <section className="grid md:grid-cols-3 gap-6">
        <FeatureCard
          icon={<Bot className="w-6 h-6" />}
          title={agentsFeatureTitle}
          description={agentsFeatureDescription}
          color="cyan"
        />
        <FeatureCard
          icon={<MessageSquare className="w-6 h-6" />}
          title={t('home.featureHitl')}
          description={t('home.featureHitlDesc')}
          color="magenta"
        />
        <FeatureCard
          icon={<GitBranch className="w-6 h-6" />}
          title={t('home.featureGithub')}
          description={t('home.featureGithubDesc')}
          color="lime"
        />
      </section>

      {/* Recent tasks */}
      {threads && threads.length > 0 && (
        <section>
          <h2 className="text-lg font-mono font-semibold text-midnight-200 mb-4">
            {t('home.recentTasks')}
          </h2>
          <div className="space-y-2">
            {threads.slice(0, 5).map((t_) => (
              <button
                key={t_.thread_id}
                onClick={() => navigate(`/task/${t_.thread_id}`)}
                className="w-full bg-midnight-900 border border-midnight-800 rounded-lg p-4
                           hover:border-accent-cyan/50 transition-colors text-left
                           flex items-center justify-between group"
              >
                <div>
                  <p className="font-mono text-midnight-200 text-sm">
                    {t_.metadata?.task || t('common.untitled')}
                  </p>
                  <p className="text-xs text-midnight-500 font-mono mt-1">
                    {new Date(t_.created_at).toLocaleString(dateLocale)}
                  </p>
                </div>
                <ArrowRight className="w-4 h-4 text-midnight-500 group-hover:text-accent-cyan transition-colors" />
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

interface FeatureCardProps {
  icon: React.ReactNode
  title: string
  description: string
  color: 'cyan' | 'magenta' | 'lime'
}

function FeatureCard({ icon, title, description, color }: FeatureCardProps) {
  const colorClasses = {
    cyan: 'text-accent-cyan bg-accent-cyan/10 border-accent-cyan/30',
    magenta: 'text-accent-magenta bg-accent-magenta/10 border-accent-magenta/30',
    lime: 'text-accent-lime bg-accent-lime/10 border-accent-lime/30',
  }

  return (
    <div className="bg-midnight-900/50 rounded-xl border border-midnight-800 p-6 hover:border-midnight-700 transition-colors">
      <div className={`w-12 h-12 rounded-lg flex items-center justify-center mb-4 border ${colorClasses[color]}`}>
        {icon}
      </div>
      <h3 className="font-mono font-semibold text-midnight-100 mb-2">{title}</h3>
      <p className="text-midnight-400 text-sm">{description}</p>
    </div>
  )
}
