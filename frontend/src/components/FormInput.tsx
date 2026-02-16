import type { ReactNode, InputHTMLAttributes } from 'react'
import { clsx } from 'clsx'

interface FormInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'className'> {
  label: string
  icon?: ReactNode
  error?: string
  /** Visual variant: "auth" for login/register pages, "form" for general forms */
  variant?: 'auth' | 'form'
}

const baseInput =
  'w-full text-midnight-100 font-mono placeholder-midnight-500 focus:outline-none transition-all'

const variants = {
  auth: `${baseInput} pl-12 pr-4 py-3 bg-midnight-800/80 border border-midnight-600 rounded-xl focus:ring-2 focus:ring-accent-cyan/50 focus:border-accent-cyan/50`,
  form: `${baseInput} px-4 py-2 bg-midnight-900 border border-midnight-700 rounded-lg text-sm focus:border-accent-cyan`,
}

const iconVariants = {
  auth: 'absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-midnight-500',
  form: 'absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-midnight-500',
}

const labelVariants = {
  auth: 'block text-sm font-mono font-medium text-midnight-300 mb-2',
  form: 'block text-sm font-mono text-midnight-300 mb-1',
}

export function FormInput({
  label,
  icon,
  error,
  variant = 'auth',
  id,
  ...inputProps
}: FormInputProps) {
  const inputId = id || label.toLowerCase().replace(/\s+/g, '-')

  return (
    <div>
      <label htmlFor={inputId} className={labelVariants[variant]}>
        {label}
      </label>
      <div className="relative">
        {icon && (
          <span className={iconVariants[variant]}>{icon}</span>
        )}
        <input
          id={inputId}
          className={clsx(
            variants[variant],
            icon && variant === 'auth' && 'pl-12',
            icon && variant === 'form' && 'pl-10',
            error && 'border-red-500 focus:ring-red-500/50 focus:border-red-500/50',
          )}
          {...inputProps}
        />
      </div>
      {error && (
        <p className="mt-1 text-xs font-mono text-red-400">{error}</p>
      )}
    </div>
  )
}
