# Deployment plan

## Goal

Secure the current VPS with HTTPS, then provide a portable, tested Docker
deployment that other users can understand and operate from the repository.

## 1. Simplify the current branch

- [x] Replace the separate server-entry module with idiomatic inline
  `argparse` handling and safe bind defaults.
- [x] Keep configurable secure session cookies.
- [x] Keep session-safe, targeted state reset behavior.
- [x] Remove the systemd unit and root-owned code/configuration deployment
  model.
- [x] Reduce the Ubuntu guide to material that is useful for the live TLS
  migration or defer documentation until it has been tested.

## 2. Enable TLS on the existing VPS — done

Completed live on 2026-08-27; the verified results are summarized in
[overview.md](overview.md). The app serves over HTTPS behind Caddy.

- [x] Inventory the current application process, paths, ports, DNS, and firewall.
- [x] Install and configure Caddy in front of the loopback application server.
- [x] Enable secure cookies and restart the application.
- [x] Validate HTTP-to-HTTPS redirect, certificate trust, proxying,
  login/session cookies (`Secure` confirmed), external reachability, and
  recovery after restart.
- [x] Record the tested reverse-proxy configuration (`deploy/Caddyfile.example`).

Note: the application supervisor was moved from a manual `screen` session
to a minimal enabled `systemd` unit for reboot persistence —
a deviation from the "keep screen" interim decision, justified because the
screen session had no boot recovery. Non-root supervision remains a Phase 3 goal.

## 3. Dockerize the deployment

- Build a minimal multi-stage image with locked dependencies and a non-root
  runtime user.
- Package static assets so the image does not depend on the repository layout.
- Add explicit health and secret-file support where needed.
- Define Docker Compose services for h21 and Caddy on a private network.
- Persist SQLite state, avatars, signing data, and Caddy certificates in named
  volumes; keep the application image read-only.
- Document and test initialization, first invite, update, backup, restore,
  restart, and rollback behavior.
- Decide whether publishing versioned multi-platform images is required for
  the initial public deployment.

## 4. Publish the deployment guide

- Add a top-level README with a short project introduction and development
  quick start.
- Make Docker Compose the primary deployment guide.
- Include configuration, secrets, TLS, persistence, updates, backups, restore,
  and troubleshooting, linking to deeper documentation where useful.

## Completion criteria

- HTTPS works reliably on the current VPS.
- A fresh host can start h21 and Caddy from the documented Compose workflow.
- Data survives container recreation, and backup/restore has been exercised.
- The README is sufficient for an interested third party to understand and
  deploy the project.
