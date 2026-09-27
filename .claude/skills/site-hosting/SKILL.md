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
  no build change. It also copies each `apps/<name>/` folder as-is to
  `docs/<name>/` (served at `beach-math.com/<name>`), so a new student app
  needs no build change either. It also writes
  the teacher-only look-ahead to `docs/teacher/index.html`
  (`beach-math.com/teacher`, see below). `wrangler.jsonc` sets the Worker
  name, `docs/` as the assets directory, and `workers_dev: false`;
  Cloudflare's dashboard manages the build/deploy commands directly.
- **beach-math.com/teacher is behind a sign-in** (Cloudflare Access, Zero
  Trust team `beach-math`). The Access application "beach-math.com" covers
  `beach-math.com/teacher` and `www.beach-math.com/teacher` only, with
  Google as the only login (instant auth), a policy allowing only
  abeach0327@gmail.com, and 1-month sessions. The Google OAuth client lives
  in Aaron's Google Cloud console (redirect URI
  `https://beach-math.cloudflareaccess.com/cdn-cgi/access/callback`).
  Student pages must stay open: after any Access change, curl `/`,
  `/math6/`, `/math78/` and an app (expect 200) and `/teacher/` (expect a
  302 to `beach-math.cloudflareaccess.com`).
- **Never set a Worker-level Access app's scope to "All traffic"**
  (Worker → Domains → Production → Enable Access). It locks every hostname
  the Worker serves, custom domains included. On 2026-09-26 it briefly
  locked students out of the whole site. Preview URLs are protected with
  scope "Previews only", which is safe. The workers.dev address is turned
  off (`workers_dev: false`) instead of protected, because it can't be
  protected on its own.
- The Cloudflare connection in Claude sessions can read Access settings
  but can't create or change them (API error 1010), so Access changes are
  made by Aaron in the dashboard.
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
