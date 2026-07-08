import type { Metadata } from 'next'
import { Inter, Instrument_Serif } from 'next/font/google'
import { SiteHeader } from '@/components/layout/site-header'
import { SiteFooter } from '@/components/layout/site-footer'
import { leaderboardMtime } from '@/lib/data/load-leaderboard'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const instrument = Instrument_Serif({
  subsets: ['latin'],
  weight: '400',
  style: ['normal', 'italic'],
  variable: '--font-instrument',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Deep Research Arena · Reproducible Elo benchmark for DR agents',
  description:
    'Open-source deep-research harnesses compared across backbone LLMs on frozen sandbox tasks. Arena score = reach^1.5 × jury win rate, with decidable truth and 95% bootstrap CIs.',
  metadataBase: new URL('https://www.deepresearcharena.com'),
  openGraph: {
    title: 'Deep Research Arena',
    description: 'The reproducible Elo benchmark for Deep Research agents.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  let lastUpdated: string | undefined
  try {
    lastUpdated = leaderboardMtime()
  } catch {
    lastUpdated = undefined
  }
  return (
    <html lang="en" className={`${inter.variable} ${instrument.variable} i18n-en`}>
      <head>
        {/* Apply the saved language before first paint (no flash). */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var l=localStorage.getItem('dra-lang');var h=document.documentElement;if(l==='zh'){h.classList.remove('i18n-en');h.classList.add('i18n-zh');h.setAttribute('lang','zh-CN');}}catch(e){}})();",
          }}
        />
      </head>
      <body className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter lastUpdated={lastUpdated} />
      </body>
    </html>
  )
}
