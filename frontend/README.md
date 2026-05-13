# Deep Research Arena · frontend

Next.js 14 (App Router) + TypeScript + Tailwind 3 + Framer Motion + Recharts.

## Quick start

```bash
cd frontend
npm install        # or pnpm install
npm run dev        # http://localhost:3000
```

## Structure

```
frontend/
├─ app/                       # Next.js App Router pages
│   ├─ page.tsx               # / — Leaderboard home
│   ├─ agents/                # /agents — hub + dynamic detail (TBD)
│   ├─ tasks/                 # /tasks — explorer (stub)
│   ├─ pillars/               # /pillars — 7-pillar hub (stub)
│   ├─ arena/                 # /arena — Live 1v1 (stub)
│   ├─ insights/              # /insights — F6 stories (stub)
│   ├─ methodology/           # /methodology — long-form (stub)
│   ├─ sandbox/               # /sandbox — architecture tour (stub)
│   ├─ about/  contribute/    # static pages (stub)
│   ├─ api/leaderboard/       # static JSON endpoint
│   └─ layout.tsx · globals.css
├─ components/
│   ├─ layout/                # site-header, site-footer, page-stub
│   ├─ home/                  # hero, highlight-tiles, composite-bar, …
│   ├─ agents/                # agent-card
│   └─ ui/                    # button, card, chip
├─ lib/
│   ├─ data/                  # leaderboard loader (build-time fs read)
│   ├─ providers.ts           # agent ↔ provider ↔ brand-color dictionary
│   ├─ format.ts · cn.ts
└─ tailwind.config.ts · postcss.config.js · tsconfig.json
```

## Data flow

- `lib/data/load-leaderboard.ts` reads `../data/results/deep_v3/leaderboard_deep.json`
  (project root) at build time. Falls back to a synthetic dataset if absent.
- `app/api/leaderboard/route.ts` re-emits that data as a static JSON endpoint
  for client-side pages (Agents Hub, Arena, etc.) to fetch.
- `lib/providers.ts` is the single source of truth for agent display name,
  backbone, family, and brand color. Edit when you add a framework.

## Design system

See `tailwind.config.ts` for tokens. Highlights:

- Brand purple `#7F4BF3`, soft footer `#C8A8FF`
- `Inter` (body) + `Instrument Serif` (display) via `next/font/google`
- Rounded card `14px`, button `8px`, pill `9999px`
- Soft hover lift via `card-lift` utility class

## Build & deploy

```bash
npm run build
npm run start              # SSR locally
# or fully static:
# tweak next.config.js → output: 'export'  for /out folder
```

## Roadmap

See `../FRONTEND_SITEMAP.md` for the full content map (15 top-level pages,
128 dynamic sub-pages, 11 creative additions).
