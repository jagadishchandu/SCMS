# Azure Container Apps pricing — straight answer

## TL;DR

**Idle (no traffic, scale-to-zero):** **$0/month for compute.** You only pay for the registry (~$5/mo for ACR Basic).

**With traffic:** Realistic monthly bills for a school/SaaS at typical volumes range from **$0–15/month** for the compute, on top of the $5 ACR. Numbers below.

---

## How Container Apps billing works (Consumption plan)

You're charged for **three things**, all per-second:

| What | Free tier (per subscription, per month) | After free tier |
|---|---|---|
| **Active CPU** (when a container is handling requests) | 180,000 vCPU-seconds | $0.000024 per vCPU-second |
| **Active memory** | 360,000 GiB-seconds | $0.000003 per GiB-second |
| **Requests** | 2,000,000 requests | $0.40 per million requests |

Plus a fourth, much cheaper rate that kicks in *between* requests:

| What | Free tier | After |
|---|---|---|
| **Idle CPU** (replica spun up but not actively serving) | 0 | $0.000003 per vCPU-second |
| **Idle memory** | 0 | $0.000003 per GiB-second |

The "idle" rate is 8× cheaper than "active" — Azure charges it during the ~5-10 minutes between scale-up and scale-back-to-zero.

---

## What "scale to zero" actually means for billing

Container Apps with `--min-replicas 0`:

```
0 replicas running         → $0 compute charge
Request arrives            → cold start (~2-5 sec), replica spins up
Replica handling traffic   → ACTIVE rate (vCPU + memory + requests)
Replica idle 5-10 min      → IDLE rate (still cheap)
No more traffic            → scales back to 0 → $0 again
```

**You are NOT charged for the time replicas are scaled to zero.** Period.

---

## Real-world cost examples for SCMS

Assumptions (matches the deployment I gave you):
- Backend: `0.5 vCPU / 1.0 GiB`, scale 0→3
- Frontend: `0.25 vCPU / 0.5 GiB`, scale 0→2 *(or $0 forever if you use Static Web Apps instead)*

### Scenario 1 — A school using the app a couple of hours/day

- ~50 concurrent users for 2 hours/day = 60 hours/month active
- ~500,000 API requests/month

| Resource | Usage | Inside free tier? | Cost |
|---|---|---|---|
| Active CPU (backend, 0.5 vCPU × 60 hr) | 108,000 vCPU-s | ✅ entirely | $0 |
| Active memory (backend, 1 GiB × 60 hr) | 216,000 GiB-s | ✅ entirely | $0 |
| Idle CPU (backend, 5-min cooldown × ~600 hits) | ~9,000 vCPU-s | (idle isn't free, but tiny) | $0.03 |
| Frontend active (0.25 vCPU × 60 hr) | 54,000 vCPU-s | ✅ within combined free tier | $0 |
| Requests (500k total) | 0.5M | ✅ entirely | $0 |
| **Compute total** | | | **~$0/month** |
| ACR Basic | | | **$5/month** |
| **Grand total** | | | **~$5/month** |

### Scenario 2 — Medium SaaS, 10 schools, all-day usage

- ~500 users active 8 hours/day = 240 hours/month
- ~5 million API requests/month
- Backend stays at 1 replica during business hours

| Resource | Usage | Cost |
|---|---|---|
| Active CPU (backend, 0.5 vCPU × 240 hr) | 432,000 vCPU-s | (432k − 180k free) × $0.000024 = **$6.05** |
| Active memory (backend, 1 GiB × 240 hr) | 864,000 GiB-s | (864k − 360k free) × $0.000003 = **$1.51** |
| Frontend active (0.25 vCPU × 240 hr) | 216,000 vCPU-s | shared free tier already used → $5.18 |
| Frontend memory (0.5 GiB × 240 hr) | 432,000 GiB-s | shared free tier already used → $1.30 |
| Requests (5M) | (5M − 2M free) × $0.40/M | **$1.20** |
| **Compute total** | | **~$15/month** |
| ACR Basic | | $5 |
| **Grand total** | | **~$20/month** |

> If you put the frontend on Static Web Apps free tier instead, that line drops by ~$6.50 → **total ~$13/month**.

### Scenario 3 — Heavy load, traffic spikes to 5 replicas

- 100,000 daily active users, autoscale to 5 replicas during peak
- 50 million API requests/month
- Effective CPU usage: 1.5 vCPU avg over the month (across all replicas)

| Resource | Usage | Cost |
|---|---|---|
| Active CPU (1.5 vCPU avg × 730 hr) | 3.94M vCPU-s | (3.94M − 0.18M free) × $0.000024 = **$90** |
| Active memory (3 GiB avg × 730 hr) | 7.88M GiB-s | (7.88M − 0.36M free) × $0.000003 = **$22.55** |
| Requests | 50M | (50M − 2M free) × $0.40/M = **$19.20** |
| **Compute total** | | **~$132/month** |
| ACR Basic | | $5 |
| **Grand total** | | **~$137/month** |

Even at 50M requests/month the bill stays under $150 — that's the magic of consumption pricing.

---

## What you DON'T pay for

- ✅ The Container Apps **Environment** (the shared network) is free
- ✅ **HTTPS certificates** auto-managed and free
- ✅ **Built-in load balancer** and ingress
- ✅ The first **100 GB/month of outbound bandwidth**
- ✅ **Log Analytics** workspace (first 5 GB/month free for logs)
- ✅ Scaling decisions, health checks, restarts, rolling deploys

---

## How to KEEP the cost low — practical knobs

1. **`--min-replicas 0`** — single most important flag. Without this, you pay 24/7 for at least one replica (~$15/month minimum).

   ```bash
   az containerapp update -n scms-backend -g $RG --min-replicas 0
   ```

2. **Right-size the container.** SCMS backend runs comfortably on `0.5 vCPU / 1 GiB`. Going to `0.25 vCPU / 0.5 GiB` halves the burn rate. Test with:

   ```bash
   az containerapp update -n scms-backend -g $RG --cpu 0.25 --memory 0.5Gi
   ```

3. **Cap max replicas** so a bug/loop can't run away with your bill:

   ```bash
   az containerapp update -n scms-backend -g $RG --max-replicas 3
   ```

4. **Tune the cooldown** — by default, an idle replica stays alive ~5 minutes before scaling down. For a low-traffic school app, shorten it to 60 seconds:

   ```bash
   az containerapp update -n scms-backend -g $RG \
     --scale-rule-name http-rule --scale-rule-type http \
     --scale-rule-http-concurrency 10
   ```

5. **Move the frontend to Static Web Apps** — already covered. Saves the entire frontend compute line.

6. **Use Mongo Atlas free tier (M0)** instead of Cosmos. Cosmos starts at ~$25/month. Atlas M0 is free forever and is plenty for < 512 MB of data.

7. **Set a budget alert** so you're notified if anything goes wrong:

   ```bash
   az consumption budget create \
     --budget-name scms-monthly-cap \
     --amount 25 \
     --time-grain Monthly \
     --start-date 2026-01-01 --end-date 2027-01-01 \
     --resource-group $RG
   ```

---

## Cold-start consideration (the only real trade-off)

With `--min-replicas 0`, the **first request after a quiet period** takes 2–5 seconds while a replica boots. After that, requests are normal (~50ms).

For SCMS this is fine — school admins log in once and the replica stays warm for all subsequent activity. For a public consumer app where first-page-load latency is everything, you might bump `--min-replicas 1` (costs ~$15/month for 24/7 backend) to eliminate cold starts.

---

## Bottom line for your SCMS deployment

| Traffic level | Monthly bill (backend on Container Apps + frontend on SWA + Mongo Atlas) |
|---|---|
| 🌙 Nobody using it | **~$5** (just ACR) |
| 👤 1 school, a few hours/day | **~$5–7** |
| 🏫 5–10 schools, daily use | **~$10–20** |
| 🏢 50+ schools, heavy use | **~$50–100** |
| 🌍 1000 schools | **~$300–500** |

Compare this to running a single Azure VM 24/7 for the same workload (~$30/month minimum, no autoscale, no free HTTPS) and Container Apps is genuinely the cheapest production-grade option Azure has.

If you want, I can also help set up the **budget alert** so Azure emails you the moment you cross a threshold like $10 or $25. Just say the word.
