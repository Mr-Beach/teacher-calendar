---
name: site-hosting
description: How beach-math.com is hosted and deployed (Cloudflare Workers Builds from main, custom domain, the docs/index.html redirect stub, why not GitHub Pages) and how to rebuild the setup. Use when the published site isn't updating, a deploy fails, DNS/domain questions come up, or the hosting needs rebuilding.
---

# Site hosting (beach-math.com)

The published site is **beach-math.com**, served by a Cloudflare Worker
(static assets), not GitHub Pages. This exists because the district's
Fortinet web filter blocks `*.github.io` at the network level for staff and
students (IT, verbatim: "we block GitHub at the firewall level for all
staff for security reasons"); moving the actual serving off GitHub's
infrastructure entirely (not just the hostname) removes any risk that the
filter is blocking GitHub's IP ranges rather than just the hostname.
Confirmed 2026-09-23 via direct DNS/header check: `beach-math.com` and
`www.beach-math.com` resolve to Cloudflare IPs and respond with
`server: cloudflare` — nothing in the serving path touches GitHub anymore.

- **Auto-deploy**: a Cloudflare Workers Builds project (`teacher-calendar`,
  in Aaron's Cloudflare account) is connected via the Cloudflare GitHub App
  to `Mr-Beach/teacher-calendar`, scoped to that repo only. Every push to
  `main` triggers: build command `python3 scripts/build_site.py docs`
  (run in Cloudflare's own ephemeral checkout — this never gets committed
  back to git), then `npx wrangler deploy`. `build_site.py` renders every
  `courses/<slug>.json` to `docs/<slug>/index.html` (served at
  `beach-math.com/<slug>`) and writes the front page (one button per
  course) to `docs/index.html` for the bare domain, so a new course needs
  no build change. No
  `wrangler.jsonc` is committed to this repo; wrangler auto-detects `docs/`
  as the assets directory, and Cloudflare's dashboard manages the build/
  deploy commands directly.
- **Domain**: `beach-math.com` was registered through Cloudflare Registrar
  and its DNS zone lives on Cloudflare. `beach-math.com` and
  `www.beach-math.com` are attached to the Worker as Custom Domains
  (Worker's **Domains** tab), which is what makes Cloudflare own and manage
  their DNS records and TLS certs — there are no manually-managed DNS
  records for this site.
- **`docs/index.html` in this repo** is now a small static redirect stub
  (meta-refresh + link to `beach-math.com`) so `mr-beach.github.io` — the
  original address, still enabled via GitHub Pages — keeps working for
  anyone with it bookmarked, instead of going dead or serving a stale
  calendar. It is committed once and should never be overwritten by the
  normal edit workflow (see step 5 above). `docs/CNAME` was removed since
  GitHub Pages no longer owns the custom domain.
- **If this ever needs rebuilding from scratch**: Cloudflare dashboard →
  Workers & Pages → `teacher-calendar` → Settings → Builds, for build/
  deploy commands and the GitHub connection; → Domains tab, for the custom
  domain attachments.
