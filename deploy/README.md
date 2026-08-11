# Deploying Context VCS to a VM (M1)

One small VM runs everything: Postgres, API, web, Caddy (TLS), nightly backups.
Budget: ~$6–15/mo + a domain.

## 1. What you need before starting (10 minutes, human steps)

1. **A VM.** DigitalOcean (recommended: signup is email + card, no ID-document
   verification, friendliest console for a first VM):
   - https://cloud.digitalocean.com → Create → Droplets → image **Ubuntu 24.04** →
     Basic plan, **$12/mo (1 vCPU / 2 GB)** is enough for a friends-team demo
     (step 2 adds swap for headroom; resize in place later if it ever feels tight) →
     Authentication: **SSH key** (paste `cat ~/.ssh/id_ed25519.pub`) → Create.
   - Networking → Firewalls (optional but good practice): allow only 22, 80, 443.
   - Alternatives if you prefer: Vultr (~$12/mo, similar flow) or AWS Lightsail
     ($12/mo, flat pricing). Hetzner is cheapest (~€4.6/mo CX22) but requires
     identity verification for new accounts. Any Ubuntu box works — nothing below
     is provider-specific.
2. **A domain (or subdomain).** Any registrar (~$10/yr). Create an **A record**
   pointing e.g. `ctx.yourdomain.com` → the VM's public IPv4. TLS is automatic
   after that (Caddy + Let's Encrypt) — no certificate work.
3. Your **Anthropic and OpenAI API keys** (the same ones from local `.env`).

## 2. Prepare the VM (once)

```bash
ssh root@<VM_IP>
curl -fsSL https://get.docker.com | sh
# on a 2 GB box, add swap so builds and pg never get OOM-killed:
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
git clone <this-repo-url> ctxvcs && cd ctxvcs
cp deploy/env.prod.example deploy/.env.prod
nano deploy/.env.prod        # DOMAIN, DB_PASSWORD (long random), INVITE_CODE,
                             # ADMIN_EMAIL, both API keys
```

## 3. Launch

```bash
docker compose -f deploy/compose.prod.yml --env-file deploy/.env.prod up -d --build
```

First build takes a few minutes. Then check `https://<DOMAIN>/api/healthz` → `{"ok":true}`
and open `https://<DOMAIN>` — the signup page. Sign up with **ADMIN_EMAIL** first
(that account gets the admin role), then send friends the URL + INVITE_CODE.

Everything auto-restarts on reboot (`restart: unless-stopped`).

## 4. Friends' machines

```bash
pipx install "git+<this-repo-url>#subdirectory=cli"   # or pip install --user
ctxvcs login --api https://<DOMAIN>/api --web https://<DOMAIN>
ctxvcs push
```

## 5. Backups & restore drill

Nightly gzip dumps land in the `backups` volume (14 kept). To copy the latest off-VM:

```bash
docker compose -f deploy/compose.prod.yml --env-file deploy/.env.prod \
  cp backup:/backups/$(docker compose -f deploy/compose.prod.yml --env-file deploy/.env.prod \
  exec backup ls -1t /backups | head -1) ./
```

Restore drill (M1 acceptance — run once on a scratch VM or locally):

```bash
gunzip -c ctxvcs-<ts>.sql.gz | docker compose -f deploy/compose.prod.yml \
  --env-file deploy/.env.prod exec -T db psql -U ctxvcs ctxvcs
```

## 6. Operations

- **Update the app:** `git pull && docker compose -f deploy/compose.prod.yml --env-file deploy/.env.prod up -d --build`
- **Logs:** `docker compose -f deploy/compose.prod.yml --env-file deploy/.env.prod logs -f api`
- **Rotate the invite code:** edit `.env.prod`, `up -d` again (existing accounts unaffected).
- **Wiki looks stale:** `POST https://<DOMAIN>/api/repos/<repo>/wiki/rebuild` (admin token) — always safe.
