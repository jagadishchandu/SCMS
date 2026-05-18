BackednURL : https://scms-backend.ambitiouscliff-7b936366.southindia.azurecontainerapps.io
# SCMS — Full manual deployment via Azure Portal

Complete step-by-step. No CLI, no scripts, just clicks. Build images locally, push to ACR, deploy two Container Apps with HTTPS, and wire them together.

> **Estimated time**: 35–45 minutes the first time

---

## Phase 0 — Prerequisites (one-time)

| What | Action |
|---|---|
| Azure account | https://azure.microsoft.com/free (₹13,300 / $200 free credit for 30 days) |
| Docker Desktop | https://www.docker.com/products/docker-desktop — must be running |
| MongoDB Atlas | https://www.mongodb.com/cloud/atlas/register (free M0 cluster — keep the connection string handy) |

Once Docker is running, open a terminal and test:

```bash
docker --version
```

---

## Phase 1 — Create the Resource Group

This is the "folder" that holds everything else.

1. Go to **https://portal.azure.com**
2. Top search bar → **Resource groups** → click it
3. Click **+ Create**
4. Fill in:
   - **Subscription**: (your subscription)
   - **Resource group name**: `scms-rg`
   - **Region**: `Central India` (or whichever is closest to your users)
5. Click **Review + create** → **Create**
6. Wait ~30 seconds for the green "Deployment succeeded" notification

---

## Phase 2 — Create Azure Container Registry (ACR)

This is where your Docker images will live.

1. Top search bar → **Container registries** → click it
2. Click **+ Create**
3. Fill in the **Basics** tab:
   - **Subscription**: (your subscription)
   - **Resource group**: `scms-rg`
   - **Registry name**: `scmsregistry<your-initials>` (must be globally unique, lowercase letters/digits only, 5–50 chars — e.g. `scmsregistryjc`)
   - **Location**: `Central India`
   - **Pricing plan**: **Basic** (cheapest at ~$5/month, 10 GB storage)
4. Click **Review + create** → **Create**
5. Wait ~1 minute for deployment

### Enable admin access (needed for `docker push` from your laptop)

1. Once created, click **Go to resource**
2. Left menu → under **Settings**, click **Access keys**
3. Toggle **Admin user** → **Enabled**
4. **Copy and save these three values somewhere** — you'll need them in Phase 3:
   - **Login server** (e.g. `scmsregistryjc.azurecr.io`) scmsregistery.azurecr.io
   - **Username** (same as your registry name)  scmsregistery
   - **password** (the long one under "password" — click the copy icon)  Eyino0xz6L5jss7GCLoNcIxCi5Fwwk1jlE9yAtRHfragyFDek6M1JQQJ99CEAC77bzfEqg7NAAACAZCR61yl
   - 3ws7F1A4EDNhczt4Pq5w1QXu19X7kdJvuKFW8xuRrrZGbfHICEBjJQQJ99CEAC77bzfEqg7NAAACAZCRWt29

---

## Phase 3 — Build & Push Images from Local

Open a terminal on your laptop. Replace `<LOGIN-SERVER>`, `<USERNAME>`, `<PASSWORD>` with the values from Phase 2.

### 3.1 Login Docker to ACR

```bash
docker login <LOGIN-SERVER> -u <USERNAME> -p <PASSWORD>
```

Example:
```bash
docker login scmsregistryjc.azurecr.io -u scmsregistryjc -p abc123longpassword==
```

You should see `Login Succeeded`.

### 3.2 Build & push the backend image

```bash
cd /app/backend

docker build -t <LOGIN-SERVER>/scms-backend:latest .
docker push <LOGIN-SERVER>/scms-backend:latest
```

Wait for the push to finish (~2–5 min depending on your upload speed).

### 3.3 Build & push the frontend image (FIRST PASS — placeholder URL)

We don't know the backend's public URL yet, so build with a placeholder. We'll rebuild after Phase 6.

```bash
cd /app/frontend

docker build \
  --build-arg REACT_APP_BACKEND_URL=https://placeholder \
  -t <LOGIN-SERVER>/scms-frontend:latest .

docker push <LOGIN-SERVER>/scms-frontend:latest
```

### 3.4 Verify in the portal

1. Portal → your container registry → left menu → **Services → Repositories**
2. You should see **two repositories**:
   - `scms-backend`
   - `scms-frontend`

✅ Images uploaded.

---

## Phase 4 — Create the Container Apps Environment

This is the shared network/runtime for both apps. **It's free** — you only pay for the apps inside it.

1. Top search bar → **Container Apps** → click it
2. Click **+ Create** → **Container App**
3. Fill in the **Basics** tab:
   - **Subscription**: (your subscription)
   - **Resource group**: `scms-rg`
   - **Container app name**: `scms-backend` (we're starting with the backend)
   - **Deployment source**: **Container image**
   - **Region**: `Central India`
   - **Container Apps Environment**: click **Create new**
     - **Environment name**: `scms-env`
     - **Zone redundancy**: **Disabled** (cheaper)
     - Click **Create**

4. Click **Next: Container >** — don't fill anything yet, we'll do that in Phase 5.

---

## Phase 5 — Deploy the Backend Container App

(Continuing from Phase 4 — you should be on the "Container" tab of the Create Container App wizard.)

### 5.1 Container tab

1. **Uncheck "Use quickstart image"**
2. Fill in:
   - **Name**: `scms-backend`
   - **Image source**: **Azure Container Registry**
   - **Registry**: select your `scmsregistryjc` registry from the dropdown
   - **Image**: `scms-backend`
   - **Image tag**: `latest`
   - **CPU and Memory**: `0.5 CPU cores, 1 Gi memory` (cheapest sensible size)

3. Scroll down to **Environment variables** — click **+ Add** for each row below. **CRITICAL: type each one exactly as shown.**

   | Name | Source | Value |
   |---|---|---|
   | `MONGO_URL` | **Reference a secret** | _(we'll add secrets in step 5.2 — for now type a placeholder value and you'll edit it later)_ |
   | `DB_NAME` | Manual entry | `scms_db` |
   | `JWT_SECRET` | **Reference a secret** | _(placeholder for now)_ |
   | `ADMIN_EMAIL` | Manual entry | `admin@yourdomain.com` |
   | `ADMIN_PASSWORD` | **Reference a secret** | _(placeholder for now)_ |
   | `ENABLE_SUBSCRIPTION_GUARD` | Manual entry | `true` |
   | `ENABLE_DIGEST_SCHEDULER` | Manual entry | `true` |
   | `SUBSCRIPTION_PRICE_PER_CHILD_MONTHLY` | Manual entry | `30` |
   | `SUBSCRIPTION_PRICE_PER_CHILD_YEARLY` | Manual entry | `300` |
   | `SUBSCRIPTION_YEARLY_NUDGE_THRESHOLD` | Manual entry | `50` |
   | `FRONTEND_URL` | Manual entry | _(leave empty for now — we'll fill it in Phase 8)_ |

   > It's fine to leave the secret-ref values blank in the wizard. We'll add the secrets and update the references right after creation.

### 5.2 Ingress tab — THIS IS HOW HTTPS GETS ENABLED

1. Click **Next: Ingress >**
2. Toggle **Ingress** → **Enabled**
3. Fill in:
   - **Ingress traffic**: **Accepting traffic from anywhere** (this gives you the public internet URL with HTTPS)
   - **Ingress type**: **HTTP**
   - **Client certificate mode**: Ignore
   - **Transport**: **Auto**
   - **Insecure connections**: **Disabled** (forces HTTPS)
   - **Target port**: `8001` ⚠️ (this is the port your FastAPI listens on inside the container)

4. Click **Review + create** → **Create**
5. Wait ~2 minutes for "Deployment succeeded"
6. Click **Go to resource**

### 5.3 Add the real secrets

Now that the app exists, add the real secret values:

1. Left menu of the container app → under **Settings**, click **Secrets**
2. Click **+ Add** for each:
   | Secret name | Value |
   |---|---|
   | `mongo-url` | _(your Mongo Atlas connection string)_ |
   | `jwt-secret` | _(a random 64-char string — generate at https://www.random.org/strings)_ |
   | `admin-password` | `ChangeMe@123` (or whatever you want as the platform admin password) |
3. Click **Save**

### 5.4 Wire the env vars to the secrets

1. Left menu → under **Application**, click **Containers**
2. Click **Edit and deploy** at the top
3. In the row that appears, click your container name (`scms-backend`)
4. Scroll to **Environment variables**, and **edit** each of these three:
   - `MONGO_URL` → change Source to **Reference a secret** → pick `mongo-url`
   - `JWT_SECRET` → change Source to **Reference a secret** → pick `jwt-secret`
   - `ADMIN_PASSWORD` → change Source to **Reference a secret** → pick `admin-password`
5. Click **Save**
6. Back on the "Edit and deploy" page → click **Create** (this creates a new revision with the new env wiring)
7. Wait ~1 minute. Watch the **Revisions** tab — the new revision should show "Running, 100%".

### 5.5 Set scale-to-zero (cost saver)

1. Left menu → under **Application**, click **Scale and replicas**
2. Click **Edit and deploy**
3. Set **Min replicas** to `0`
4. Set **Max replicas** to `3`
5. Click **Save** → **Create**

### 5.6 Grab the backend URL

1. Left menu → click **Overview**
2. On the right side, find **Application Url** — looks like:
   ```
   https://scms-backend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io
   ```
3. **COPY THIS ENTIRE URL** — you'll need it twice in the next phases.

### 5.7 Verify backend is healthy

Open this in your browser (replace with your URL):

```
https://scms-backend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io/api/health
```

You should see:
```json
{"status":"ok","db":"ok"}
```

If you see `{"status":"degraded","db":"..."}`, your `MONGO_URL` secret is wrong — go fix it in **Secrets** and create a new revision.

✅ Backend is live on HTTPS.

---

## Phase 6 — Rebuild Frontend with the REAL Backend URL

The backend URL must be baked into the React bundle. Now we know it.

Back in your terminal:

```bash
cd /app/frontend

docker build \
  --build-arg REACT_APP_BACKEND_URL=https://scms-backend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io \
  -t <LOGIN-SERVER>/scms-frontend:latest .

docker push <LOGIN-SERVER>/scms-frontend:latest
```

> 🔑 **Use the EXACT URL from Phase 5.6**, including the `https://` prefix, no trailing slash.

---

## Phase 7 — Deploy the Frontend Container App

1. Portal → top search → **Container Apps** → click **+ Create** → **Container App**

2. **Basics tab**:
   - **Resource group**: `scms-rg`
   - **Container app name**: `scms-frontend`
   - **Deployment source**: **Container image**
   - **Region**: `Central India`
   - **Container Apps Environment**: select the existing `scms-env` from the dropdown (don't create a new one!)

3. Click **Next: Container >**
   - **Uncheck "Use quickstart image"**
   - **Name**: `scms-frontend`
   - **Image source**: **Azure Container Registry**
   - **Registry**: select your registry
   - **Image**: `scms-frontend`
   - **Image tag**: `latest`
   - **CPU/Memory**: `0.25 CPU cores, 0.5 Gi memory`
   - **Environment variables**: none required

4. Click **Next: Ingress >**
   - Toggle **Ingress** → **Enabled**
   - **Ingress traffic**: **Accepting traffic from anywhere**
   - **Ingress type**: **HTTP**
   - **Insecure connections**: **Disabled**
   - **Target port**: `3000` ⚠️ (nginx inside the frontend container listens on 3000)

5. Click **Review + create** → **Create**. Wait ~2 minutes.

6. Click **Go to resource** → left menu → **Scale and replicas** → **Edit and deploy** → set **Min replicas = 0**, **Max replicas = 2** → **Save** → **Create**

7. Click **Overview** → copy the **Application Url** — e.g.:
   ```
   https://scms-frontend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io
   ```

---

## Phase 8 — Connect Backend ↔ Frontend (CORS)

The backend needs to know the frontend's URL to allow it through CORS.

1. Portal → **Container Apps** → click **`scms-backend`**
2. Left menu → under **Application**, click **Containers**
3. Click **Edit and deploy** at the top
4. Click your container name (`scms-backend`)
5. Scroll to **Environment variables** → find `FRONTEND_URL` row → set the value to your **frontend URL from Phase 7** (full URL with `https://`, no trailing slash). If there's no `FRONTEND_URL` row, click **+ Add** to create one.
6. Click **Save**
7. Click **Create** to deploy a new revision
8. Wait ~30 seconds for the new revision to go live

---

## Phase 9 — Test End-to-End

1. Open the **frontend URL** from Phase 7 in your browser. You should see the SCMS login screen.
2. Sign in:
   - Email: `admin@yourdomain.com` (the `ADMIN_EMAIL` you set in Phase 5.1)
   - Password: the `admin-password` secret value from Phase 5.3
3. You should land on the Platform Console.
4. Navigate around — login, dashboard, subscriptions tab. Every API call should succeed.

If the login page loads but login itself fails with a CORS error:

- Go back to Phase 8 and double-check `FRONTEND_URL` is set correctly on the backend (no typos, no trailing slash, includes `https://`).
- Open the backend's **Log stream** (left menu → **Monitoring → Log stream**) — you'll see the exact CORS rejection if it's that.

---

## Phase 10 (Optional) — Custom Domain with Free SSL

If you want `https://app.yourdomain.com` and `https://api.yourdomain.com` instead of the Azure URLs:

### 10.1 Frontend custom domain

1. Portal → `scms-frontend` → left menu → under **Settings**, click **Custom domains**
2. Click **+ Add custom domain**
3. **Hostname**: `app.yourdomain.com`
4. Azure shows you a **CNAME** and a **TXT** record to add at your DNS provider (GoDaddy, Namecheap, Cloudflare, etc.). Add them.
5. Click **Validate** → once green, click **Add**
6. Under **Managed certificate**, click **Add certificate** → **Bind**. Azure issues a free auto-renewing cert in ~5–10 minutes.

### 10.2 Backend custom domain

Same flow on `scms-backend` with hostname `api.yourdomain.com`.

### 10.3 Update wiring for the custom domains

You changed both public URLs, so:

1. **Rebuild frontend** with the new backend URL:
   ```bash
   cd /app/frontend
   docker build --build-arg REACT_APP_BACKEND_URL=https://api.yourdomain.com \
     -t <LOGIN-SERVER>/scms-frontend:latest .
   docker push <LOGIN-SERVER>/scms-frontend:latest
   ```

2. Portal → `scms-frontend` → **Containers** → **Edit and deploy** → click container row → in **Image source**, **Refresh** to pull the new `:latest`, then **Save** → **Create** (new revision).

3. Portal → `scms-backend` → **Containers** → **Edit and deploy** → update `FRONTEND_URL` env var to `https://app.yourdomain.com` → **Save** → **Create**.

---

## Where everything lives — quick reference

| What | Where in the portal | What you do there |
|---|---|---|
| Resource group | Search bar → "Resource groups" → `scms-rg` | Container for everything |
| ACR | Search bar → "Container registries" → your registry | Holds Docker images, gives push credentials |
| Container App Environment | Search bar → "Container Apps Environments" → `scms-env` | Shared network (free) |
| Backend app | Search bar → "Container Apps" → `scms-backend` | API container |
| Backend secrets | Backend app → Settings → Secrets | `MONGO_URL`, `JWT_SECRET`, `ADMIN_PASSWORD` |
| Backend env vars | Backend app → Containers → Edit and deploy | `FRONTEND_URL`, pricing knobs, etc. |
| Frontend app | Search bar → "Container Apps" → `scms-frontend` | React + nginx container |
| Logs | Either app → Monitoring → Log stream | Live tail of container output |
| Scale settings | Either app → Application → Scale and replicas | Min/max replicas (set min=0 for cost) |
| Custom domain | Either app → Settings → Custom domains | Add `app.` / `api.` + free SSL |

---

## When you push new code (the loop you'll run forever)

### Backend change
```bash
cd /app/backend
docker build -t <LOGIN-SERVER>/scms-backend:latest .
docker push <LOGIN-SERVER>/scms-backend:latest
```
Then in the portal: **scms-backend → Containers → Edit and deploy → Save → Create** (this pulls the latest image and rolls a new revision with zero downtime).

### Frontend change
```bash
cd /app/frontend
docker build --build-arg REACT_APP_BACKEND_URL=<backend-url> \
  -t <LOGIN-SERVER>/scms-frontend:latest .
docker push <LOGIN-SERVER>/scms-frontend:latest
```
Same redeploy flow on `scms-frontend`.

---

## Connection wiring at a glance

```
┌───────────────────────────────────────────────────────────┐
│  Browser (user)                                            │
└───────────────────────────────────────────────────────────┘
        │
        │  HTTPS
        ▼
┌───────────────────────────────────────────────────────────┐
│  scms-frontend (Container App)                             │
│  https://scms-frontend.<id>.azurecontainerapps.io          │
│                                                             │
│  React bundle hard-codes REACT_APP_BACKEND_URL at build:   │
│    → https://scms-backend.<id>.azurecontainerapps.io       │
└───────────────────────────────────────────────────────────┘
        │
        │  HTTPS API calls (CORS allowed because backend's
        │  FRONTEND_URL env var matches this origin)
        ▼
┌───────────────────────────────────────────────────────────┐
│  scms-backend (Container App, port 8001)                   │
│  https://scms-backend.<id>.azurecontainerapps.io           │
│                                                             │
│  Env: MONGO_URL → Mongo Atlas                              │
│       FRONTEND_URL = (the frontend's URL)                   │
│       JWT_SECRET, ADMIN_PASSWORD = (from Secrets)           │
└───────────────────────────────────────────────────────────┘
        │
        │  Mongo connection (TLS auto-enabled by code)
        ▼
   Mongo Atlas free tier
```

**Two URLs, two places to put them:**

| Direction | Variable | Where you put it | Phase |
|---|---|---|---|
| Frontend → Backend | `REACT_APP_BACKEND_URL` | `docker build --build-arg ...` on your laptop | Phase 6 |
| Backend → Frontend | `FRONTEND_URL` | Backend Container App → Containers → Env var | Phase 8 |

Get those two right and the app is live on HTTPS. Get either wrong and you'll see CORS errors or the login network call hitting `https://placeholder` (= you forgot to rebuild the frontend after Phase 5).

You're done — frontend is public on HTTPS, backend is public on HTTPS, both scale to zero when nobody's using them, and your total monthly cost stays around $5–10 for typical school traffic.
