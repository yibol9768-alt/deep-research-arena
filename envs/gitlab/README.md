# GitLab Environment (WebArena `gitlab-populated-final-port8023`)

Self-hosted GitLab with seeded repos, issues, MRs, and users for
deep-research tasks on dev-ops / code collaboration data.

## Start / Reset

```bash
cd envs/gitlab
./reset.sh               # down -v → up -d → wait healthy (3-5 min cold start!)
```

## Port

`8023:8023`. Runner env var: `GITLAB=http://localhost:8023`.

## Seeded credentials

- Admin: `root` / `Password.1`
- Regular user: `byteblaze` / `hello1234`  (per WebArena docs)

## Remote deployment (westd + WSL)

- tar: `/mnt/d/webarena/gitlab-populated-final-port8023.tar` (~72 GB)
- compose dir: `/root/deep_reserch/envs/gitlab/`

## Caveats

- Cold start is slow (Rails + PG + Redis + Sidekiq + Nginx all in one).
  Allow 180s start_period and up to 360s for full health.
- GitLab bakes the external URL into its config on boot — we inject
  `external_url 'http://localhost:8023'` via `GITLAB_OMNIBUS_CONFIG`.
