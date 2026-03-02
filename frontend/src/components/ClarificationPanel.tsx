import { useState } from 'react'
import { AlertCircle, Send, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface ClarificationPanelProps {
  question: string
  context?: string
  onSubmit: (response: string) => void
  isLoading?: boolean
}

export function ClarificationPanel({
  question,
  context,
  onSubmit,
  isLoading = false,
}: ClarificationPanelProps) {
  const [response, setResponse] = useState('')
  const { t } = useTranslation()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!response.trim() || isLoading) return
    onSubmit(response.trim())
    setResponse('')
  }

  return (
    <div className="bg-accent-amber/5 border border-accent-amber/30 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="bg-accent-amber/10 px-4 py-3 flex items-center gap-3">
        <AlertCircle className="w-5 h-5 text-accent-amber" />
        <h3 className="font-mono font-medium text-accent-amber">
          {t('clarification.title')}
        </h3>
      </div>
      
      {/* Content */}
      <div className="p-4 space-y-4">
        {context && (
          <div className="text-xs text-midnight-500 font-mono uppercase tracking-wider">
            {context}
          </div>
        )}
        
        <div className="bg-midnight-900 rounded-lg p-4">
          <p className="text-midnight-100 font-mono text-sm whitespace-pre-wrap">
            {question}
          </p>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-3">
          <textarea
            value={response}
            onChange={(e) => setResponse(e.target.value)}
            placeholder={t('clarification.placeholder')}
            className="w-full bg-midnight-900 border border-midnight-700 rounded-lg px-4 py-3
                       text-midnight-100 placeholder-midnight-500 font-mono text-sm
                       focus:outline-none focus:border-accent-amber focus:ring-1 focus:ring-accent-amber
                       resize-none min-h-[100px]"
            disabled={isLoading}
          />
          
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!response.trim() || isLoading}
              className="bg-accent-amber text-midnight-950 px-4 py-2 rounded-lg font-mono font-medium
                         flex items-center gap-2 hover:opacity-90 transition-opacity
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              {isLoading ? t('clarification.sending') : t('clarification.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
