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
    'Eight open-source Deep Research frameworks, 107 sandbox tasks, 7 evaluation pillars, 95% bootstrap CIs. Reproducible. Ground-truth verified.',
  metadataBase: new URL('https://deep-research-arena.local'),
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
    <html lang="en" className={`${inter.variable} ${instrument.variable}`}>
      <body className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter lastUpdated={lastUpdated} />
      </body>
    </html>
  )
}
