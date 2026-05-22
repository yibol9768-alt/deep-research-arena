# Claude Entry Point

Use `claude.md` in this directory as the canonical maintenance guide.

Key operational facts:

- Public site: `https://www.deepresearcharena.com/`
- Repository: `yibol9768-alt/deep-research-arena`
- Current production source: `frontend/`
- Static deploy artifact: `web/dist/`
- Build: `cd frontend && npm ci && npm run typecheck && npm run build`
- Sync: `rsync -a --delete --exclude 'wrangler.jsonc' frontend/out/ web/dist/`
- Publish: commit source/data plus `web/dist/`, then push `main`

The live domain is served by Cloudflare. GitHub is still the source-of-truth
update path: pushing the correct files to the GitHub repository is what updates
the public site.

## Hard rule: log every update on the site before deploying

Every meaningful change to scoring, tasks, sandbox enforcement, frontend, or
methodology MUST be logged in `data/changelog.json` and rendered on the public
`/changelog` page before the change is deployed.

Workflow for any update:

1. Make the code/data change.
2. Append a new entry to the top of the `entries` array in
   `data/changelog.json` (schema: `{version, date, title, summary, tags[],
   sections:[{heading,bullets[]}], links?}`). Version format is
   `v<MAJOR>-<YYYY-MM-DD>`. Keep summaries to 1-2 sentences and bullets terse.
3. Rebuild: `cd frontend && npm run typecheck && npm run build`.
4. Sync: `rsync -a --delete --exclude 'wrangler.jsonc' frontend/out/ web/dist/`
   (then verify `web/dist/wrangler.jsonc` still exists; restore from
   `claude.md` if rsync ate it).
5. Commit the source/data change plus the regenerated `web/dist/`.
6. Push to `main`. Cloudflare redeploys automatically.

Skipping the changelog step is not acceptable, even for small fixes — the
`/changelog` page is the user-facing record of every shipped change.

See `claude.md` for the longer maintenance guide.
