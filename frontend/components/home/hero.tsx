'use client'

import { motion } from 'motion/react'
import { ArrowRight, BookOpen, Github, Swords } from 'lucide-react'
import Link from 'next/link'

interface Stat {
  value: string
  label: string
}

interface Props {
  stats: Stat[]
}

export function Hero({ stats }: Props) {
  return (
    <section className="relative overflow-hidden">
      {/* Soft dotted backdrop */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 opacity-50"
        style={{
          backgroundImage: 'radial-gradient(circle at 2px 2px, rgba(127,75,243,0.18) 1px, transparent 0)',
          backgroundSize: '24px 24px',
          maskImage: 'radial-gradient(ellipse 80% 60% at 50% 30%, black, transparent)',
        }}
      />

      <div className="container py-16 md:py-24">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
          className="max-w-3xl"
        >
          <span className="label-caps">2026 · v3.1 · NeurIPS draft</span>
          <h1 className="mt-4 font-serif text-display text-balance leading-[1.05] tracking-tight">
            The reproducible Elo benchmark for{' '}
            <em className="not-italic text-brand">Deep Research</em> agents.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted md:text-lg">
            Eight open-source frameworks battle on 107 sandbox tasks. Every cited URL is verified against the
            backing database. Every score has a 95% bootstrap confidence interval. No drifting search,
            no hand-judged rubrics, no inflated numbers.
          </p>

          {/* CTAs */}
          <div className="mt-7 flex flex-wrap items-center gap-2.5">
            <Link
              href="#leaderboard"
              className="group inline-flex h-11 items-center gap-2 rounded-tab bg-ink px-5 text-sm font-medium text-white transition-all duration-150 ease-smooth hover:bg-ink-soft"
            >
              Explore leaderboard
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/arena"
              className="inline-flex h-11 items-center gap-2 rounded-tab border border-hairline bg-white px-5 text-sm font-medium text-ink transition-all duration-150 hover:border-ink/30 hover:shadow-soft"
            >
              <Swords className="h-4 w-4" />
              Try Live Arena
            </Link>
            <Link
              href="/methodology"
              className="inline-flex h-11 items-center gap-2 rounded-tab px-3 text-sm text-muted transition-colors hover:text-ink"
            >
              <BookOpen className="h-4 w-4" />
              Read methodology
            </Link>
            <a
              href="https://github.com/"
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-11 items-center gap-2 rounded-tab px-3 text-sm text-muted transition-colors hover:text-ink"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
          </div>
        </motion.div>

        {/* Stat strip */}
        <motion.dl
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: 0.2 } } }}
          className="mt-14 grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4"
        >
          {stats.map((s) => (
            <motion.div
              key={s.label}
              variants={{
                hidden: { opacity: 0, y: 12 },
                show: { opacity: 1, y: 0, transition: { type: 'spring', damping: 20, stiffness: 220 } },
              }}
              className="card p-5"
            >
              <dt className="label-caps">{s.label}</dt>
              <dd className="mt-1 font-serif text-3xl tnum text-ink md:text-4xl">{s.value}</dd>
            </motion.div>
          ))}
        </motion.dl>
      </div>
    </section>
  )
}
