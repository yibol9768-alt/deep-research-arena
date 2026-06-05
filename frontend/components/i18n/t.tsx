import React from 'react'

/**
 * Bilingual text. Renders BOTH languages; a CSS class on <html> (set by
 * LangToggle / the head script in layout) shows exactly one. Works in server
 * AND client components (no hooks), so any page can go bilingual without being
 * converted to a client component.
 *
 *   <h1><T en="Leaderboard" zh="排行榜" /></h1>
 *
 * For attribute strings (placeholder, aria-label, title) CSS toggling cannot
 * apply; leave those in English or handle separately.
 */
export function T({ en, zh }: { en: React.ReactNode; zh: React.ReactNode }) {
  return (
    <>
      <span data-lang="en">{en}</span>
      <span data-lang="zh">{zh}</span>
    </>
  )
}

/** Pick one of two strings for non-JSX contexts (rare). Defaults to English on
 *  the server; the visible language is still governed by CSS, so prefer <T>. */
export function tline(en: string, zh: string) {
  return { en, zh }
}
