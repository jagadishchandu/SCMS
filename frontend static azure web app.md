# Frontend on Azure Static Web Apps — Free Tier, $0/month

This drops your frontend cost to literally zero forever. Backend stays on Container Apps. **Total stack cost: ~$5–8/month** (just ACR + low backend traffic).

## What you get on the free tier

| Feature | Free tier |
|---|---|
| Bandwidth | 100 GB/month |
| Storage | 0.5 GB |
| Custom domain | ✅ free |
| HTTPS / SSL | ✅ auto, free, auto-renewed |
| Global CDN | ✅ built-in |
| Staging environments | 3 free |
| Build minutes | Unlimited (uses GitHub Actions free tier: 2000 min/month for private repos, unlimited for public) |
| Auth providers | GitHub, Azure AD, Twitter — built-in |

## How it works

You no longer build a Docker image for the frontend. Instead, Azure Static Web Apps (SWA) connects to your GitHub repo, runs `yarn build`, and serves the resulting `/build` folder from a global CDN.

```
Browser → https://app.yourdomain.com (CDN, free SSL)
            ↓
            /              → static React files (served from CDN edge)
            /api/* (optional) → proxied to Container Apps backend
```

---

## Step 1 — Push code to GitHub (one-time)

Static Web Apps needs a GitHub repo to wire up CI/CD.

If your repo isn't on GitHub yet, use the "Save to GitHub" button in your Emergent chat input, or:

```bash
cd /app
git remote add origin https://github.com/<your-username>/scms.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Reuse the variables from before

```bash
export RG=scms-rg
export LOC=centralindia                  # SWA is auto-replicated globally; pick any region
export SWA_NAME=scms-frontend-swa
export GITHUB_REPO="https://github.com/<your-username>/scms"
export GITHUB_BRANCH="main"

# Your existing backend URL from Container Apps
export BACKEND_URL="https://$(az containerapp show -n scms-backend -g $RG --query properties.configuration.ingress.fqdn -o tsv)"
echo "Backend: $BACKEND_URL"
```

---

## Step 3 — Create the Static Web App

```bash
az extension add --name staticwebapp --upgrade

az staticwebapp create \
  --name $SWA_NAME \
  --resource-group $RG \
  --location $LOC \
  --source $GITHUB_REPO \
  --branch $GITHUB_BRANCH \
  --app-location "/frontend" \
  --output-location "build" \
  --login-with-github
```

What each flag does:

| Flag | Meaning |
|---|---|
| `--source` | Your GitHub repo URL |
| `--branch` | Branch to deploy from (`main`) |
| `--app-location` | Where your frontend source lives in the repo (`/frontend`) |
| `--output-location` | Where `yarn build` writes the bundle (`build` for CRA) |
| `--login-with-github` | One-time browser popup to authorize SWA to read your repo |

When the command runs:

1. A browser window opens → you authorize Azure to talk to GitHub.
2. SWA creates a **GitHub Actions workflow** in your repo at `.github/workflows/azure-static-web-apps-<random>.yml`.
3. The workflow runs immediately, builds your React app, deploys it.

Grab the public URL:

```bash
export FRONTEND_URL="https://$(az staticwebapp show -n $SWA_NAME -g $RG --query defaultHostname -o tsv)"
echo "Frontend: $FRONTEND_URL"
# e.g. https://gentle-stone-1a2b3c4d.5.azurestaticapps.net
```

---

## Step 4 — Tell SWA where the backend lives (build-time env var)

This is the **critical** step — `REACT_APP_BACKEND_URL` must be set on the Azure side **before** the next build runs, so the React bundle picks it up:

```bash
az staticwebapp appsettings set \
  -n $SWA_NAME \
  --setting-names REACT_APP_BACKEND_URL=$BACKEND_URL
```

> 💡 SWA also auto-injects this into the GitHub Actions build env, so `yarn build` sees it.

---

## Step 5 — Edit the GitHub Actions workflow (one-time)

Open the file SWA just created in your repo:

```
.github/workflows/azure-static-web-apps-<random>.yml
```

Find the `Build And Deploy` step and add the env block so `REACT_APP_BACKEND_URL` is passed into the build:

```yaml
      - name: Build And Deploy
        id: builddeploy
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN_... }}
          repo_token: ${{ secrets.GITHUB_TOKEN }}
          action: "upload"
          app_location: "/frontend"
          output_location: "build"
        env:                                                # 👈 add this block
          REACT_APP_BACKEND_URL: ${{ secrets.REACT_APP_BACKEND_URL }}
```

Then add the secret in GitHub:

1. Go to **your repo → Settings → Secrets and variables → Actions → New repository secret**
2. Name: `REACT_APP_BACKEND_URL`
3. Value: paste the backend URL from Step 2 (e.g. `https://scms-backend.gentle-stone-1a2b3c4d.eastus.azurecontainerapps.io`)
4. Click "Add secret"

Commit & push the workflow change:

```bash
cd /app
git add .github/workflows/
git commit -m "Inject backend URL into SWA build"
git push
```

The push triggers a new build. Watch it in your repo's **Actions** tab — takes ~2 minutes.

---

## Step 6 — Tell the backend about the new frontend URL (CORS)

```bash
az containerapp update \
  -n scms-backend -g $RG \
  --set-env-vars FRONTEND_URL=$FRONTEND_URL
```

Backend reloads automatically and now allows your new SWA origin through CORS.

---

## Step 7 — Verify

```bash
# Frontend renders the React shell
curl -I $FRONTEND_URL

# Backend stays live, scaled to zero except on demand
curl $BACKEND_URL/api/health

# Open in browser
echo "Open $FRONTEND_URL"
```

You should land on the SCMS login page over HTTPS. Sign in as `$ADMIN_EMAIL` / `$ADMIN_PASSWORD`.

---

## Step 8 (optional) — Custom domain for the frontend

Free, automatic HTTPS:

```bash
# Add custom hostname
az staticwebapp hostname set \
  -n $SWA_NAME -g $RG \
  --hostname app.yourdomain.com

# CLI prints a CNAME record to add at your DNS provider.
# Add it, then Azure auto-validates and issues a free cert (5-10 minutes).

# After it's live, point the backend's CORS at it
az containerapp update -n scms-backend -g $RG \
  --set-env-vars FRONTEND_URL=https://app.yourdomain.com

# And update the GitHub secret so future builds use the clean URL —
# only matters if you ALSO custom-domain the backend
```

---

## Optional: route /api/* through SWA's domain (no CORS at all)

If you want a single origin (`https://app.yourdomain.com/api/*` proxied to your backend), add a `staticwebapp.config.json` file in `/app/frontend/`:

```json
{
  "routes": [
    {
      "route": "/api/*",
      "rewrite": "https://scms-backend.<id>.azurecontainerapps.io/api/*"
    }
  ],
  "navigationFallback": {
    "rewrite": "/index.html",
    "exclude": ["/static/*", "/*.{png,jpg,jpeg,svg,gif,ico}"]
  }
}
```

Commit + push → SWA picks it up automatically. Now your React app can use a **relative** `/api` path, and you can set `REACT_APP_BACKEND_URL` to empty:

```bash
# Empty string → React uses relative /api
az staticwebapp appsettings set -n $SWA_NAME --setting-names REACT_APP_BACKEND_URL=""
```

CORS becomes irrelevant because everything is one origin.

---

## Day-to-day workflow

| Change you make | What happens |
|---|---|
| Push code to `main` | GitHub Actions auto-builds + deploys the frontend in ~2 min |
| Push code to a feature branch | SWA spins up a **free preview environment** at `https://<branch>.<id>.azurestaticapps.net` (auto-deleted when PR closes) |
| Change `REACT_APP_BACKEND_URL` | Update the GitHub secret → push any commit → rebuilds with new URL |
| Update backend Docker image | Same `docker build/push + az containerapp update` as before |

No more frontend rebuilds locally. No more pushing Docker images for the frontend.

---

## Connection parameters cheat sheet (with SWA)

| Direction | Where it's set | Variable | When applied |
|---|---|---|---|
| Frontend → Backend | SWA app settings + GitHub secret | `REACT_APP_BACKEND_URL` | **GitHub Actions build time** |
| Backend → Frontend (CORS) | Container Apps env | `FRONTEND_URL` | **Runtime** |

That's still the only wiring you need. SWA replaces the frontend Container App; everything else is unchanged.

---

## Final cost (typical small school)

| Component | Plan | Monthly |
|---|---|---|
| Azure Container Registry | Basic | $5.00 |
| Container Apps — backend | Consumption, scale to 0 | $0–4 |
| Azure Static Web Apps — frontend | Free | **$0** |
| Mongo Atlas | M0 free tier | **$0** |
| Bandwidth | First 100 GB free | $0 |
| Custom HTTPS certs (both) | Built-in | $0 |
| **Total** | | **~$5–9/month** |

The only way to go cheaper would be to drop ACR by using Docker Hub (free for public images) or GHCR (free for public images), saving another $5/month. Just be aware that means your images are public — fine if you don't bake secrets into them (you shouldn't, and the SCMS images don't).

Want me to also generate the `staticwebapp.config.json` and a sample GitHub Actions workflow file pre-filled with your settings, so you can commit them directly?
