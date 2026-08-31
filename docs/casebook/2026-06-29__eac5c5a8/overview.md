# Deployment — VPS HTTPS, Docker packaging, and public guide

## Current state

This case remains open. Its goal is to get HTTPS working on the existing VPS,
then turn that experience into a portable Docker Compose deployment and a
public-facing README. The phased plan is in
[deployment-plan.md](deployment-plan.md).

**Phase 2 (live TLS) is fully done:** the app now serves over HTTPS behind
Caddy on the existing VPS, with a valid Let's Encrypt certificate (auto-renewed
by Caddy), an HTTP->HTTPS redirect, h21 bound to loopback `127.0.0.1:8000`, and
`secure_cookies` enabled — the `Secure` session cookie was confirmed in the
browser on a live HTTPS login. h21 runs as an enabled systemd service
(`Restart=always`) that replaced the previous manual `screen` supervision, so
reboots and crashes recover automatically. The tested reverse-proxy shape is a
single Caddy site block proxying to loopback:8000, as captured in
`deploy/Caddyfile.example`. Phase 3 (Dockerization) is not yet started; for
Phase 4, a minimal top-level README (intro, quick start, doc pointers) now
exists, but the full deployment guide still awaits the tested Docker setup.
The existing root `Dockerfile` was found broken during the README pass — its
build produces an empty wheel and an installed (non-editable) package cannot
resolve `static/` — so Phase 3 should replace or remove it; the docs no longer
advertise it as a working path.

The branch contains three application changes:

- an idiomatic inline server CLI with safe port-8000 bind defaults and port
  validation;
- configurable secure session cookies for HTTPS;
- a targeted reset command that invalidates sessions before deleting account
  data and preserves unrelated files and avatars.

The rejected complex systemd unit and root-owned code/configuration deployment
model have been removed from the repo; the minimal interim unit supervising the
live host is deliberately not committed, since proper non-root supervision
arrives with Docker in Phase 3. The previous direct-IP Ubuntu guide was also
removed rather than preserving an insecure or untested deployment path.

## Settled direction

- Public deployment requires TLS; Caddy is the selected reverse proxy.
- TLS will first be configured and validated on the existing VPS without
  redesigning its current application supervision.
- Docker Compose will then become the primary reproducible deployment path,
  including Caddy, secrets, persistent state, and a non-root application
  container.
- A top-level README will present the tested Docker deployment after the
  container work is complete.

## Verification so far

- `PYTHONPATH=src python3 -m unittest discover -s tests -v` — 2 tests passed.
- Python AST parsing and `git diff --check` — passed.
- Live HTTPS verified on the VPS: Let's Encrypt certificate issuance and trust,
  `https://` -> 302 `/login` via Caddy, `http://` -> 308 redirect to HTTPS,
  h21 on loopback:8000, the `Secure` session cookie on login, external
  reachability, and recovery after a service restart.

## Open thread

The live VPS checkout runs this branch. If the branch history is rewritten
(rebase onto master) or the branch is merged and deleted, the live checkout
must be updated to the rewritten ref or moved back to master afterwards.
