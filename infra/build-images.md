# Building the Sandbox Images

The DR Benchmark V2 sandbox is 5 docker containers. This doc covers
both **dev path** (rebuild on westd from existing local images) and
**3rd-party path** (pull from a public registry, no build needed).

## Image inventory

| Image | Source | Size | Builds via |
|---|---|---:|---|
| `shopping_final_0712:latest` | WebArena Magento snapshot | ~4.2 GB | preexisting on westd |
| `postmill-populated-exposed-withimg:latest` | WebArena Postmill snapshot | ~1.8 GB | preexisting on westd |
| `kiwix-serve` | public Kiwix project | ~50 MB + .zim mount | `docker pull ghcr.io/kiwix/kiwix-serve:latest` |
| `dr-bench-gateway:latest` | this repo | ~90 MB | `docker build -f infra/Dockerfile.gateway` |
| `dr-bench-ds-proxy:latest` | this repo | ~70 MB | `docker build -f infra/Dockerfile.ds_proxy` |

The 4.2 + 1.8 GB images are the heavy ones. They contain the actual
sandbox content (Magento DB, Postmill DB) so they're pre-populated.
We can NOT regenerate them from scratch publicly because the corpora
were scraped from a specific point in time (2025-09-01 cutoff per
methodology); reproducing them would change the benchmark.

## Path A — Dev (rebuild on westd)

```bash
# rsync V2 code to westd
bash infra/sync_to_westd.sh --apply

# On westd, in WSL Ubuntu
ssh my5090 'wsl -d Ubuntu -- bash -lc "
  cd /opt/deep_reserch
  docker build -f infra/Dockerfile.gateway   -t dr-bench-gateway:latest .
  docker build -f infra/Dockerfile.ds_proxy  -t dr-bench-ds-proxy:latest .
  docker pull ghcr.io/kiwix/kiwix-serve:latest

  # Bring up the stack
  docker compose -f infra/sandbox.docker-compose.yml up -d
  sleep 60   # let healthchecks settle

  # Smoke test all 5 services
  curl -fsS http://localhost:7770/   >/dev/null && echo shopping ok
  curl -fsS http://localhost:9999/   >/dev/null && echo reddit ok
  curl -fsS http://localhost:8090/   >/dev/null && echo wiki ok
  curl -fsS http://localhost:8081/healthz >/dev/null && echo gateway ok
"'
```

If anything fails, see `Phase 8-D` runbook in
`/Users/liuyibo/.claude/plans/optimized-coalescing-tower.md`.

## Path B — 3rd-party (pull from public registry)

**Status**: not yet published. To make this work for outsiders, the
maintainer needs to:

1. Choose a registry (GHCR / Docker Hub / private). For an OSS paper,
   GHCR under a public org is simplest.
2. Tag and push:
   ```bash
   for img in shopping_final_0712 postmill-populated-exposed-withimg \
              dr-bench-gateway dr-bench-ds-proxy; do
     docker tag "$img:latest" "ghcr.io/<your-org>/$img:v2-2026-05-09"
     docker push "ghcr.io/<your-org>/$img:v2-2026-05-09"
   done
   ```
3. Update `infra/sandbox.docker-compose.yml` `SANDBOX_REGISTRY` env
   default to point at the chosen registry.
4. Make sure GHCR visibility is set to "public" so outsiders pull
   without auth.

Once published, an outside contributor runs:

```bash
git clone <this repo>
cd deep_reserch
export DEEPSEEK_API_KEY=sk-...           # they bring their own
docker compose -f infra/sandbox.docker-compose.yml up -d
```

Five containers come up; gateway healthcheck on `localhost:8081/healthz`
returns 200 within ~90 seconds.

## Path C — Offline rebuild (the corpora aren't published)

If the maintainer doesn't want to publish the heavy 4 GB / 28 GB images,
outsiders can rebuild Magento + Postmill + Kiwix from scratch using:

* `scripts/build_deep_golden.py` — scrapes the sandbox content
* WebArena's bring-up scripts (`envs/{shopping,reddit}/docker-compose.yml`)
* A Wikipedia .zim file (download from kiwix.org/zim mirrors)

This takes a few hours and produces images with **slightly different**
content (timestamps, search indices) than the published sandbox. Not
recommended for paper-comparable scores; recommended for prototyping.

## Storage notes

The Kiwix Wikipedia snapshot is ~28 GB compressed. The compose file
mounts a host-provided .zim file via `WIKI_ZIM_DIR` env so we don't
have to bake it into the image:

```bash
export WIKI_ZIM_DIR=/path/to/your/zim_dir   # contains wikipedia_en_*.zim
docker compose ... up
```

If this env var is unset, the compose file expects `./infra/wiki-zim/`
to contain the file. On westd it's already at `/opt/deep_reserch/wiki/`
or similar (find it with `find / -name '*.zim' 2>/dev/null`).
