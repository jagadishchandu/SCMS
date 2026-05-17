Both files are in place. Here's everything you need to know to wire it all up.

---

## What I just created

```
/app/
├── .github/
│   └── workflows/
│       └── azure-static-web-apps.yml      # GitHub Actions CI/CD
└── frontend/
    └── staticwebapp.config.json            # SWA routing + SPA fallback + security headers
```

---

## File 1 — `frontend/staticwebapp.config.json`

This file does **three** things on the SWA side:

1. **Reverse-proxies** `/api/*` → your backend Container App, so frontend + backend share one origin (zero CORS).
2. **SPA fallback** — any deep URL like `/school/dashboard` returns `index.html` instead of 404 (so React Router takes over).
3. **Security headers** — adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` automatically.

### Before you deploy — edit ONE line

Open `/app/frontend/staticwebapp.config.json` and replace:

```jsonc
"rewrite": "https://REPLACE-WITH-BACKEND-FQDN.azurecontainerapps.io/api/*"
```

…with your actual backend Container App URL. Grab it with:

```bash
az containerapp show -n scms-backend -g $RG \
  --query properties.configuration.ingress.fqdn -o tsv
# Example output:
# scms-backend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io
```

Then commit and push — SWA reads this file on the next deploy.

---

## File 2 — `.github/workflows/azure-static-web-apps.yml`

This is the CI/CD pipeline. Every `git push` to `main` rebuilds and deploys the frontend automatically. Pull requests get **free preview environments** (auto-deleted when the PR closes).

### Before your first deploy — set TWO GitHub secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value | Where to get it |
|---|---|---|
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | Deployment token | `az staticwebapp secrets list -n $SWA_NAME -g $RG --query "properties.apiKey" -o tsv` |
| `REACT_APP_BACKEND_URL` | Backend URL **or empty string** | See note below |

### Which value to use for `REACT_APP_BACKEND_URL`?

**Option A — Use the SWA /api reverse-proxy (recommended, no CORS):**

```
REACT_APP_BACKEND_URL = (empty string)
```

With this set to empty, axios uses relative `/api` paths → request hits `https://app.yourdomain.com/api/*` → SWA proxies to your backend → no CORS at all.

**Option B — Frontend calls backend directly (CORS needed):**

```
REACT_APP_BACKEND_URL = https://scms-backend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io
```

The browser hits the backend's URL directly. CORS is satisfied because backend has `FRONTEND_URL` in its env.

> 👉 **My recommendation**: Option A. One origin, no CORS, one fewer thing to break.

---

## Setting up the secrets — exact commands

```bash
# Already-set variables from earlier (re-export if you opened a new shell)
export RG=scms-rg
export SWA_NAME=scms-frontend-swa

# 1. Get the SWA deployment token
az staticwebapp secrets list -n $SWA_NAME -g $RG \
  --query "properties.apiKey" -o tsv
# → Copy this value to GitHub secret AZURE_STATIC_WEB_APPS_API_TOKEN

# 2. Get the backend URL (only needed if you chose Option B above)
az containerapp show -n scms-backend -g $RG \
  --query properties.configuration.ingress.fqdn -o tsv
# → Prefix with `https://` and copy to GitHub secret REACT_APP_BACKEND_URL
#   OR leave the secret empty if you chose Option A (recommended)
```

---

## Putting it all together — full first-deploy flow

```bash
# 1. Variables (from previous step)
export RG=scms-rg
export LOC=centralindia
export SWA_NAME=scms-frontend-swa
export BACKEND_FQDN=$(az containerapp show -n scms-backend -g $RG \
  --query properties.configuration.ingress.fqdn -o tsv)
export BACKEND_URL="https://$BACKEND_FQDN"
echo "Backend FQDN: $BACKEND_FQDN"

# 2. Fill in the rewrite line of staticwebapp.config.json
sed -i.bak "s#REPLACE-WITH-BACKEND-FQDN.azurecontainerapps.io#${BACKEND_FQDN}#" \
  /app/frontend/staticwebapp.config.json
rm /app/frontend/staticwebapp.config.json.bak

# 3. Commit + push (kicks off first build automatically)
cd /app
git add frontend/staticwebapp.config.json .github/workflows/
git commit -m "feat: Azure SWA config + GitHub Actions deploy pipeline"
git push origin main

# 4. Create the SWA (one-time) if you haven't already
az staticwebapp create \
  --name $SWA_NAME -g $RG -l $LOC \
  --source https://github.com/<your-username>/scms \
  --branch main \
  --app-location "/frontend" \
  --output-location "build" \
  --login-with-github

# 5. Pull the deploy token and add it to GitHub
DEPLOY_TOKEN=$(az staticwebapp secrets list -n $SWA_NAME -g $RG \
  --query "properties.apiKey" -o tsv)
echo "Add this as GitHub secret AZURE_STATIC_WEB_APPS_API_TOKEN:"
echo "$DEPLOY_TOKEN"

# 6. Decide your auth/proxy mode:
#    Option A — relative /api proxy (no CORS, recommended):
#      → Add GitHub secret REACT_APP_BACKEND_URL = "" (empty string)
#    Option B — direct backend calls:
#      → Add GitHub secret REACT_APP_BACKEND_URL = $BACKEND_URL

# 7. Grab the frontend URL
export FRONTEND_URL="https://$(az staticwebapp show -n $SWA_NAME -g $RG \
  --query defaultHostname -o tsv)"
echo "Frontend: $FRONTEND_URL"

# 8. Tell backend about the frontend (only matters for Option B; harmless for A)
az containerapp update -n scms-backend -g $RG \
  --set-env-vars FRONTEND_URL=$FRONTEND_URL

# 9. Test
curl -I $FRONTEND_URL
curl $FRONTEND_URL/api/health   # Option A only — proxied through SWA
curl $BACKEND_URL/api/health    # always works
```

---

## What happens on every subsequent push

```
git push origin main
   ↓
GitHub Actions runs azure-static-web-apps.yml
   ↓
yarn install --frozen-lockfile && yarn build
   ↓ (REACT_APP_BACKEND_URL baked in)
SWA upload action ships /frontend/build to Azure
   ↓
SWA reads staticwebapp.config.json — applies routes + headers + SPA fallback
   ↓
Frontend live globally on CDN, fresh HTTPS cert, in ~90 seconds
```

---

## Pull-request previews (free, automatic)

Open a PR → Actions runs the same workflow with `action: "upload"` → SWA spins up a **temporary preview URL**:

```
https://gentle-stone-1a2b3c4d-pr42.centralindia.5.azurestaticapps.net
```

Share it with your team for review. When the PR is closed/merged, the `close_pull_request` job in the workflow tears the preview down automatically. **All free.**

---

## Verifying it all wired up

After your first successful Action run:

```bash
# 1. Frontend renders
curl -I $FRONTEND_URL                 # → HTTP/2 200, security headers visible

# 2. /api proxy works (Option A)
curl $FRONTEND_URL/api/health         # → {"status":"ok","db":"ok"}

# 3. Open in browser, log in as platform admin
echo "Visit $FRONTEND_URL and sign in"
```

If `/api/health` returns the backend response **through the frontend URL**, the rewrite is working. If you see a 404 or HTML, double-check that you edited the `rewrite` line in `staticwebapp.config.json` to point at your real backend FQDN and pushed it.

---

## Final wiring cheat sheet

| Direction | Variable | Set on | When | Recommended value |
|---|---|---|---|---|
| Frontend → Backend | `REACT_APP_BACKEND_URL` | GitHub secret | Build time (GitHub Actions) | **empty string** (use SWA proxy) |
| Frontend → Backend | `rewrite` path | `staticwebapp.config.json` | Deploy time | Backend Container App FQDN |
| Backend → Frontend (CORS) | `FRONTEND_URL` | Container Apps env | Runtime | SWA URL (only needed if NOT using proxy) |

Two files, two GitHub secrets, one `git push` per change. That's the whole pipeline.

Want me to also wire up an analogous Actions workflow for the **backend** (auto-build → push to ACR → `az containerapp update` on every push)? Saves you the manual `docker build` step from earlier.
