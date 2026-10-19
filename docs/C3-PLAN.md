# C3 plan: publish the dashboard (Caddy + DNS), close `/docs`

Status 2026-10-19 (night): steps 1 to 5 are DONE except the owner's own browser check. The dashboard is LIVE at
https://cdl-demo.accelentai.com (not advertised, demo password still private).
- Step 1 code `bc592c1`; step 2 deploy 16:13 Vancouver (rollback `src.before-20261019-161345`, `compose.yaml.before-20261019-161345`);
  19 of 19 checks inside the container, both logins 200, Supabase unchanged.
- Step 3 DNS: the owner added `A cdl-demo -> 62.238.51.45`, DNS only (grey), verified at both Cloudflare nameservers and 1.1.1.1/8.8.8.8.
- Step 4 Caddy (approved): backup `/opt/n8n/Caddyfile.before-20261019-233253` (250 bytes), site block appended (1171 bytes), `caddy validate`
  OK, graceful reload OK. Let's Encrypt certificate (TLS 1.3) valid 2026-10-19 to 2027-01-17, renewed automatically by Caddy.
  Rollback: `cat <backup> | sudo tee /opt/n8n/Caddyfile` then `docker exec n8n-caddy-1 caddy reload --config /etc/caddy/Caddyfile`.
- Step 5 outside checks from the laptop: 26 of 26 (http redirects to https, security headers, /docs /redoc /openapi.json 404,
  POST /calls and /call-reports 404, dashboard endpoints 401 without a login, sign-in limit 401 x5 then 429 through Caddy,
  n8n.accelentai.com still answers). Caddy's log shows cookies as REDACTED and holds no password text.
- Seen in the log within minutes of going live: 105 requests from 20 addresses, including Let's Encrypt validation and automated
  scanners asking for /.env and similar (all 404). The hostname is discoverable at once (certificate transparency logs), so the
  hardening in step 1 is not optional.
- Owner check in a real browser (2026-10-19): sign-in failed once in the owner's normal browser window with "Couldn't reach the
  server" (the request never reached Caddy; cause not found, an extension or saved state is likely), then worked in a private window
  or another browser. After sign-in: To do shows 7 people, the detail page opens, no red console errors (so the security policy
  blocks nothing on those pages). Also seen: Caddy advertises HTTP/3 (`Alt-Svc: h3`) but UDP 443 is closed; browsers fall back, but
  it is a mismatch (the n8n site has it too). Optional cleanup, needs approval: serve only h1/h2 or open UDP 443.
- NOT verified: audio playback under the policy (no recorded call in the database yet; `media-src` allows the recording host),
  the n8n to /call-reports hop. Steps 6 and 7 (independent review, C4 seed data and nightly reset) are not done. Do not put the
  link or the demo password on a resume before them.

## Outcome in plain words

A visitor opens `https://<demo-host>`, signs in as `demo`, and sees the To do page. They cannot reach the
endpoints only n8n should call, cannot read `/docs`, and the existing n8n site keeps working exactly as before.

## What was found (read-only, 2026-10-17)

| Fact | Evidence |
|---|---|
| Caddy already runs on the server (`n8n-caddy-1`, caddy:2.10.2), publishes 80 and 443, firewall allows both | `docker ps`, `ufw status` |
| Caddy and `cdl-api` are on the same Docker network (`n8n_app`); Caddy resolves `cdl-api` | `docker inspect`, name lookup |
| The Caddyfile is `/opt/n8n/Caddyfile` on the host (mounted read-only) and has ONE site: `n8n.accelentai.com` -> `n8n:5678` | `docker exec ... cat` |
| DNS for `accelentai.com` is at Cloudflare; `n8n.accelentai.com` points straight at the server (DNS only) | `nslookup` |
| The API container's healthcheck calls `/docs` (compose.yaml line 19), so closing `/docs` needs a new healthcheck first | compose.yaml |
| n8n reaches the API by its internal name `http://cdl-api:8000`, never through the public name | n8n node config |
| The database holds 7 test applicants (Test Driver Alpha, John Smith, Drill Wang, ...); phone numbers not inspected | read-only query |

## Decisions the owner must make

1. Hostname. Recommended: `cdl-demo.accelentai.com` (descriptive, does not claim to be a real client's system).
2. Order. Recommended: code hardening first (step 1), then publish. Alternative: publish first and keep the link off the resume.
3. Whether the 7 test applicants stay visible to visitors. Recommended: no. Replace with fictional seed data (C4) before the link goes on a resume.

## Steps

| # | Step | Who | Live change? | Verified by |
|---|---|---|---|---|
| 1 | Code, test-first, no live change: (a) `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`; (b) a public `GET /healthz` and switch the compose healthcheck to it; (c) refuse `POST /calls` and `POST /call-reports` when a `X-Forwarded-For` header is present (Caddy adds it; n8n's internal call never has it); (d) login throttle: too many failed attempts per username and per client address gives 429 for a few minutes | Claude | no | unit tests, mutation checks |
| 2 | Deploy API and compose (healthcheck change goes with the app change, never one without the other) | Claude, approved | yes (about 30 to 60 s without call saving) | `docker compose ps` healthy, in-container checks |
| 3 | DNS: add an `A` record `<demo-host>` -> `62.238.51.45`, "DNS only" (grey cloud) so Caddy can get its certificate | Owner, in Cloudflare | yes | `nslookup` |
| 4 | Caddy: back up `/opt/n8n/Caddyfile`, append the site block below, `caddy validate`, then `caddy reload` (graceful; an invalid file is refused and the old config keeps running) | Claude, approved | yes (also touches the n8n site's proxy, 0 s expected) | `curl` from outside, n8n site still 200 |
| 5 | Check from outside and in a real browser (see "Verification") | Claude + owner | no | table below |
| 6 | Independent review of login, cookie, throttle and headers BEFORE the link or the demo password goes on a resume | Reviewer agent first, human optional | no | written findings |
| 7 | C4: fictional seed data, nightly reset, rotate the demo password | Claude, approved | yes | read-only counts |

## Draft Caddy site block (step 4)

```
<demo-host> {
    encode zstd gzip

    # Endpoints only n8n may call, and the API docs: not reachable from the internet at all.
    @internal path /calls /calls/* /call-reports /call-reports/* /docs /docs/* /redoc /openapi.json
    respond @internal 404

    header {
        Strict-Transport-Security "max-age=31536000"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy no-referrer
        # media-src must allow the signed recording host the audio redirects to
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' https://*.r2.cloudflarestorage.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        -Server
    }

    log {
        output file /var/log/caddy/cdl-demo.log {
            roll_size 10MiB
            roll_keep 3
            roll_keep_for 168h
        }
        format json
    }

    reverse_proxy cdl-api:8000
}
```

## Verification (expected vs observed; fill in when run)

| Check | Expected |
|---|---|
| `http://<host>` | redirects to https |
| `https://<host>/login` | 200, valid certificate, the headers above present |
| `/docs`, `/openapi.json`, `/calls`, `/call-reports` from outside | 404 |
| The same two POST endpoints from inside the Docker network (n8n path) | still work (401 without key, 422 with key and empty body) |
| Sign in as `demo` in a real browser | To do page loads; cookie has Secure, HttpOnly, SameSite=Lax |
| Wrong password many times | 401, then 429 |
| Play a recording in the browser | audio plays under the CSP (the likeliest thing to need a tweak) |
| `https://n8n.accelentai.com` | unchanged, still works |
| Caddy log lines | no cookie or password values |

## Risks and rollback

| Risk | Mitigation / rollback |
|---|---|
| Bad Caddyfile breaks the n8n site | `caddy validate` first; reload keeps the old config if the new one is invalid; keep `Caddyfile.before-<stamp>` and reload it |
| Healthcheck points at a closed `/docs`, container turns unhealthy, worker never starts | step 1(b) and the deploy go together; roll back with `src.before-<stamp>` |
| CSP blocks the audio or a page script | test in a browser before announcing; loosen only the one directive that failed |
| Visitors write to the live database through the demo account | field limits and the audit log exist; the nightly reset (C4) cleans up; keep the link off the resume until C4 is done |
| Brute force on `owner` (admin) | throttle (step 1d), long random password; consider hiding admin behind a second hostname or IP allow-list later |
| Test calls contain a real phone number | do not publish the link before the data is replaced by seed data |

## Real actions expected

About 3 SSH sessions for the Caddy change, 1 file edit on the server (`/opt/n8n/Caddyfile`), 1 Caddy reload,
1 DNS record (owner), 1 API deploy (about 8 SSH sessions), 0 phone calls, 0 Zoho writes.

## Not verifiable by me

Cloudflare settings (no access), certificate issuance until DNS exists, behaviour in the owner's real browsers
and phone, and anything an independent security review would find.
