# Deep Research Arena Maintenance Guide

This repository powers the public Deep Research Arena site:

- Public site: `https://www.deepresearcharena.com/`
- GitHub repository: `yibol9768-alt/deep-research-arena`
- SSH remote: `git@github.com:yibol9768-alt/deep-research-arena.git`
- Default branch: `main`

Important: this local directory, `/root/Desktop/lyb/deep_reserch`, is a working
copy but not currently a Git checkout. `git status` fails here because there is
no `.git` directory. To publish website changes, use a real checkout of the
GitHub repository, commit the changed source plus generated static output, and
push to `main`.

## Hosting Model

The site is updated through GitHub, but the live domain is served through
Cloudflare. Current HTTP headers for `www.deepresearcharena.com` show
`server: cloudflare`, and the latest repository history references
`web/dist` plus Cloudflare Workers Builds. There are no GitHub Actions workflows
in this repo, and GitHub's Pages API does not report a standard GitHub Pages
site.

Operationally, treat this as:

```text
edit source -> build static site -> sync to web/dist -> commit -> push GitHub -> Cloudflare deploys
```

If someone says "GitHub Pages" for this project, they usually mean the
GitHub-backed static deployment path. The practical update action is still:
push the correct files to GitHub.

## Production Website Source

Use these paths for the live website:

- `frontend/` is the current production Next.js app.
- `frontend/next.config.js` uses `output: 'export'`, so `npm run build`
  produces a static export in `frontend/out/`.
- `web/dist/` is the tracked static deployment artifact consumed by Cloudflare
  Workers Builds.
- `web/dist/wrangler.jsonc` is required. Do not let `rsync --delete` remove it.

Do not use these paths for normal production website edits:

- `web-next/` is an older Next.js/static prototype and data snapshot.
- `web/server.py` and `web/templates/` are the legacy FastAPI/Jinja site.
- `web/build_static.py` is legacy static generation for that older site.

## Common Website Edits

Homepage and leaderboard:

- `frontend/app/page.tsx`
- `frontend/components/home/*`
- `frontend/components/layout/site-header.tsx`
- `frontend/components/layout/site-footer.tsx`

Navigation and metadata:

- `frontend/app/layout.tsx`
- `frontend/components/layout/site-header.tsx`
- `frontend/components/layout/site-footer.tsx`

Agent names, models, colors, and GitHub links:

- `frontend/lib/providers.ts`

Leaderboard and task data loading:

- `frontend/lib/data/load-leaderboard.ts`
- `frontend/lib/data/tasks.ts`
- `frontend/app/api/leaderboard/route.ts`

Task pages:

- `frontend/app/tasks/page.tsx`
- `frontend/app/tasks/[id]/page.tsx`
- `data/tasks/deep_research/cross_site_deep/*.json`

Methodology, sandbox, insights, and contribution pages:

- `frontend/app/methodology/page.tsx`
- `frontend/app/sandbox/page.tsx`
- `frontend/app/insights/page.tsx`
- `frontend/app/contribute/page.tsx`

Changelog page (data-driven; renders `data/changelog.json`):

- `frontend/app/changelog/page.tsx`
- `frontend/lib/data/changelog.ts`
- `data/changelog.json` (source of truth — append new entries to the top of
  the `entries` array)

## Changelog Discipline (hard rule)

Every meaningful change to scoring, tasks, adapters, sandbox enforcement,
frontend, or methodology MUST be logged in `data/changelog.json` and
rendered on `/changelog` before deployment. Skipping this step is not
acceptable — `/changelog` is the user-facing record of every shipped change.

Entry schema (in `data/changelog.json`):

```json
{
  "version": "v<MAJOR>-<YYYY-MM-DD>",
  "date": "YYYY-MM-DD",
  "title": "Short headline",
  "summary": "1-2 sentence summary of why this update matters.",
  "tags": ["scoring", "frontend", "sandbox", ...],
  "sections": [
    { "heading": "Scoring", "bullets": ["terse bullet", "..."] },
    { "heading": "Site",    "bullets": ["...", "..."] }
  ],
  "links": [
    { "label": "Spec", "href": "/methodology" }
  ]
}
```

Workflow for any user-visible update:

1. Make the code/data change.
2. Append a new entry to the top of `entries` in `data/changelog.json`.
3. `cd frontend && npm run typecheck && npm run build` — verify zero errors.
4. `rsync -a --delete --exclude 'wrangler.jsonc' frontend/out/ web/dist/` and
   confirm `web/dist/wrangler.jsonc` still exists (restore from this file's
   "Publishing Workflow" section if rsync stripped it).
5. Commit source/data + regenerated `web/dist/` together.
6. Push `main`. Cloudflare redeploys automatically.

For multi-workstream releases (like the V3 overhaul, 2026-05-21), still
ship one consolidated changelog entry. Sub-sections inside the entry are how
you split scoring vs. site vs. sandbox concerns.

## Leaderboard Data Flow

The benchmark and scoring pipeline writes result files under `data/results/`.
The production frontend reads the v3 leaderboard at build time from:

```text
data/results/deep_v3/leaderboard_deep.json
data/results/deep_v3/kpi_stats.json
```

Related scripts:

```bash
python scripts/build_deep_leaderboard.py
python scripts/build_v4_leaderboard.py
python scripts/recompute_v4b.py
python scripts/recompute_v4c.py
```

After changing result JSON or task JSON, rebuild the static site and commit both
the source/data changes and the regenerated `web/dist/` output.

## Publishing Workflow

Use a clean checkout when publishing:

```bash
cd /root/Desktop/lyb
git clone git@github.com:yibol9768-alt/deep-research-arena.git deep-research-arena-publish
cd deep-research-arena-publish
git status --short --branch
```

Apply the intended source/data changes there. If work was done in
`/root/Desktop/lyb/deep_reserch`, copy only the needed files into the checkout.
Do not bulk-copy caches, virtualenvs, secrets, or third-party checkouts.

Build the production static site:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
cd ..
```

Sync the static export into the deploy artifact directory:

```bash
rsync -a --delete --exclude 'wrangler.jsonc' frontend/out/ web/dist/
test -f web/dist/wrangler.jsonc
```

If `web/dist/wrangler.jsonc` is missing, restore it before committing:

```json
{
  "name": "deepresearcharena",
  "compatibility_date": "2025-01-01",
  "assets": {
    "directory": "."
  }
}
```

Inspect and commit:

```bash
git status --short
git diff --stat
git add frontend web/dist data/results/deep_v3 data/results/deep_v4 data/tasks docs README.md claude.md CLAUDE.md agent.md AGENT.md AGENTS.md
git commit -m "Update Deep Research Arena website"
git push origin main
```

After pushing, Cloudflare should redeploy the site from GitHub. Verify:

```bash
curl -I https://www.deepresearcharena.com/
curl -s https://www.deepresearcharena.com/api/leaderboard | head
```

## Local Verification

Before pushing a frontend change:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
```

After syncing `frontend/out` to `web/dist`, smoke-test the static artifact:

```bash
cd ..
python3 -m http.server 8080 --directory web/dist
```

In another terminal:

```bash
curl -I http://127.0.0.1:8080/
curl -s http://127.0.0.1:8080/api/leaderboard | head
```

For Python/scoring changes, run the relevant tests before rebuilding the site:

```bash
python -m pytest -q
```

## Remote Benchmark Execution

The sandbox and long-running benchmark jobs live on `westd` / WSL. Useful paths:

- Remote project: `/opt/deep_reserch`
- Main venv: `.venv-camel`
- Sandbox services: Magento `:7770`, Postmill `:9999`, Kiwix `:8090`
- Search shim: `:8081`
- DS proxy: `:8088`

Common remote commands:

```bash
ssh westd
wsl -d Ubuntu
cd /opt/deep_reserch
.venv-camel/bin/python scripts/build_deep_leaderboard.py
```

For long-running benchmark jobs, use the existing scripts and scheduled-task
pattern already documented in the repository. Avoid running fragile long jobs
directly in a short SSH session.

## Security Rules

- Never commit API keys, provider tokens, `.env`, `secrets.yaml`, `.pem`, or
  `.key` files.
- Never commit virtualenvs, caches, Playwright artifacts, `node_modules`, or
  temporary benchmark scratch files.
- Be careful with `third_party/`, `webarena_ref/`, `paper_dr_lab/`, and large
  corpus files. They are generally not part of a routine website update.
- Do not edit `web/dist/` by hand except for emergency static-asset fixes.
  Prefer editing `frontend/`, rebuilding, and syncing.
