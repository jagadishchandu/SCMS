# Custom domain from GoDaddy → SCMS frontend on Azure (full manual flow)

Target end state: your users visit `https://app.yourdomain.com` and see your SCMS frontend, served over free auto-renewing HTTPS from Azure.

**Estimated time:** 30–40 min (most of it is DNS-propagation waiting time)

---

## Phase 1 — Buy / Pick the Domain on GoDaddy

> Skip this phase if you already own a domain.

1. Go to **https://www.godaddy.com**
2. Search for the domain you want (e.g. `myschoolapp.in`, `scms.io`, etc.)
3. Buy the domain. ₹999/year for `.in` or ~₹1,500/year for `.com` is typical.
4. Decide what hostname you want your frontend on:
   - `app.yourdomain.com` (recommended — subdomain, keeps the root free for marketing later)
   - or just `yourdomain.com` (apex/root domain — slightly trickier; covered at the end)

I'll use `app.yourdomain.com` in the steps below. Just replace `yourdomain.com` with your actual domain.

---

## Phase 2 — Add the Custom Domain in Azure Portal

1. Go to **https://portal.azure.com**
2. Top search bar → **Container Apps** → click **`scms-frontend`**
3. Left menu → under **Settings** → click **Custom domains**
4. Click **+ Add custom domain**
5. Fill in:
   - **Domain type**: **Managed certificate** _(this gives you free auto-renewing SSL — what you want)_
   - **Hostname**: `app.yourdomain.com` _(use your real domain)_
6. Click **Validate**

Azure will now show you **two DNS records** you need to add at GoDaddy. They look something like:

| Record type | Hostname / Name | Value / Points to |
|---|---|---|
| **CNAME** | `app` | `scms-frontend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io` |
| **TXT** | `asuid.app` | `A1B2C3D4E5F6789...` _(a long verification string)_ |

> ⚠️ **DO NOT close this Azure tab yet.** You'll come back to click "Add" once GoDaddy DNS is set up. Keep these two values handy — copy them somewhere.

---

## Phase 3 — Add the DNS Records in GoDaddy

1. Open a new browser tab → **https://account.godaddy.com**
2. Log in
3. Go to **My Products**
4. Find your domain → click the three-dot menu → **DNS** (or click the domain name and then **DNS**)
5. You're now on the **DNS Management** page for your domain

### 3.1 Add the CNAME record

1. Scroll to the **DNS Records** section → click **Add New Record**
2. Fill in:
   - **Type**: `CNAME`
   - **Name**: `app` _(just the subdomain part — NOT `app.yourdomain.com`)_
   - **Value**: paste the CNAME target from Azure
     (e.g. `scms-frontend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io`)
   - **TTL**: `1 Hour` (or `600 seconds` — keep it low so changes propagate fast)
3. Click **Save**

### 3.2 Add the TXT verification record

1. Click **Add New Record** again
2. Fill in:
   - **Type**: `TXT`
   - **Name**: `asuid.app` _(yes, including the `asuid.` prefix — GoDaddy will auto-append your domain)_
   - **Value**: paste the verification string from Azure (the long `A1B2C3D4...` value)
   - **TTL**: `1 Hour`
3. Click **Save**

> 📌 **GoDaddy gotcha**: GoDaddy automatically appends your root domain to the Name field. So when you type `app`, the actual record becomes `app.yourdomain.com`. When you type `asuid.app`, it becomes `asuid.app.yourdomain.com`. This is correct — don't include `.yourdomain.com` in the Name field yourself or it'll double up.

### 3.3 Verify the records were saved

After saving, scroll through the DNS records list. You should see:

| Type | Name | Value |
|---|---|---|
| CNAME | `app` | `scms-frontend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io` |
| TXT | `asuid.app` | `A1B2C3D4E5F6789...` |

---

## Phase 4 — Wait for DNS Propagation

DNS changes take **5–30 minutes** to propagate globally. Sometimes longer.

You can speed-check propagation:

1. Open https://www.whatsmydns.net
2. In the search box: enter `app.yourdomain.com`
3. Select record type **CNAME**
4. Click **Search**

When you see green checkmarks across multiple regions, the DNS is live.

Alternative: from your terminal:

```bash
nslookup app.yourdomain.com
# Should return something like:
# Non-authoritative answer:
# app.yourdomain.com  canonical name = scms-frontend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io.
```

If you see the CNAME target, you're good. Move to Phase 5.

---

## Phase 5 — Complete Validation in Azure

1. Go back to the Azure portal tab you left open in Phase 2
2. Click **Validate** again
3. Both checks should now show ✅ green:
   - **Domain ownership**: Passed (TXT verified)
   - **CNAME**: Passed (CNAME points to your container app)
4. Click **Add**

Azure now binds the domain to your frontend container app. The hostname appears in the **Custom domains** list.

If validation fails: wait another 10 minutes, retry. DNS propagation is the most common cause.

---

## Phase 6 — Issue the Free SSL Certificate

1. Still on the **Custom domains** page of `scms-frontend`
2. Find your newly-added `app.yourdomain.com` row
3. Under the **Certificate** column, click the **Add certificate** link → choose **Add managed certificate**
4. A panel slides in:
   - **Validation method**: `CNAME` (already there because you used a CNAME record)
   - **Certificate name**: anything readable (e.g. `app-yourdomain-cert`)
5. Click **Validate** → then **Add**

Azure now provisions a free auto-renewing SSL certificate. **This takes 5–15 minutes.** You'll see a progress indicator.

Once it shows **Status: Healthy**, your domain is live on HTTPS.

---

## Phase 7 — Update Backend CORS to Trust the New Domain

Your backend's CORS allowlist still points at the old `scms-frontend.<id>.azurecontainerapps.io` URL. Now that users will arrive from `app.yourdomain.com`, you need to update it.

1. Portal → **Container Apps** → click **`scms-backend`**
2. Left menu → **Application** → **Containers**
3. Click **Edit and deploy** at the top
4. Click the container name (`scms-backend`)
5. Scroll to **Environment variables**
6. Find the `FRONTEND_URL` row → change its value to:
   ```
   https://app.yourdomain.com
   ```
   _(use your real custom domain, no trailing slash)_
7. Click **Save**
8. Back on the "Edit and deploy" page → click **Create**
9. Wait ~30 seconds for the new revision to go live

---

## Phase 8 — Test Everything

Open in your browser:

```
https://app.yourdomain.com
```

You should see:
- 🟢 Green padlock in the address bar (HTTPS working, certificate trusted)
- The SCMS login screen
- Login works
- All API calls succeed (open DevTools → Network — every `/api/*` call returns 200)

---

## Phase 9 (Optional but Recommended) — Force HTTPS Redirect

Make sure visitors typing `http://app.yourdomain.com` automatically get redirected to HTTPS.

1. Portal → `scms-frontend` → left menu → under **Settings** → click **Ingress**
2. Verify **Insecure connections** is set to **Disabled** _(this means HTTP requests are auto-redirected to HTTPS)_
3. Click **Save** if you changed it

This was already set in the deploy phase, but double-check.

---

## Phase 10 (Optional) — Also Custom-Domain the Backend (`api.yourdomain.com`)

For a cleaner setup, give the backend its own subdomain too. Same flow:

### 10.1 In Azure

1. Portal → **`scms-backend`** → **Settings** → **Custom domains** → **+ Add custom domain**
2. **Hostname**: `api.yourdomain.com` → **Validate**
3. Note the two DNS records Azure gives you (CNAME for `api`, TXT for `asuid.api`)

### 10.2 In GoDaddy

Add the two records:

| Type | Name | Value | TTL |
|---|---|---|---|
| CNAME | `api` | `scms-backend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io` | 1 Hour |
| TXT | `asuid.api` | _(the verification string Azure gave you)_ | 1 Hour |

### 10.3 Wait, validate, bind cert

Same as Phases 4–6 but for the backend.

### 10.4 Rebuild and redeploy the frontend with the new backend URL

This is the critical part — `REACT_APP_BACKEND_URL` is baked into the React bundle.

On your laptop:

```bash
cd /app/frontend

docker build \
  --build-arg REACT_APP_BACKEND_URL=https://api.yourdomain.com \
  -t <LOGIN-SERVER>/scms-frontend:latest .

docker push <LOGIN-SERVER>/scms-frontend:latest
```

Then in the portal:

1. **`scms-frontend`** → **Application** → **Containers**
2. Click **Edit and deploy** → click container → in **Image source** click **Refresh** to re-pull `:latest`
3. **Save** → **Create**

After this, the frontend hits `api.yourdomain.com` directly. Clean, no Azure auto-URLs visible anywhere.

---

## Special case — Apex domain (`yourdomain.com` without `app.`)

CNAME records can't be used on the apex (root) domain. If you want `https://yourdomain.com` directly:

**Option A — Use GoDaddy's domain forwarding** (simplest):
1. GoDaddy → **DNS Management** → **Forwarding** → **Add Forwarding**
2. Forward `yourdomain.com` → `https://app.yourdomain.com`
3. Forward type: **301 Permanent** with **Forward only**

Users typing `yourdomain.com` get redirected to `app.yourdomain.com`. SSL only matters on the `app.` subdomain.

**Option B — A record to Azure Container Apps' IP** (advanced):
Azure Container Apps doesn't expose a static IP on the consumption plan, so this isn't directly supported. The clean path is Option A above.

**Option C — Use Cloudflare in front of GoDaddy DNS** (most flexible):
1. Move DNS from GoDaddy to Cloudflare (free)
2. Use Cloudflare's "CNAME flattening" to put a CNAME on the apex
3. Cloudflare also gives you another free SSL layer and a CDN

If you want detailed steps for Option C, just ask — but Option A covers 95% of use cases.

---

## Troubleshooting cheat sheet

| Symptom | Cause | Fix |
|---|---|---|
| `nslookup` doesn't return the CNAME after 30+ min | TTL too high or record typo in GoDaddy | Re-check Phase 3 — make sure Name is `app` (not `app.yourdomain.com`) |
| Azure "Validate" fails with "TXT record not found" | TXT record propagation slow | Wait 10 more minutes, retry |
| Azure "Validate" fails with "CNAME mismatch" | Wrong CNAME target | Re-copy the CNAME target from Phase 2, update in GoDaddy |
| Browser shows "Not Secure" red padlock | Certificate hasn't finished provisioning | Wait 15 min, refresh the Custom domains page |
| Login works but API calls fail with CORS error | Backend's `FRONTEND_URL` still points at old URL | Re-do Phase 7 |
| API calls go to `https://placeholder` or wrong URL | Frontend was never rebuilt with new backend URL | Re-do Phase 10.4 |
| Cert renewal fails 1 year later | DNS records were deleted | Always keep the CNAME + TXT records — Azure uses them to verify ownership at renewal time |

---

## Cost impact

| Thing | Cost |
|---|---|
| Domain (1 year, `.com` from GoDaddy) | ~$15 |
| Azure managed SSL certificate | **$0 (free, auto-renewing)** |
| Azure custom domain feature | **$0 (included with Container Apps)** |

The only money you spend on the custom domain path is the GoDaddy domain registration itself.

---

## TL;DR — what to type where

| What | Where | Value |
|---|---|---|
| Buy domain | GoDaddy | `yourdomain.com` |
| Add CNAME in GoDaddy DNS | Name: `app` | Value: (CNAME target from Azure) |
| Add TXT in GoDaddy DNS | Name: `asuid.app` | Value: (TXT value from Azure) |
| Wait | whatsmydns.net | Until CNAME shows green globally |
| Click "Validate" + "Add" | Azure portal | scms-frontend → Custom domains |
| Click "Add managed certificate" | Azure portal | Same panel — wait 10 min |
| Update `FRONTEND_URL` env var | Azure portal | scms-backend → Containers → `https://app.yourdomain.com` |
| (Optional) Repeat for `api.yourdomain.com` | Backend | Then rebuild frontend with new backend URL |

After all this, your users have a clean `https://app.yourdomain.com` URL, a green padlock, and Azure renews the cert for free every 6 months automatically. No more `azurecontainerapps.io` URLs anywhere a customer sees.

Want me to also walk you through setting up a **www → app redirect** so `https://www.yourdomain.com` works too? Or set up the apex Cloudflare flow (Option C)?

# `www` redirect + Apex domain via Cloudflare — Full manual steps

Two separate workflows. Pick the one (or both!) you want.

---

# Part A — Add `www.yourdomain.com` → redirects to `app.yourdomain.com`

This makes `https://www.yourdomain.com` work even though your app lives at `app.`. Users who type either URL land on the right place.

> ⏱️ Time: ~10 minutes

## Step A1 — Add the www CNAME at GoDaddy

1. Go to **https://account.godaddy.com** → log in → **My Products**
2. Find your domain → three-dot menu → **DNS**
3. You're on the **DNS Management** page
4. Find the existing **CNAME** record where Name = `www` (GoDaddy creates one by default pointing to `@`). If it exists:
   - Click the pencil/edit icon
   - Change **Value** to: `app.yourdomain.com`
   - **TTL**: `1 Hour`
   - Click **Save**

   If it doesn't exist:
   - Click **Add New Record**
   - **Type**: `CNAME`
   - **Name**: `www`
   - **Value**: `app.yourdomain.com`
   - **TTL**: `1 Hour`
   - Click **Save**

5. Wait 5–10 minutes for DNS propagation. Verify:
   ```bash
   nslookup www.yourdomain.com
   # → should resolve via app.yourdomain.com → Azure FQDN
   ```

## Step A2 — Tell Azure to accept `www.yourdomain.com` too

1. Portal → **Container Apps** → click **`scms-frontend`**
2. Left menu → **Settings** → **Custom domains** → **+ Add custom domain**
3. **Domain type**: **Managed certificate**
4. **Hostname**: `www.yourdomain.com`
5. Click **Validate** → it asks for **one** DNS record this time (just a TXT verification — the CNAME is already pointing through `app`):

   | Type | Name | Value |
   |---|---|---|
   | TXT | `asuid.www` | _(verification string Azure shows)_ |

6. Back at GoDaddy → **Add New Record**:
   - **Type**: `TXT`
   - **Name**: `asuid.www`
   - **Value**: paste the verification string
   - **TTL**: `1 Hour`
   - **Save**
7. Wait 5–10 min for DNS propagation
8. Back in Azure → **Validate** again → both checks green → **Add**
9. Under **Certificate** column for the `www.yourdomain.com` row → click **Add certificate** → **Add managed certificate** → **Validate** → **Add**
10. Wait 5–15 min for cert to provision

## Step A3 — Make it actually redirect (not just serve duplicate content)

Right now both `app.yourdomain.com` and `www.yourdomain.com` serve the same React bundle. SEO-wise that's bad (duplicate content). We want `www.` to **301-redirect** to `app.`.

There are two clean ways:

### Option 1 — GoDaddy Domain Forwarding (simplest, no infrastructure)

1. GoDaddy → **DNS Management** for your domain
2. Scroll to **Forwarding** section → **Add Forwarding**
3. Fill in:
   - **Forward from**: `www.yourdomain.com`
   - **Forward to**: `https://app.yourdomain.com`
   - **Type**: **Permanent (301)**
   - **Settings**: **Forward only** _(not "Forward with masking" — masking breaks HTTPS)_
4. Save

> ⚠️ GoDaddy forwarding **does not handle HTTPS** for `www.` properly — users typing `https://www.yourdomain.com` may get a cert warning. If your users mostly type the URL without typing `https://` first, this works fine. For zero-warning HTTPS on `www`, use Option 2.

### Option 2 — Use nginx in your frontend container to do the redirect (zero-warning HTTPS, recommended)

Add a tiny redirect block to your nginx config:

Open `/app/frontend/nginx.conf` and add this server block **above** the existing `server { listen 3000; ... }`:

```nginx
# Redirect www → app (HTTPS-only, 301 permanent)
server {
    listen 3000;
    server_name www.yourdomain.com;
    return 301 https://app.yourdomain.com$request_uri;
}
```

Then rebuild + push + redeploy:

```bash
cd /app/frontend
docker build \
  --build-arg REACT_APP_BACKEND_URL=https://api.yourdomain.com \
  -t <LOGIN-SERVER>/scms-frontend:latest .
docker push <LOGIN-SERVER>/scms-frontend:latest
```

Portal → **`scms-frontend`** → **Containers** → **Edit and deploy** → click container → **Refresh** image → **Save** → **Create**.

Now `https://www.yourdomain.com/anything` → instant `301` → `https://app.yourdomain.com/anything`. SEO-clean. Cert-clean.

## Step A4 — Test

```bash
curl -I https://www.yourdomain.com
# → HTTP/2 301
# → Location: https://app.yourdomain.com/

curl -I https://app.yourdomain.com
# → HTTP/2 200
```

Or just visit `https://www.yourdomain.com` in your browser — should jump instantly to `app.yourdomain.com`.

---

# Part B — Move DNS to Cloudflare so `yourdomain.com` (apex) works

GoDaddy's DNS can't put a CNAME on the apex (root) domain — DNS standard limitation. Cloudflare invented "CNAME flattening" which solves this, and you get a bunch of bonuses for free along the way.

> ⏱️ Time: ~30 minutes (mostly DNS propagation)
> 💰 Cost: $0 (Cloudflare free plan is plenty)

## What you gain by moving to Cloudflare

| Feature | Benefit |
|---|---|
| **Apex domain support** | `https://yourdomain.com` works directly (no `app.` prefix needed) |
| **Free CDN** | Static assets cached at 300+ global edge locations |
| **Free DDoS protection** | Basic L7 protection automatic |
| **Free SSL** | Cloudflare adds another HTTPS layer |
| **Analytics** | Basic traffic stats, free |
| **Page rules** | Rewrites, redirects, header manipulation |

Your **domain registration stays at GoDaddy** — we're only moving the *DNS* hosting to Cloudflare.

## Step B1 — Sign up for Cloudflare

1. Go to **https://cloudflare.com**
2. Click **Sign Up** → use your email
3. Verify email
4. Click **Add a Site**
5. Enter `yourdomain.com` (no `www.`, no `https://`, no path — just the bare domain)
6. Pick the **Free plan** → **Continue**

## Step B2 — Cloudflare imports your existing DNS

Cloudflare scans GoDaddy's existing DNS records and shows them all:

- CNAME `app` → `scms-frontend.<id>.azurecontainerapps.io` ✓
- CNAME `api` → `scms-backend.<id>.azurecontainerapps.io` ✓
- CNAME `www` → `app.yourdomain.com` ✓
- TXT `asuid.app` → ... ✓
- TXT `asuid.api` → ... ✓
- TXT `asuid.www` → ... ✓
- Plus any MX records (email) GoDaddy auto-created

**Verify every record imported correctly** — if any are missing, click **+ Add record** and add them manually before continuing. Missing the `asuid.*` TXT records will eventually break SSL renewal.

Click **Continue**.

## Step B3 — Cloudflare gives you new nameservers

You'll see something like:

```
abc.ns.cloudflare.com
xyz.ns.cloudflare.com
```

**Copy both nameservers** — you'll paste them at GoDaddy next.

## Step B4 — Change nameservers at GoDaddy

1. **https://account.godaddy.com** → **My Products** → your domain
2. Click **DNS** (or **Manage DNS**)
3. Scroll to **Nameservers** section
4. Click **Change** (or **Change Nameservers**)
5. Select **I'll use my own nameservers** (or **Enter my own**)
6. Enter both Cloudflare nameservers:
   - `abc.ns.cloudflare.com`
   - `xyz.ns.cloudflare.com`
7. **Save** → confirm any "are you sure?" prompts

> ⏱️ Nameserver changes can take **5 min to 24 hr** to propagate globally. Usually 15–30 min. Cloudflare will email you when it detects the change.

## Step B5 — Verify Cloudflare is in control

Once Cloudflare emails you "Your site is active":

1. Go to Cloudflare dashboard → click your domain
2. Top of the page should say **Status: Active** (green)
3. From your terminal:
   ```bash
   nslookup -type=NS yourdomain.com
   # → should now return Cloudflare's nameservers, not GoDaddy's
   ```

## Step B6 — Add the apex CNAME (CNAME flattening)

This is the magic step that lets `https://yourdomain.com` work.

1. Cloudflare dashboard → your domain → left menu → **DNS** → **Records**
2. Click **+ Add record**
3. Fill in:
   - **Type**: **CNAME**
   - **Name**: `@` _(this means the apex / root domain — Cloudflare displays it as `yourdomain.com`)_
   - **Target**: `scms-frontend.gentle-stone-1a2b3c4d.centralindia.azurecontainerapps.io`
     _(your frontend's Azure FQDN — same target as your `app` CNAME)_
   - **Proxy status**: 🟠 **Proxied** _(the orange cloud — this enables CNAME flattening, free CDN, and Cloudflare's SSL)_
   - **TTL**: `Auto`
4. Click **Save**

> 📌 In Cloudflare-speak, the **orange cloud** means traffic goes through Cloudflare's edge. The **gray cloud** means DNS-only (traffic bypasses Cloudflare). For the apex to work, **MUST be orange**.

## Step B7 — Tell Azure to accept the apex domain

1. Portal → **`scms-frontend`** → **Settings** → **Custom domains** → **+ Add custom domain**
2. **Domain type**: **Managed certificate**
3. **Hostname**: `yourdomain.com` _(no `app.`, no `www.`)_
4. **Validate** → Azure shows you DNS records to add

But here's the catch — **Cloudflare's orange-cloud proxy hides Azure's domain validation**. You need to handle this:

### Option B7a (easier) — Temporarily turn off the proxy for validation

1. Cloudflare DNS → find the apex CNAME (`@`) → click **Edit**
2. Change **Proxy status** to 🌫️ **DNS only** (gray cloud)
3. **Save**
4. In Cloudflare DNS, add the TXT verification record Azure gave you:
   - **Type**: `TXT`
   - **Name**: `asuid` _(just `asuid`, which Cloudflare shows as `asuid.yourdomain.com`)_
   - **Content**: _(the verification string)_
   - **Proxy status**: leave as DNS only (TXT records can't be proxied)
   - **Save**
5. Wait 5 min → back in Azure → **Validate** again → ✅ → **Add**
6. Under **Certificate** column → **Add certificate** → **Add managed certificate** → **Validate** → **Add**
7. Wait 5–15 min for Azure cert to provision
8. Once **Status: Healthy** in Azure → go back to Cloudflare DNS → edit the apex CNAME → toggle proxy back to 🟠 **Proxied** → **Save**

✅ Done. Apex domain is live with two layers of HTTPS (Azure cert + Cloudflare cert).

### Option B7b (alternative) — Use Cloudflare's own SSL only

If you'd rather skip Azure's cert for the apex and let Cloudflare handle SSL exclusively:

1. Cloudflare → your domain → **SSL/TLS** → **Overview** → set encryption mode to **Full** _(not "Flexible" — that's insecure)_
2. Cloudflare → **SSL/TLS** → **Edge Certificates** → **Always Use HTTPS** → **On**
3. Skip Azure's "Add custom domain" entirely for the apex
4. Visitors hit `https://yourdomain.com` → Cloudflare serves them with Cloudflare's cert → reverse-proxies to Azure (HTTPS internal hop) → no cert mismatch

This is simpler but means the cert chain shows Cloudflare's CN, not yours. For 99% of users this is invisible.

## Step B8 — Force apex → app redirect (recommended for SEO)

You probably don't want **both** `yourdomain.com` and `app.yourdomain.com` serving identical content. Pick one as canonical.

Most SaaS apps redirect apex → `app.`. In Cloudflare:

1. Cloudflare → your domain → left menu → **Rules** → **Redirect Rules**
2. Click **+ Create rule**
3. Fill in:
   - **Rule name**: `apex → app redirect`
   - **When incoming requests match**: Custom filter expression
     - **Field**: `Hostname`
     - **Operator**: `equals`
     - **Value**: `yourdomain.com`
   - **Then**:
     - **Type**: **Static**
     - **URL**: `https://app.yourdomain.com${http.request.uri}`
     - **Status code**: `301 (Permanent Redirect)`
     - **Preserve query string**: ✅ checked
4. **Deploy**

Now `https://yourdomain.com/anything` → instant `301` → `https://app.yourdomain.com/anything`. Zero infrastructure changes, free, fast.

## Step B9 — Update backend CORS to allow the apex too

Backend currently allows only `app.yourdomain.com`. If you skipped the apex redirect and want apex to serve content directly, also add the apex to the CORS list:

1. Portal → **`scms-backend`** → **Containers** → **Edit and deploy**
2. Find env var `CORS_ORIGINS` (if it doesn't exist, click **+ Add** and create it)
3. Set value to:
   ```
   https://app.yourdomain.com,https://yourdomain.com,https://www.yourdomain.com
   ```
4. **Save** → **Create**

If you set up the apex-redirect (Step B8), this isn't needed — every request reaches the React bundle through `app.yourdomain.com` anyway.

---

# Final state — all the URLs your users can use

| URL | What happens |
|---|---|
| `https://yourdomain.com` | 301 → `https://app.yourdomain.com` (via Cloudflare Redirect Rule) |
| `https://www.yourdomain.com` | 301 → `https://app.yourdomain.com` (via nginx in frontend container, Step A3 Option 2) |
| `https://app.yourdomain.com` | **Frontend serves the React app** |
| `https://api.yourdomain.com` | Backend API (called by the React app) |

All four have green padlocks. All four are HTTPS-only. Cert renewals are automatic at every level (Azure + Cloudflare). Total recurring cost: **$0** beyond your GoDaddy domain renewal.

---

# Quick verification checklist

```bash
# All four should respond
curl -I https://yourdomain.com           # → 301 to app.yourdomain.com
curl -I https://www.yourdomain.com       # → 301 to app.yourdomain.com
curl -I https://app.yourdomain.com       # → 200, React HTML
curl -I https://api.yourdomain.com/api/health  # → 200, JSON

# No SSL warnings anywhere
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com 2>/dev/null | openssl x509 -noout -subject -dates
echo | openssl s_client -connect app.yourdomain.com:443 -servername app.yourdomain.com 2>/dev/null | openssl x509 -noout -subject -dates
```

---

# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Apex resolves but Cloudflare shows "Error 1014: CNAME Cross-User Banned" | Trying to CNAME to a domain owned by a different Cloudflare customer | Don't proxy the apex CNAME (gray cloud), or use Cloudflare Workers proxy |
| `www.` shows Azure cert warning despite Step A2 working | Browser cached an old cert | Ctrl-Shift-R hard refresh; check in incognito |
| Cloudflare says "Site not active" 24 hr after nameserver change | Nameservers not propagated | Run `whois yourdomain.com` — should show Cloudflare's nameservers; if not, re-check GoDaddy |
| Apex domain throws "Too many redirects" | Cloudflare SSL set to "Flexible" + Azure forcing HTTPS | Cloudflare → SSL/TLS → set to **Full (strict)** |
| 521/522/523 errors from Cloudflare | Cloudflare can't reach Azure origin | Cloudflare → SSL/TLS → Origin server → check; or temporarily set Proxy to DNS-only to bypass Cloudflare |

---

# Summary

| What | Where you do it |
|---|---|
| Add `www` CNAME | GoDaddy DNS (or Cloudflare if you moved) |
| Add `www` to Azure custom domains + cert | Azure portal → `scms-frontend` → Custom domains |
| Redirect `www` → `app` | Either GoDaddy Forwarding (Option 1) or nginx in container (Option 2 — better) |
| Move DNS to Cloudflare | Cloudflare signup → change nameservers at GoDaddy |
| Add apex CNAME flattening | Cloudflare DNS → CNAME `@` to Azure FQDN, orange-cloud proxied |
| Apex domain validation in Azure | Temporarily toggle proxy to gray cloud → validate → bind cert → toggle back to orange |
| Redirect apex → app | Cloudflare → Rules → Redirect Rules (free) |

Once all this is in, every URL combination your users will ever type — `yourdomain.com`, `www.yourdomain.com`, `app.yourdomain.com` — lands on the React app over clean HTTPS. The only cost is the GoDaddy domain itself (~₹999–1,500/year).
