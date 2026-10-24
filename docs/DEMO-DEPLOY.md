# Demo deploy runbook (C4 live steps)

Goal: a public demo at `https://cdl-demo.accelentai.com` that runs only fictional data, and the real dashboard moved to
`https://cdl-admin.accelentai.com` (decision 9 in `docs/C4-PLAN.md`). Files: `api/deploy/demo/`.

**Each step below needs the owner's explicit approval before it runs.** After each step, report the real actions
(server changes) separately from tests. Nothing here touches Zoho, VAPI, n8n workflows or the real database,
except step 4 (Caddy, which also fronts n8n) and step 6 (the real users table).

## What was rehearsed locally (no live change) on 2026-10-23
The exact compose file, built from this repo, was run on Docker Desktop and checked from inside the API container:
non-root (uid 10001), read-only filesystem, `DEMO_MODE=1`, no n8n/VAPI/Zoho keys, cannot resolve `cdl-api` or `n8n`,
no outbound internet, seed writes 39 fictional people, demo login 200, to-do and calls load, both sample recordings
play (200, audio/wav), `POST /calls` and `/call-reports` answer 503, a recruiter response holds no `last_error` or
Zoho id, the nightly reset works twice in a row, a restart comes back healthy, `stop` takes about 1 second.

## Before step 1
- Build the demo source from a CLEAN release worktree of the exact commit to release (never the shared working
  tree, see CLAUDE.md). It is the folder `api/` minus `.venv`, `tests`, `deploy`: `app`, `migrations`,
  `requirements.txt`, `Dockerfile`, `.dockerignore`.
- Cloudflare: add ONE record, type A, name `cdl-admin`, value `62.238.51.45`, proxy status **DNS only** (grey cloud).
  `cdl-demo` already exists with the same value.

## Step 1: prepare the server (no traffic yet)
1. `sudo mkdir -p /opt/cdl-demo/{src,recordings,secrets}`; owner `hermesadmin`.
2. `docker network create --internal demo_edge` (internal: no member can reach the internet).
3. Copy: the source tar into `src/`, `api/deploy/demo/compose.yaml`, the two WAV files from `demo-recordings/` into
   `recordings/`.
4. Create `/opt/cdl-demo/.env.demo` from `.env.example`, values generated ON the server (`openssl rand`), `chmod 600`.
   `SESSION_SECRET` must differ from the real instance's.
Rollback: `sudo rm -rf /opt/cdl-demo; docker network rm demo_edge`.

## Step 2: start the demo stack and fill it
1. `cd /opt/cdl-demo && docker compose --env-file .env.demo up -d --build`; wait for both containers healthy.
2. Seed: `docker compose --env-file .env.demo exec -T demo-api python -m app.demo_seed` (39 fictional people).
3. Demo login: `docker compose --env-file .env.demo run --rm -v /opt/cdl-demo/secrets:/secrets demo-api python -m app.users_cli create demo recruiter --write-password-to /secrets/demo.password`.
   The password is written to a file, never printed or pasted into chat.
4. Run the same checks as the rehearsal from inside the container.
Rollback: `docker compose --env-file .env.demo down -v`.

## Step 3: install the nightly reset (03:00 Vancouver)
Copy `demo-reset.service` and `demo-reset.timer` to `/etc/systemd/system/`, `sudo systemctl daemon-reload`,
`sudo systemctl enable --now demo-reset.timer`, run `sudo systemctl start demo-reset.service` once and read
`journalctl -u demo-reset`. Rollback: `systemctl disable --now demo-reset.timer` and delete the two unit files.

## Step 4: Caddy (the one change to the shared n8n stack)
1. Back up `/opt/n8n/Caddyfile` (and `compose.yaml`).
2. Put Caddy on `demo_edge`: add `demo_edge` (external) to the caddy service's networks in `/opt/n8n/compose.yaml`,
   then `docker compose up -d caddy` (a few seconds of Caddy downtime, n8n itself is not restarted).
3. Replace the existing `cdl-demo.accelentai.com { ... }` block with the two blocks in
   `api/deploy/demo/Caddyfile.cdl-demo.snippet` (demo to `demo-api:8000`, `cdl-admin` to `cdl-api:8000`).
4. `docker exec n8n-caddy-1 caddy validate --config /etc/caddy/Caddyfile`, then `caddy reload` (graceful).
   Caddy fetches the certificate for `cdl-admin` on first use (the DNS record must exist and propagate first).
Rollback: restore the backed-up Caddyfile and compose.yaml, reload.

## Step 5: outside checks (from this machine, not the server)
- `cdl-demo`: login page 200; demo login works; the list shows only the fictional drivers; `POST /calls` and
  `/call-reports` and `/docs` answer 404; response headers present (CSP with `media-src 'self'`, HSTS, nosniff,
  frame deny, no `Server`); a 100 KB form body to `/login` is refused (413).
- `cdl-admin`: needs the owner login; a `demo` login there still exists until step 6.
- `n8n.accelentai.com` still works (Caddy was touched).

## Step 6: close the real instance to strangers (owner runs the delete)
- Remove the `demo` recruiter from the real `users` table (a delete in the real database, so the owner runs it).
- When the real API next deploys: set `INSTANCE_NAME=real` in `/opt/cdl-api/.env.api` (one-time logout of the owner)
  and deploy n8n and API fixes together as one approved step (CLAUDE.md).

## Step 7: owner's browser check, then the link may go on the resume.

## Not covered here
The independent review's remaining items: IPv6 `/64` login throttle, `__Host-` cookie prefix, old files on the
server, database indexes. The "new call overwrites a recruiter's correction" rule is an open owner decision.
