# How Maritimer was deployed

This is the record of the actual production deployment: which services were used, the settings chosen and why, how each step was checked, and the problems hit along the way. For a generic, reusable guide with every environment variable explained, see [DEPLOY.md](DEPLOY.md).

No secrets are stored here. Passwords, API keys and connection strings live only in the dashboards of the services that use them.

---

## Live system

| Piece | Where | Address |
|---|---|---|
| Frontend (React SPA) | Vercel | https://maritimer-sage.vercel.app |
| Backend API (Django, Docker) | Render, Singapore, free plan | https://maritimer-api.onrender.com/api/v1 |
| Database (PostgreSQL) | Neon, AWS Asia Pacific (Singapore) | private |
| File storage (invoices, documents, PDFs) | Cloudflare R2 bucket `maritimer-files` | private (signed links only) |
| Sign-in (Google) | Firebase Authentication, project `maritimer-entnt` | — |
| Source code | GitHub `Raajzz/maritimer` (public) | https://github.com/Raajzz/maritimer |

```
Browser ── https://maritimer-sage.vercel.app (Vercel)
   │  1. "Continue with Google" → Firebase popup → Firebase ID token
   │  2. every API call sends  Authorization: Bearer <ID token>
   ▼
https://maritimer-api.onrender.com (Render, Docker, Singapore)
   ├─ verifies the token against Google's public keys (project maritimer-entnt)
   ├─ looks up role and approval status in its own database
   ├─ PostgreSQL ── Neon (Singapore, direct connection, SSL)
   └─ files ─────── Cloudflare R2 (private bucket, 5-minute signed download links)
```

Everything runs on free tiers. The only cost caveat is that Cloudflare asks for a card to enable R2, but doesn't charge within the 10 GB free allowance.

---

## Order of work

Each service needs values from the one before it, so they were set up in this order:

1. GitHub: push the code
2. Firebase: Google sign-in
3. Neon: database
4. Cloudflare R2: file storage
5. Render: backend API
6. Vercel: frontend
7. Connect them: Firebase authorized domain, then CORS on Render

---

## 1. GitHub

- The repository was pushed to `Raajzz/maritimer` and made **public**.
- Before making it public, I checked that no secrets were tracked:
  - `.gitignore` excludes `.env`, `*.env.local`, `backend/media/`, `node_modules/`, `dist/` and local tool folders.
  - Only the `.env.example` files are committed, and they hold placeholders.
- Commits use the GitHub no-reply address as the author email.

## 2. Firebase (Google sign-in)

1. Created the Firebase project **`maritimer-entnt`**.
2. **Authentication → Sign-in method:** enabled **Google** as the only provider.
3. **Project settings → Your apps:** registered a **Web** app. Firebase Hosting isn't used.
4. Took four values from the web config (`apiKey`, `authDomain`, `projectId`, `appId`). These are public by design, because Firebase web config ships to every browser.
5. **Authentication → Settings → Authorized domains:** `localhost` is there by default, and `maritimer-sage.vercel.app` was added after the Vercel deploy (step 7).

No Firebase service account is used. The backend verifies Google ID tokens with Google's published public keys and needs only the project ID. This was a deliberate fix; see "Problems hit" below.

## 3. Neon (PostgreSQL)

**Create-project form:**

| Field | Chosen | Why |
|---|---|---|
| Project name | `maritimer` | — |
| Region | **AWS Asia Pacific (Singapore)** | Same region as the Render API. The default (US East, Ohio) would add about 200 ms to every query. |
| Services | **Postgres database only** | Object storage, Functions, Better Auth, AI gateway and Realtime aren't used. Files go to R2 and auth is Firebase. |
| Postgres version | Neon default (**18**) | Migrations and the app were verified on it. Local development uses 16. |

**After creation:**

- Neon offered a "set up with an AI agent / `neon init`" flow. **It was skipped.** That flow targets Node.js apps: it adds `neon.ts` and a `package.json` and rewires drivers. The backend is Django and already reads `DATABASE_URL`, so no code changes were needed.
- **Connect** was used with **Connection pooling off**, giving the **direct** connection string (database `neondb`, role `neondb_owner`, no `-pooler` in the host, `sslmode=require`).
  - The direct string is safer for psycopg 3, which reuses prepared statements, and a transaction-mode pooler can break them.
  - Django migrations also belong on a direct connection.

**Check:** before anything was deployed, the migrations were run from a laptop against Neon:

```bash
cd backend
DATABASE_URL='<neon direct string>' DJANGO_SETTINGS_MODULE=config.settings.dev \
  .venv/bin/python manage.py migrate          # every migration "OK"
.venv/bin/python manage.py seed_masterdata    # 15 countries, 9 ports, 18 service categories, 4 request policies
```

The result was 44 tables and a server reporting `PostgreSQL 18.x`.

## 4. Cloudflare R2 (file storage)

1. **R2 Object Storage:** enabled R2 on the account.
2. **Create bucket:**
   - Name: `maritimer-files`
   - Location: Automatic
   - Storage class: Standard
   - **Public access off**
3. **Manage API tokens → Create API token:**
   - Permission: **Object Read & Write**
   - Scope: **only `maritimer-files`**
   - TTL: Forever
4. Kept three values: **Access Key ID**, **Secret Access Key** and the **S3 endpoint** (`https://<account-id>.r2.cloudflarestorage.com`). The token's own "Token value" isn't used by the app.

**Check:** the app's real storage code was run against R2 with production-style settings (`STORAGE_BACKEND=s3`):

| Test | Result |
|---|---|
| Upload a test file | saved, `exists = True` |
| Download through the app's signed link | **200**, contents correct |
| Download the same path *without* the signature | **400**, so the bucket is private |
| Delete the test file | removed |

## 5. Render (backend API)

1. **New → Blueprint**, connected `Raajzz/maritimer`, blueprint name `maritimer`. Render read [`render.yaml`](render.yaml), which defines:
   - a **web service `maritimer-api`**
   - runtime **Docker**, root directory `backend`
   - region **Singapore**, plan **free**
   - health check `/api/v1/health`
2. Environment variables entered when the blueprint asked for them:

| Variable | Value used |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` (preset in the blueprint) |
| `DJANGO_SECRET_KEY` | generated by Render |
| `DJANGO_ALLOWED_HOSTS` | `maritimer-api.onrender.com` (Render's own hostname is also allowed automatically) |
| `DATABASE_URL` | Neon **direct** connection string |
| `FIREBASE_PROJECT_ID` | `maritimer-entnt` |
| `STORAGE_BACKEND` | `s3` (preset) |
| `S3_BUCKET_NAME` | `maritimer-files` |
| `S3_ENDPOINT_URL` | the R2 S3 endpoint |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | from the R2 API token |
| `S3_REGION_NAME` | `auto` (preset) |
| `BOOTSTRAP_ADMIN_EMAIL` | the Google account that should be the first **Admin** |
| `CORS_ALLOWED_ORIGINS` | left empty at first, then set in step 7 |
| `CORS_ALLOWED_ORIGIN_REGEXES` | left empty. Preview deploys can't use Google sign-in anyway, because Firebase authorized domains don't accept wildcards. |
| `AUDIT_LOG_REVOKE_ROLE` | left empty (optional database-level hardening) |
| `WEB_CONCURRENCY` / `SECURE_SSL_REDIRECT` | `2` / `true` (preset) |

3. **Deploy.** The image installs WeasyPrint's system libraries (pango and friends) for PDF generation. On every start, `backend/bin/start.sh` runs:
   1. `migrate`
   2. `seed_masterdata` (safe to repeat)
   3. `bootstrap_admin` with `BOOTSTRAP_ADMIN_EMAIL` (safe to repeat)
   4. gunicorn

**Checks against the live API:**

```bash
curl https://maritimer-api.onrender.com/api/v1/health
# {"status":"ok"}                                              HTTP 200

curl https://maritimer-api.onrender.com/api/v1/auth/me
# {"error":{"code":"unauthenticated",...}}                    HTTP 401  (auth required)

curl -H 'Authorization: Bearer dev:x@y.z' https://maritimer-api.onrender.com/api/v1/auth/me
# HTTP 401  (development tokens are rejected in production)
```

## 6. Vercel (frontend)

1. **Add New → Project**, imported `Raajzz/maritimer`.
2. **Root Directory: `frontend`.** The framework (Vite), build command and output folder come from [`frontend/vercel.json`](frontend/vercel.json), which also adds the single-page-app rewrite and security headers. The `Cross-Origin-Opener-Policy: same-origin-allow-popups` header is what lets the Google popup work.
3. Environment variables, set for **Production and Preview**:

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://maritimer-api.onrender.com/api/v1` |
| `VITE_FIREBASE_API_KEY` | from the Firebase web config |
| `VITE_FIREBASE_AUTH_DOMAIN` | `maritimer-entnt.firebaseapp.com` |
| `VITE_FIREBASE_PROJECT_ID` | `maritimer-entnt` |
| `VITE_FIREBASE_APP_ID` | from the Firebase web config |
| `VITE_DEV_AUTH` | **not set**, so production builds contain no developer sign-in |

4. **Deploy.** The assigned domain is **https://maritimer-sage.vercel.app**.

**Check:** the deployed JavaScript bundle was downloaded and searched:

| Search term | Count | Meaning |
|---|---|---|
| `maritimer-api.onrender.com` | 1 | points at the live API |
| `maritimer-entnt` | 2 | uses the right Firebase project |
| `maritimer.test` (demo emails) | **0** | none shipped |
| `Development sign-in` | **0** | no dev panel |
| `dev:` (dev tokens) | **0** | no dev tokens |
| `localhost:8000` | **0** | no local API address |

## 7. Connecting the services

The frontend and backend live on different domains, so two settings link them:

1. **Firebase → Authentication → Settings → Authorized domains:** added `maritimer-sage.vercel.app`. Without it, the Google popup fails with `auth/unauthorized-domain`.
2. **Render → maritimer-api → Environment:** set `CORS_ALLOWED_ORIGINS=https://maritimer-sage.vercel.app` (scheme included, no trailing slash), then **Save, rebuild, and deploy**.

**Check:** a browser-style preflight request from the Vercel origin:

```bash
curl -X OPTIONS -H 'Origin: https://maritimer-sage.vercel.app' \
     -H 'Access-Control-Request-Method: GET' -H 'Access-Control-Request-Headers: authorization' \
     -D - -o /dev/null https://maritimer-api.onrender.com/api/v1/auth/me
# HTTP/2 200
# access-control-allow-origin: https://maritimer-sage.vercel.app
```

## 8. First sign-in

1. Open https://maritimer-sage.vercel.app and choose **Continue with Google** with the `BOOTSTRAP_ADMIN_EMAIL` account. It lands on the **Admin dashboard**.
2. Any other Google account signs in, chooses a role (Owner, Port agent or Merchant), completes onboarding and waits in **Admin → Approvals**.
3. Each role needs its **own** Google account. Gmail `+` aliases sign in as the same account.

---

## Problems hit and how they were fixed

| Problem | Cause | Fix |
|---|---|---|
| Sign-in returned `401 Invalid or expired token` locally, with `DefaultCredentialsError` in the server log | `firebase_admin.auth.verify_id_token` looks for Google service-account credentials even though it only needs public keys | The backend now verifies tokens with `google.oauth2.id_token.verify_firebase_token`, checking the audience (project ID) and issuer, with cached Google certificates. A service account is only used if one is configured. `firebase-admin`, `google-auth` and `CacheControl` were pinned in `requirements.txt`. |
| Console warnings about `Cross-Origin-Opener-Policy` during the Google popup | Browser noise from the popup flow | Harmless. Production sends `same-origin-allow-popups` from `vercel.json`. |
| Neon offered the pooled (`-pooler`) string by default | Neon's default | Turned pooling off and used the direct string (see step 3). |
| Neon's "set up with AI agent" prompt | Aimed at Node.js projects | Skipped; not needed for Django. |
| Neon created Postgres 18, not 16 | Neon's default version | Verified all migrations and seed data on 18. No change needed. |
| Signing in with the admin's Google account landed in "choose a role", and nobody could approve users | `BOOTSTRAP_ADMIN_EMAIL` on Render was missing `.com`, so the real account wasn't recognised as admin and self-onboarded as an agent | Repaired in the database: the real account became the approved Admin and the mistyped admin user was removed. The empty draft agent company stays, because audit history references it. The variable was corrected, and `bin/start.sh` now logs a warning instead of failing to start if the admin email is wrong. |
| `git push` couldn't authenticate | No Git credential helper for HTTPS | Logged in with `gh auth login` and set the repo's credential helper to the GitHub CLI. |
| Developer sign-in and demo emails visible locally | Intended for local development | They're compiled in only when `VITE_DEV_AUTH=true`. Vercel doesn't set it, and the production API rejects dev tokens anyway. |

## Known limits of the free setup

- **Render free plan sleeps** after 15 minutes without traffic, and the next request takes about 30–50 seconds. To avoid it, ping `/api/v1/health` every 10 minutes (UptimeRobot, cron-job.org) or upgrade the plan.
- **Request expiry** (`python manage.py expire_requests`) needs a scheduled job. Render cron jobs are paid, and requests created from the UI don't expire by default, so it isn't scheduled.
- **Preview deployments** on Vercel can load, but Google sign-in works only on `maritimer-sage.vercel.app` and `localhost`.

## Day-to-day operations

| Task | How |
|---|---|
| Ship a change | Push to `main`. Render rebuilds the API (migrations run on start) and Vercel rebuilds the frontend. |
| Approve a new user | Admin account → **Approvals** |
| See server logs | Render → maritimer-api → **Logs** |
| Inspect the database | Neon → **SQL Editor** or **Tables** |
| Browse stored files | Cloudflare → R2 → `maritimer-files` |
| Rotate the database password | Neon → Roles → `neondb_owner` → Reset password, then update `DATABASE_URL` on Render |
| Rotate R2 keys | Cloudflare → R2 → Manage API tokens → roll or recreate, then update `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` on Render |
| Add another frontend domain | Add it to Firebase authorized domains **and** to `CORS_ALLOWED_ORIGINS` on Render (comma-separated) |
