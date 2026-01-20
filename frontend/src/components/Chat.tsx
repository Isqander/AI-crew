import { useState, useRef, useEffect } from 'react'
import { Send, User, Bot, AlertCircle, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import type { Message, AgentName, AGENTS } from '../types'

interface ChatProps {
  messages: Message[]
  currentAgent?: AgentName
  needsClarification?: boolean
  clarificationQuestion?: string
  onSendMessage?: (message: string) => void
  isLoading?: boolean
}

export function Chat({
  messages,
  currentAgent,
  needsClarification = false,
  clarificationQuestion,
  onSendMessage,
  isLoading = false,
}: ChatProps) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || !onSendMessage || isLoading) return
    
    onSendMessage(input.trim())
    setInput('')
  }

  return (
    <div className="flex flex-col h-full bg-midnight-900 rounded-lg border border-midnight-800">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-midnight-500">
            <Bot className="w-12 h-12 mb-4 opacity-50" />
            <p className="font-mono text-sm">Здесь будут сообщения агентов</p>
          </div>
        ) : (
          messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))
        )}
        
        {/* Clarification prompt */}
        {needsClarification && clarificationQuestion && (
          <ClarificationPrompt question={clarificationQuestion} />
        )}
        
        {/* Loading indicator */}
        {isLoading && !needsClarification && (
          <div className="flex items-center gap-2 text-accent-cyan">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="font-mono text-sm">
              {currentAgent ? `${currentAgent} думает...` : 'Обработка...'}
            </span>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form 
        onSubmit={handleSubmit}
        className="border-t border-midnight-800 p-4"
      >
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={needsClarification ? "Введите ответ..." : "Отправить сообщение..."}
            className="flex-1 bg-midnight-800 border border-midnight-700 rounded-lg px-4 py-2
                       text-midnight-100 placeholder-midnight-500 font-mono text-sm
                       focus:outline-none focus:border-accent-cyan"
            disabled={isLoading && !needsClarification}
          />
          <button
            type="submit"
            disabled={!input.trim() || (isLoading && !needsClarification)}
            className="bg-accent-cyan text-midnight-950 p-2 rounded-lg
                       hover:opacity-90 transition-opacity
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </form>
    </div>
  )
}

interface ChatMessageProps {
  message: Message
}

function ChatMessage({ message }: ChatMessageProps) {
  const isHuman = message.type === 'human'
  const isSystem = message.type === 'system'
  
  return (
    <div className={clsx(
      'flex gap-3',
      isHuman && 'flex-row-reverse'
    )}>
      {/* Avatar */}
      <div className={clsx(
        'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
        isHuman ? 'bg-accent-magenta/20' : 'bg-accent-cyan/20',
        isSystem && 'bg-midnight-700'
      )}>
        {isHuman ? (
          <User className="w-4 h-4 text-accent-magenta" />
        ) : (
          <Bot className="w-4 h-4 text-accent-cyan" />
        )}
      </div>
      
      {/* Content */}
      <div className={clsx(
        'max-w-[80%] rounded-lg px-4 py-3',
        isHuman ? 'bg-accent-magenta/10 border border-accent-magenta/30' : 'bg-midnight-800',
        isSystem && 'bg-midnight-700/50 border border-midnight-600'
      )}>
        {/* Agent name */}
        {message.name && !isHuman && (
          <p className="text-xs text-accent-cyan font-mono mb-1 uppercase">
            {message.name}
          </p>
        )}
        
        {/* Message content */}
        <div className="text-midnight-100 font-mono text-sm whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    </div>
  )
}

interface ClarificationPromptProps {
  question: string
}

function ClarificationPrompt({ question }: ClarificationPromptProps) {
  return (
    <div className="bg-accent-amber/10 border border-accent-amber/30 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-accent-amber flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-accent-amber font-mono text-sm font-medium mb-2">
            Требуется ваш ввод
          </p>
          <p className="text-midnight-200 font-mono text-sm whitespace-pre-wrap">
            {question}
          </p>
        </div>
      </div>
    </div>
  )
}
