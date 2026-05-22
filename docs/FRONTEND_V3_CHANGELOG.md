# Frontend v3 surfacing changelog

Workstream E (frontend) for the Deep Research Arena v3 dry-run. The goal of
this change is to stop relying on the synthetic placeholder sparkline that
shipped with the v2 leaderboard and instead surface the real per-pillar Elo
and per-agent profile scores produced by Workstream A.

## What changed

### Schema and loader

- `frontend/lib/data/types.ts`
  - Added `PerPillarElo` (8 dimensions: `coverage`, `depth`, `rigor`, `style`,
    `checklist`, `spec`, `reachability`, `quote_match`).
  - Extended `RankedAgent` with the v3 fields from `per_agent_profile` plus
    `per_pillar`, `schema_version`, `is_dry_run`, `synthetic_placeholder`,
    and the derived `sig_vs_next` flag.
  - Extended `Leaderboard` with `schema_version`, `is_dry_run`, `weights_v3`,
    `composite_formula`, `rank_significance`, and `human_alignment`.

- `frontend/lib/data/load-leaderboard.ts`
  - Tries `data/results/deep_v3/leaderboard_deep_v3.json` first; falls back
    to the existing v2 `leaderboard_deep.json`; falls back again to a tiny
    synthetic seed so local dev does not crash.
  - Hydrates `per_pillar` from `pillar_elo` and the raw quality fields from
    `per_agent_profile`.
  - Derives `sig_vs_next` from `rank_significance_v3.adjacent_pairs`.
  - Exposes `isDryRun()` and `schemaVersion()` helpers and propagates the
    dry-run flag through `loadLeaderboard()`.

### Components

- `frontend/components/home/leaderboard-table.tsx`
  - Replaced the synthetic 7-bar sparkline with a real 8-bar sparkline driven
    by `agent.per_pillar`, ordered `[depth, rigor, style, coverage, checklist,
    spec, reachability, quote_match]`.
  - Heights are scaled per-dimension against the global min/max so a tall bar
    means "best on that pillar" rather than "largest Elo across pillars".
  - Hover title shows `{pillar}: {elo}`.
  - When `per_pillar` is missing, renders a faint em-dash placeholder.
  - Adds a `*` significance marker next to the agent name when the gap to the
    next-lower-ranked agent is significant (`p < 0.05`).

- `frontend/components/home/highlight-tiles.tsx`
  - Added the **Deepest reports** tile, surfacing the agent with the highest
    `depth_avg` from `per_agent_profile`. Falls back to a "data not available"
    message when no agent has `depth_avg`.
  - Bumped the grid to `xl:grid-cols-5` so all tiles fit on wide screens.

- `frontend/components/agents/quality-profile.tsx` (new)
  - Six-row Quality Profile card (Depth, Rigor, Style, Coverage, Checklist,
    URL Veracity) using a 10-segment bar with the agent's brand color and a
    two-decimal numeric value. Renders a `SYNTHETIC` pill when the underlying
    `per_agent_profile.synthetic_placeholder` is true.
  - Rendered on `frontend/app/agents/[id]/page.tsx` directly below the Elo
    metric cards.

- `frontend/components/home/dry-run-banner.tsx` (new)
  - Non-dismissible banner shown at the top of the homepage when the loaded
    leaderboard carries `_dry_run: true`. Includes the schema-version tag
    (e.g. `v3-dryrun-2026-05-21`).
  - Rendered from `frontend/app/page.tsx`.

## What new fields each component consumes

| File | New v3 fields consumed |
| --- | --- |
| `leaderboard-table.tsx` | `per_pillar`, `sig_vs_next` |
| `highlight-tiles.tsx` | `depth_avg` |
| `quality-profile.tsx` | `depth_avg`, `rigor_avg`, `style_avg`, `coverage_pct`, `checklist_pass_rate`, `url_veracity_pct`, `synthetic_placeholder` |
| `dry-run-banner.tsx` | `loadLeaderboard().is_dry_run`, `loadLeaderboard().schema_version` |
| `agents/[id]/page.tsx` | (passes the above through to `QualityProfile`) |

## How to test locally

From the worktree root:

```bash
cd frontend
npm ci          # or: npm install (falls back if package-lock is stale)
npm run typecheck
npm run build
```

The build emits `frontend/out/`. Smoke-test the static export:

```bash
python3 -m http.server 8765 -d frontend/out &
curl -I http://127.0.0.1:8765/
curl -s http://127.0.0.1:8765/ | grep -i "dry-run\|synthetic" | head -2
kill %1
```

Pages worth eyeballing:

- `/` — top-of-page dry-run banner, Deepest reports tile, real per-pillar
  sparkline in the leaderboard, `*` next to significantly-ranked agents.
- `/agents/<id>/` — Quality Profile card below the Elo block.

## Deployment (parent session, not this worktree)

```bash
cd frontend && npm ci && npm run typecheck && npm run build && cd ..
rsync -a --delete --exclude 'wrangler.jsonc' frontend/out/ web/dist/
test -f web/dist/wrangler.jsonc       # MUST still exist
```

`web/dist/wrangler.jsonc` is required by Cloudflare Workers Builds and must
survive every rsync. The `--exclude 'wrangler.jsonc'` flag above is the
operative guard; if it ever goes missing, restore it from the snippet in
`claude.md` before committing.

## Graceful degradation

Every new v3 field is optional on `RankedAgent` and the loader falls through
to v2 if `leaderboard_deep_v3.json` is missing or malformed. In v2-only mode:

- The dry-run banner does not render.
- The per-pillar sparkline shows the em-dash placeholder per row.
- The Quality Profile card shows a "not available for this agent yet" line.
- The `*` significance marker is suppressed.

This means the build is safe to ship even before Workstream A finalises the
v3 file, and it will light up automatically once the file lands.

## Open items / known gaps

- Human alignment block is propagated through `loadLeaderboard()` but is not
  yet surfaced in any component; the agent detail page will gain an
  "awaiting Workstream D" badge once `human_alignment.n_human_judgements`
  goes positive.
- The "Composite" column header does not yet render the `composite_formula`
  tooltip; the value is loaded and ready to wire when the design lands.
- `weights_v3` is loaded but not yet drawn as a legend on the per-pillar
  sparkline — would be a small follow-up.
