# Reddit Environment (Postmill, WebArena `postmill-populated-exposed-withimg`)

WebArena's forum sandbox. Self-hosted Postmill (reddit clone) with seeded
posts and users for deep-research tasks on discussion / opinion data.

## Start / Reset

```bash
cd envs/reddit
./reset.sh               # down -v → up -d → wait healthy
```

No base_url rewrite needed (Postmill reads Host header dynamically, unlike
Magento which pins `base_url` in its DB).

## Port

`9999:80`. Runner env var: `REDDIT=http://localhost:9999`.

## Seeded credentials (per WebArena)

- Default user: `MarvelsGrantMan136` / `test1234`
- (Other accounts exist — see WebArena README for full list.)

## Remote deployment (westd + WSL)

- tar: `/mnt/d/webarena/postmill-populated-exposed-withimg.tar` (49 GB)
- compose dir: `/root/deep_reserch/envs/reddit/`
