'use client'

import { useEffect, useState } from 'react'

/**
 * Read the GLOBAL site language (set by LangToggle / the head script via the
 * `dra-lang` localStorage key + the html i18n-* class). Returns 'en' | 'zh' and
 * updates live when the header toggle changes it (same tab, via the
 * 'dra-lang-change' event) or when another tab changes it (the 'storage' event).
 *
 * Use this when content must be CONDITIONALLY rendered per language (e.g. long
 * markdown reports on /annotate) rather than dual-rendered via <T>.
 */
export function useLang(): 'en' | 'zh' {
  const [lang, setLang] = useState<'en' | 'zh'>('en')
  useEffect(() => {
    const read = () => {
      try {
        setLang((localStorage.getItem('dra-lang') as 'en' | 'zh') || 'en')
      } catch {
        setLang('en')
      }
    }
    read()
    window.addEventListener('dra-lang-change', read)
    window.addEventListener('storage', read)
    return () => {
      window.removeEventListener('dra-lang-change', read)
      window.removeEventListener('storage', read)
    }
  }, [])
  return lang
}
