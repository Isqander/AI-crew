import { AlertCircle } from 'lucide-react'

interface ErrorBannerProps {
  /** Optional title shown next to the icon */
  title?: string
  /** Error message text */
  message: string
  /** Extra badge text (e.g. agent node name) */
  badge?: string
  /** Additional CSS class for the outer div */
  className?: string
}

/**
 * Reusable error banner with consistent styling.
 *
 * Supports two modes:
 * - Simple: just `message` — renders a compact red text block
 * - Rich: `title` + `message` — renders icon, title, optional badge, and description
 */
export function ErrorBanner({ title, message, badge, className = '' }: ErrorBannerProps) {
  if (!title) {
    // Simple compact mode (used in Login, Register, etc.)
    return (
      <div className={`p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-mono ${className}`}>
        {message}
      </div>
    )
  }

  // Rich mode with icon, title, optional badge, and message body
  return (
    <div className={`bg-red-500/10 border border-red-500/30 rounded-lg p-4 ${className}`}>
      <div className="flex items-center gap-2 text-red-400 font-mono text-sm">
        <AlertCircle className="w-5 h-5 flex-shrink-0" />
        <span className="font-semibold">{title}</span>
        {badge && (
          <span className="ml-1 px-2 py-0.5 bg-red-500/20 rounded-full text-xs">
            {badge}
          </span>
        )}
      </div>
      <p className="text-red-300/80 text-sm font-mono mt-2">{message}</p>
    </div>
  )
}
