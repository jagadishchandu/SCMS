# Cheapest Azure setup for SCMS — scale-to-zero with HTTPS

For a dynamic-traffic app where you want to pay **only when someone hits your site**, the right Azure service is **Azure Container Apps (Consumption plan)**. It:

- Scales **down to 0 replicas** when idle (you pay $0 for compute)
- Gives you **free HTTPS** on a `*.azurecontainerapps.io` URL out of the box
- Bills **per second** of CPU/memory + per request
- Has a **generous free tier**: 180,000 vCPU-seconds + 2,000,000 requests free/month
- For a small school/SaaS at low traffic: realistically **$0–8/month total** (ACR is the biggest fixed cost at ~$5/mo)

> **Even cheaper alternative for the frontend**: Azure Static Web Apps (free tier, HTTPS, 100 GB bandwidth, custom domain). Mentioned at the end — but the steps below use Container Apps for both since you have Docker images.

---

## Cost breakdown (typical school workload, < 50k requests/day)

| Component | Plan | Cost |
|---|---|---|
| **Azure Container Registry** | Basic | ~$0.167/day = **~$5/month** |
| **Container Apps — backend** | Consumption, scale 0→3, 0.5 vCPU / 1 GiB | **$0–4/month** (mostly inside free tier) |
| **Container Apps — frontend** | Consumption, scale 0→2, 0.25 vCPU / 0.5 GiB | **$0–2/month** (mostly inside free tier) |
| **Outbound bandwidth** | First 100 GB free | $0 |
| **HTTPS certificate** | Free, auto-renewed | $0 |
| **MongoDB** | Use Mongo Atlas free tier (M0) — not Cosmos | $0 |
| **Total** | | **~$5–11/month** |

To stay cheapest:
- Pick **Mongo Atlas free tier (M0)** instead of Cosmos for Mongo — Cosmos starts at ~$25/month.
- Pick **ACR Basic** ($5/mo) — Standard/Premium are 4–10× more.
- Set **minReplicas: 0** on both Container Apps so they sleep when nobody's using them. First request after sleep adds ~2-5 seconds of cold-start, which is fine for an internal SaaS.

---

## Prerequisites (one-time)

```bash
# Install Azure CLI
brew install azure-cli                       # macOS
# OR
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash   # Ubuntu/Debian

# Install Docker Desktop (if not already)
# https://docs.docker.com/desktop/

# Verify
az --version
docker --version
```

Login and pick a region close to your users:

```bash
az login
az account set --subscription "<your-subscription-id>"   # if you have multiple
```

---

## Step 1 — Define your variables (used by every command below)

Edit and paste this once into your shell — every later command reuses it:

```bash
# ---- EDIT THESE ----
export RG=scms-rg                       # resource group name
export LOC=centralindia                 # closest Azure region (e.g. eastus, westeurope, centralindia)
export ACR_NAME=scmsregistry$RANDOM     # must be globally unique, lowercase, 5-50 chars
export ENV_NAME=scms-env                # container apps environment name
export BACKEND_APP=scms-backend
export FRONTEND_APP=scms-frontend

# ---- Backend secrets (used at runtime) ----
export MONGO_URL="mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority"
export JWT_SECRET="$(openssl rand -hex 32)"
export ADMIN_EMAIL="admin@yourdomain.com"
export ADMIN_PASSWORD="ChangeMe@123"
```

Get a free Mongo Atlas cluster (M0) here in 5 minutes if you don't have one: <https://www.mongodb.com/atlas/database> — copy the connection string into `MONGO_URL` above.

---

## Step 2 — Create resource group + Azure Container Registry

```bash
# Resource group
az group create -n $RG -l $LOC

# Container Registry (Basic tier = cheapest at ~$5/mo)
az acr create -g $RG -n $ACR_NAME --sku Basic --admin-enabled true

# Login Docker to ACR
az acr login --name $ACR_NAME
```

Your registry is now reachable at `$ACR_NAME.azurecr.io`.

---

## Step 3 — Build and push the **backend** image

```bash
cd /app/backend

docker build -t $ACR_NAME.azurecr.io/scms-backend:latest .
docker push $ACR_NAME.azurecr.io/scms-backend:latest

# Verify it landed in ACR
az acr repository list -n $ACR_NAME -o table
```

---

## Step 4 — Create the Container Apps environment

This is the shared network that both apps will live in. **It's free** — you only pay for the apps inside it.

```bash
# Install the container-apps extension once
az extension add --name containerapp --upgrade

# Register the providers (one-time per subscription)
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# Create the environment
az containerapp env create \
  -n $ENV_NAME \
  -g $RG \
  -l $LOC
```

---

## Step 5 — Deploy the **backend** (with secrets, scale-to-zero, HTTPS)

```bash
az containerapp create \
  -n $BACKEND_APP \
  -g $RG \
  --environment $ENV_NAME \
  --image $ACR_NAME.azurecr.io/scms-backend:latest \
  --registry-server $ACR_NAME.azurecr.io \
  --target-port 8001 \
  --ingress external \
  --transport auto \
  --min-replicas 0 \
  --max-replicas 3 \
  --cpu 0.5 --memory 1.0Gi \
  --secrets \
      mongo-url="$MONGO_URL" \
      jwt-secret="$JWT_SECRET" \
      admin-password="$ADMIN_PASSWORD" \
  --env-vars \
      MONGO_URL=secretref:mongo-url \
      DB_NAME=scms_db \
      JWT_SECRET=secretref:jwt-secret \
      ADMIN_EMAIL="$ADMIN_EMAIL" \
      ADMIN_PASSWORD=secretref:admin-password \
      ENABLE_SUBSCRIPTION_GUARD=true \
      ENABLE_DIGEST_SCHEDULER=true \
      SUBSCRIPTION_PRICE_PER_CHILD_MONTHLY=30 \
      SUBSCRIPTION_PRICE_PER_CHILD_YEARLY=300 \
      SUBSCRIPTION_YEARLY_NUDGE_THRESHOLD=50
```

Key flags explained:

| Flag | What it does |
|---|---|
| `--ingress external` | Exposes the app publicly on HTTPS |
| `--target-port 8001` | Port your FastAPI listens on inside the container |
| `--min-replicas 0` | **Scale to zero when idle — this is what makes it cheap** |
| `--max-replicas 3` | Auto-scale up to 3 instances on traffic spikes |
| `--cpu 0.5 --memory 1.0Gi` | Per-instance size (smallest sensible for FastAPI + Mongo driver) |
| `--secrets` | Stored encrypted in the platform; never appear in logs |

Grab the public backend URL:

```bash
export BACKEND_URL="https://$(az containerapp show -n $BACKEND_APP -g $RG --query properties.configuration.ingress.fqdn -o tsv)"
echo "Backend: $BACKEND_URL"
curl $BACKEND_URL/api/health
```

Expected output: `{"status":"ok","db":"ok"}` (HTTPS, automatic cert, ready).

---

## Step 6 — Build and push the **frontend** image (with backend URL baked in)

This is **critical**: `REACT_APP_BACKEND_URL` is compiled into the JS bundle. You must rebuild whenever it changes.

```bash
cd /app/frontend

docker build \
  --build-arg REACT_APP_BACKEND_URL=$BACKEND_URL \
  -t $ACR_NAME.azurecr.io/scms-frontend:latest .

docker push $ACR_NAME.azurecr.io/scms-frontend:latest
```

---

## Step 7 — Deploy the **frontend**

```bash
az containerapp create \
  -n $FRONTEND_APP \
  -g $RG \
  --environment $ENV_NAME \
  --image $ACR_NAME.azurecr.io/scms-frontend:latest \
  --registry-server $ACR_NAME.azurecr.io \
  --target-port 3000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.25 --memory 0.5Gi
```

Grab the public frontend URL:

```bash
export FRONTEND_URL="https://$(az containerapp show -n $FRONTEND_APP -g $RG --query properties.configuration.ingress.fqdn -o tsv)"
echo "Frontend: $FRONTEND_URL"
```

---

## Step 8 — Tell the backend about the frontend (CORS)

Backend auto-adds `FRONTEND_URL` to its CORS allowlist — just set it and the app reloads:

```bash
az containerapp update \
  -n $BACKEND_APP -g $RG \
  --set-env-vars FRONTEND_URL=$FRONTEND_URL
```

---

## Step 9 — Verify the whole flow

```bash
# Backend health
curl $BACKEND_URL/api/health

# Frontend HTML loads
curl -I $FRONTEND_URL

# Open in browser
echo "Open $FRONTEND_URL and sign in as $ADMIN_EMAIL / $ADMIN_PASSWORD"
```

You now have:
- **`https://scms-frontend.<id>.<region>.azurecontainerapps.io`** — frontend with HTTPS
- **`https://scms-backend.<id>.<region>.azurecontainerapps.io`** — backend API with HTTPS

Both auto-renewing certificates, both scaling to zero when no one's using them.

---

## Connection parameters — what links the two apps

Exactly **two** values wire them together:

### 1. Backend → knows about Frontend (for CORS)

| Container | Env var | Value | When set | Purpose |
|---|---|---|---|---|
| backend | `FRONTEND_URL` | `https://scms-frontend.<id>.azurecontainerapps.io` | **runtime** | Auto-added to CORS allowlist by `server.py` |

### 2. Frontend → knows about Backend (for API calls)

| Container | Variable | Value | When set | Purpose |
|---|---|---|---|---|
| frontend | `REACT_APP_BACKEND_URL` | `https://scms-backend.<id>.azurecontainerapps.io` | **build-time** (Docker `--build-arg`) | Baked into the JS bundle; React calls this URL directly |

That's it. Everything else (`MONGO_URL`, `JWT_SECRET`, `ADMIN_*`, pricing knobs) is backend-only and doesn't affect the frontend.

> ⚠️ **Important**: if you ever change `BACKEND_URL`, you must **rebuild and redeploy** the frontend image. The URL cannot be changed at runtime.

---

## Updating after code changes

Both apps support zero-downtime rolling updates. The flow:

```bash
# Code change in backend
cd /app/backend
docker build -t $ACR_NAME.azurecr.io/scms-backend:latest .
docker push $ACR_NAME.azurecr.io/scms-backend:latest
az containerapp update -n $BACKEND_APP -g $RG \
  --image $ACR_NAME.azurecr.io/scms-backend:latest

# Code change in frontend
cd /app/frontend
docker build --build-arg REACT_APP_BACKEND_URL=$BACKEND_URL \
  -t $ACR_NAME.azurecr.io/scms-frontend:latest .
docker push $ACR_NAME.azurecr.io/scms-frontend:latest
az containerapp update -n $FRONTEND_APP -g $RG \
  --image $ACR_NAME.azurecr.io/scms-frontend:latest
```

---

## Optional: custom domain (`app.yourdomain.com`)

```bash
# Add the custom domain (the CLI will print a TXT record to add at your DNS provider)
az containerapp hostname add -n $FRONTEND_APP -g $RG --hostname app.yourdomain.com

# Bind a free, auto-renewing managed certificate
az containerapp hostname bind -n $FRONTEND_APP -g $RG \
  --hostname app.yourdomain.com --environment $ENV_NAME --validation-method CNAME

# Then update the backend's CORS allowlist
az containerapp update -n $BACKEND_APP -g $RG \
  --set-env-vars FRONTEND_URL=https://app.yourdomain.com

# And rebuild frontend with the new backend custom domain too
az containerapp hostname add  -n $BACKEND_APP -g $RG --hostname api.yourdomain.com
az containerapp hostname bind -n $BACKEND_APP -g $RG \
  --hostname api.yourdomain.com --environment $ENV_NAME --validation-method CNAME

docker build --build-arg REACT_APP_BACKEND_URL=https://api.yourdomain.com \
  -t $ACR_NAME.azurecr.io/scms-frontend:latest /app/frontend
docker push $ACR_NAME.azurecr.io/scms-frontend:latest
az containerapp update -n $FRONTEND_APP -g $RG \
  --image $ACR_NAME.azurecr.io/scms-frontend:latest
```

Both `app.yourdomain.com` and `api.yourdomain.com` are now HTTPS-only, auto-renewed, $0 extra.

---

## Even cheaper: Azure Static Web Apps for the frontend

If you want to drop the frontend cost to **literally $0 forever** (free tier covers 100 GB/month bandwidth, free HTTPS, custom domain):

1. Skip building the frontend Docker image.
2. Push your `/app/frontend` source to GitHub.
3. Run `az staticwebapp create` pointing at your repo — it builds the React app and serves it on `https://<name>.azurestaticapps.net` with HTTPS + global CDN automatically.
4. Set `REACT_APP_BACKEND_URL` as a build env var in the Static Web Apps config.

Backend stays on Container Apps. Total cost drops to ~$5–8/month (ACR + backend compute only).

If you want the steps for that route too, just say the word.
