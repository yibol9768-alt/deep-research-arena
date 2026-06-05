'use client'

import { useEffect, useState } from 'react'

/**
 * EN / 中文 switch. Flips a class on <html> (i18n-en / i18n-zh) which the CSS in
 * globals.css uses to show/hide [data-lang] spans rendered by <T>. Persists to
 * localStorage; the head script in layout.tsx applies the saved choice before
 * first paint so there is no flash.
 */
export function LangToggle({ className = '' }: { className?: string }) {
  const [lang, setLang] = useState<'en' | 'zh'>('en')

  useEffect(() => {
    const saved = (localStorage.getItem('dra-lang') as 'en' | 'zh') || 'en'
    setLang(saved)
  }, [])

  const apply = (l: 'en' | 'zh') => {
    setLang(l)
    try {
      localStorage.setItem('dra-lang', l)
    } catch {}
    const html = document.documentElement
    html.classList.toggle('i18n-zh', l === 'zh')
    html.classList.toggle('i18n-en', l === 'en')
    html.setAttribute('lang', l === 'zh' ? 'zh-CN' : 'en')
  }

  return (
    <button
      type="button"
      onClick={() => apply(lang === 'en' ? 'zh' : 'en')}
      aria-label="Switch language"
      title={lang === 'en' ? 'Switch to 中文' : 'Switch to English'}
      className={
        'inline-flex h-8 items-center justify-center rounded-tab border border-hairline px-2.5 text-xs font-medium text-muted transition-colors hover:bg-surface-low hover:text-ink ' +
        className
      }
    >
      {lang === 'en' ? '中文' : 'EN'}
    </button>
  )
}
