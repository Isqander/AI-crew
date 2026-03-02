import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'

const LANGUAGES = [
  { code: 'en', label: 'English', flag: 'EN' },
  { code: 'ru', label: 'Русский', flag: 'RU' },
] as const

export function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const current = LANGUAGES.find(l => l.code === i18n.language) ?? LANGUAGES[0]

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const switchLanguage = (code: string) => {
    i18n.changeLanguage(code)
    document.documentElement.lang = code
    setOpen(false)
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-midnight-400 hover:text-accent-cyan transition-colors font-mono text-sm px-2 py-1 rounded-lg hover:bg-midnight-800/50"
        aria-label="Change language"
      >
        <Globe className="w-4 h-4" />
        <span className="text-xs font-semibold">{current.flag}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 bg-midnight-900 border border-midnight-700 rounded-lg shadow-xl shadow-midnight-950/50 overflow-hidden z-50 min-w-[140px]">
          {LANGUAGES.map(lang => (
            <button
              key={lang.code}
              onClick={() => switchLanguage(lang.code)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm font-mono transition-colors text-left
                ${lang.code === i18n.language
                  ? 'bg-accent-cyan/10 text-accent-cyan'
                  : 'text-midnight-300 hover:bg-midnight-800 hover:text-midnight-100'
                }`}
            >
              <span className="text-xs font-semibold w-6">{lang.flag}</span>
              {lang.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
