Good question — there are two distinct things at play here, and people often mix them up:

1. **Azure Container Registry (ACR)** = where your **images are stored** (like Docker Hub). It does not run containers.
2. **Azure Container Apps / App Service / AKS / Container Instances** = where the images actually **run** and get a public URL.

So your "backend URL" and "frontend URL" come from the **runtime service**, not from ACR.

---

## Step 1 — Push images to ACR (no URLs assigned yet)

```bash
# Login
az login
az acr login --name <your-acr-name>          # e.g. scmsregistry

# Tag for ACR
docker tag scms-backend:latest  <your-acr-name>.azurecr.io/scms-backend:latest
docker tag scms-frontend:latest <your-acr-name>.azurecr.io/scms-frontend:latest

# Push
docker push <your-acr-name>.azurecr.io/scms-backend:latest
docker push <your-acr-name>.azurecr.io/scms-frontend:latest
```

After this step, ACR holds the images at:
```
scmsregistry.azurecr.io/scms-backend:latest
scmsregistry.azurecr.io/scms-frontend:latest
```
…but **nothing is running yet**.

---

## Step 2 — Run the images on an Azure compute service

The URL pattern depends on which service you pick. Here are the three most common options:

### Option A — **Azure Container Apps** (recommended, simplest for two services)

URLs look like:
```
https://scms-backend.<random-id>.<region>.azurecontainerapps.io
https://scms-frontend.<random-id>.<region>.azurecontainerapps.io
```

Example (real format):
```
https://scms-backend.gentlebush-1a2b3c4d.eastus.azurecontainerapps.io
https://scms-frontend.gentlebush-1a2b3c4d.eastus.azurecontainerapps.io
```

The `gentlebush-1a2b3c4d` part is unique to your "Container Apps Environment" and is assigned when you create it.

**Build & deploy in this order so the URLs line up:**

```bash
RG=scms-rg
LOC=eastus
ENV=scms-env
ACR=scmsregistry

# 1) Create resource group + environment
az group create -n $RG -l $LOC
az containerapp env create -n $ENV -g $RG -l $LOC

# 2) Deploy backend FIRST (we need its URL before building the frontend)
az containerapp create \
  -n scms-backend -g $RG --environment $ENV \
  --image $ACR.azurecr.io/scms-backend:latest \
  --registry-server $ACR.azurecr.io \
  --target-port 8001 --ingress external \
  --env-vars \
    MONGO_URL=secretref:mongo-url \
    DB_NAME=scms_db \
    JWT_SECRET=secretref:jwt-secret \
    ADMIN_EMAIL=admin@yourdomain.com \
    ADMIN_PASSWORD=secretref:admin-password \
    ENABLE_SUBSCRIPTION_GUARD=true \
  --secrets \
    mongo-url="mongodb+srv://..." \
    jwt-secret="$(openssl rand -hex 32)" \
    admin-password="ChangeMe@123"

# 3) Grab the backend's public URL
BACKEND_URL=$(az containerapp show -n scms-backend -g $RG --query properties.configuration.ingress.fqdn -o tsv)
BACKEND_URL="https://$BACKEND_URL"
echo "Backend at: $BACKEND_URL"
# e.g. https://scms-backend.gentlebush-1a2b3c4d.eastus.azurecontainerapps.io

# 4) Rebuild frontend image with the real backend URL baked in, push, then deploy
docker build \
  --build-arg REACT_APP_BACKEND_URL=$BACKEND_URL \
  -t $ACR.azurecr.io/scms-frontend:latest /app/frontend
docker push $ACR.azurecr.io/scms-frontend:latest

az containerapp create \
  -n scms-frontend -g $RG --environment $ENV \
  --image $ACR.azurecr.io/scms-frontend:latest \
  --registry-server $ACR.azurecr.io \
  --target-port 3000 --ingress external

# 5) Grab the frontend URL and feed it back to the backend so CORS allows it
FRONTEND_URL=$(az containerapp show -n scms-frontend -g $RG --query properties.configuration.ingress.fqdn -o tsv)
FRONTEND_URL="https://$FRONTEND_URL"
echo "Frontend at: $FRONTEND_URL"

az containerapp update -n scms-backend -g $RG \
  --set-env-vars FRONTEND_URL=$FRONTEND_URL
```

> **Why the order matters**: `REACT_APP_BACKEND_URL` is baked into the React bundle at build time, so you need the backend's URL **before** you build the frontend image. And `FRONTEND_URL` on the backend just controls CORS, so it can be set after.

### Option B — **Azure App Service for Containers**

URLs look like:
```
https://scms-backend.azurewebsites.net
https://scms-frontend.azurewebsites.net
```
(The name you pick must be globally unique across all of Azure.)

### Option C — **Azure Container Instances (ACI)**

URLs look like:
```
http://scms-backend.<region>.azurecontainer.io:8001
http://scms-frontend.<region>.azurecontainer.io:3000
```
You pick the DNS label when you create it. Not recommended for production (no HTTPS unless you put a Front Door / App Gateway in front), but cheapest for testing.

---

## Step 3 — Pin a custom domain (the URLs you actually want)

The auto-generated Azure URLs are ugly. Most teams add a custom domain:

| Service | What you point | Result |
|---|---|---|
| `app.yourdomain.com` | CNAME → frontend container's azure URL | Frontend public URL |
| `api.yourdomain.com` | CNAME → backend container's azure URL | Backend public URL |

Then **rebuild the frontend image** one more time with the clean URL:
```bash
docker build --build-arg REACT_APP_BACKEND_URL=https://api.yourdomain.com \
  -t $ACR.azurecr.io/scms-frontend:latest /app/frontend
docker push $ACR.azurecr.io/scms-frontend:latest
az containerapp update -n scms-frontend -g $RG \
  --image $ACR.azurecr.io/scms-frontend:latest
az containerapp update -n scms-backend -g $RG \
  --set-env-vars FRONTEND_URL=https://app.yourdomain.com
```

---

## TL;DR

- **ACR only stores images.** It does not give your app a URL.
- **The URLs come from whatever runs the container**: Container Apps → `*.azurecontainerapps.io`, App Service → `*.azurewebsites.net`, ACI → `*.azurecontainer.io`.
- **Order of operations**: deploy backend → grab its URL → build frontend with that URL baked in → deploy frontend → grab its URL → set `FRONTEND_URL` on backend for CORS.
- **Custom domains** (`api.yourdomain.com`, `app.yourdomain.com`) hide the Azure auto-URLs and make rebuilds painless.

Tell me which Azure service you want to use (Container Apps is my recommendation for two-service apps) and I can generate the exact deploy script for your setup.
