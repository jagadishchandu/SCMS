# Running SCMS frontend & backend in **separate containers**

The repo ships with a `docker-compose.yml` that wires the two services together
on a private network. If you'd rather run them as two completely independent
containers (different hosts, different clouds, k8s pods, etc.) — this guide
shows exactly how to do that and which environment variables to pass.

> TL;DR
> * Build the **frontend** with `--build-arg REACT_APP_BACKEND_URL=https://api.example.com`.
> * Run the **backend** with `FRONTEND_URL=https://app.example.com`.
> * That's it — the React bundle calls the backend directly, and the backend's
>   CORS allowlist includes whatever `FRONTEND_URL` you set.

---

## 1. Backend container

```bash
cd backend
docker build -t scms-backend .

docker run -d --name scms-backend \
  -p 8001:8001 \
  -e MONGO_URL="mongodb+srv://user:pass@cluster/?retryWrites=true" \
  -e DB_NAME="scms_db" \
  -e JWT_SECRET="<generate a long random string>" \
  -e ADMIN_EMAIL="admin@yourdomain.com" \
  -e ADMIN_PASSWORD="<strong password>" \
  -e FRONTEND_URL="https://app.example.com" \
  -e ENABLE_SUBSCRIPTION_GUARD="true" \
  -e SUBSCRIPTION_PRICE_PER_CHILD_MONTHLY="30" \
  -e SUBSCRIPTION_PRICE_PER_CHILD_YEARLY="300" \
  scms-backend
```

### Key environment variables

| Variable | What it does | Default |
|----------|--------------|---------|
| `MONGO_URL` | Mongo / Cosmos connection string | _required_ |
| `DB_NAME` | Master database name | `scms_db` |
| `JWT_SECRET` | Signing key for auth tokens | _required_ |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Single platform super-admin (provisioned on first boot) | _required_ |
| **`FRONTEND_URL`** | **Public URL of the frontend container — automatically added to the CORS allowlist** | _empty_ |
| `CORS_ORIGINS` | Extra comma-separated origins to allow | _empty_ |
| `ENABLE_SUBSCRIPTION_GUARD` | Block writes when subscription expires | `true` |
| `SUBSCRIPTION_PRICE_PER_CHILD_MONTHLY` | INR/child/month | `30` |
| `SUBSCRIPTION_PRICE_PER_CHILD_YEARLY` | INR/child/year | `300` |

`FRONTEND_URL` is the **only** thing the backend needs to know about the
frontend — it gets appended to `CORS_ORIGINS` automatically at startup.

The backend listens on **:8001** and serves all routes under **`/api/...`**.
Health check: `GET /api/health`.

The default uvicorn command bundled in the image already runs with
`--timeout-keep-alive 400` so long-running exports / digest jobs don't drop.

---

## 2. Frontend container

The React bundle needs to know where the backend lives **at build time**
(this is a Create React App limitation — the value is baked into the JS).

```bash
cd frontend
docker build \
  --build-arg REACT_APP_BACKEND_URL=https://api.example.com \
  -t scms-frontend .

docker run -d --name scms-frontend \
  -p 3000:3000 \
  scms-frontend
```

That's it — the browser will hit `https://api.example.com/api/...` directly.
CORS is satisfied because the backend has `FRONTEND_URL=https://app.example.com`
in its allowlist (see step 1).

### Optional: route /api/* through the frontend's nginx

If you don't want the browser to talk to the backend directly (e.g. you want a
single public origin and CORS-free cookies), leave `REACT_APP_BACKEND_URL`
**empty** at build time and instead point the nginx reverse-proxy at the
backend's internal address:

```bash
docker run -d --name scms-frontend \
  -p 3000:3000 \
  -e BACKEND_UPSTREAM="scms-backend:8001" \
  scms-frontend
```

`BACKEND_UPSTREAM` is substituted into `nginx.conf` at container start by
nginx's built-in `envsubst` templating.

### Frontend HTTP timeout

The axios client is configured with a **400-second** timeout
(`frontend/src/lib/api.js`) and the bundled nginx config uses
`proxy_read_timeout 400s` to match — long-running PDF / digest / import
endpoints no longer drop mid-request.

---

## 3. Cross-container networking checklist

* **Frontend URL** (the value you give the user) — passed to the backend as
  `FRONTEND_URL`. The backend auto-adds it to CORS.
* **Backend URL** (where the React bundle should send requests) — passed to
  the frontend Docker build as `--build-arg REACT_APP_BACKEND_URL=...`.
* If your backend sits behind HTTPS + a path prefix, give the **full** URL
  including scheme (e.g. `https://api.example.com`). Do **not** include
  `/api` — the React client appends that itself.
* Cookies are scoped to the backend origin. If you need cross-site cookies
  (frontend on a different domain), the backend already sends
  `Access-Control-Allow-Credentials: true` — just make sure both origins are
  served over HTTPS in production.

---

## 4. Subscription-charge bug — fixed

Earlier, the "Choose your plan" cards on `/school/subscription` showed
`₹0` until students were physically onboarded — even though the school admin
had already entered the planned children count.

The quote endpoint (`GET /api/subscriptions/my`) now bills the **greater of**:

* `subscription_approval.approved_children_count`
* `subscription_approval.requested_children_count`
* current `students.status == "active"` count

…and the approval form shows a **live monthly + yearly cost preview** as the
admin types. The previously misleading "For 0 active students in your school
today" caption is gone.
