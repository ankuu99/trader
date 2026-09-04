# AWS Deployment Plan — Trader Bot (EC2 Free Tier)

## Context
The trading bot runs as a long-running Python daemon during NSE market hours (9:15 AM–3:30 PM IST, Mon–Fri). The goal is to deploy it on an AWS EC2 t2.micro (free tier) with a static IP, security hardening, and a daily token refresh workflow that works around Kite's browser-based OAuth flow.

---

## Architecture

```
Your Mac
  ├─ daily 8:45 AM IST: ~/scripts/refresh-token.sh
  │     runs login.py locally → scp config/.env → ssh restart
  └─ SSH (port 9654, any IP — key-only auth)
        │
        EC2 t2.micro (ap-south-1, Ubuntu 24.04)
          ├─ Elastic IP (static)
          ├─ /opt/trader/          ← project root (git pull to update)
          ├─ /opt/trader/.venv/    ← Python 3.12 venv
          ├─ /opt/trader/config/.env  ← chmod 600, trader user only
          └─ systemd: trader.service  ← auto-start on boot, restart on crash
```

---

## Step 1: AWS Console Setup

### 1.1 EC2 Instance
- **Region**: ap-south-1 (Mumbai) — lowest latency to Kite/NSE
- **AMI**: Ubuntu 24.04 LTS (ships Python 3.12 natively, LTS until 2029)
- **Type**: t2.micro (1 vCPU, 1 GB RAM) — free tier
- **Storage**: 20 GB gp3

### 1.2 Key Pair
Generate ED25519 key locally before launching:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/trader_ec2 -C "trader-ec2"
```
Upload the public key (`trader_ec2.pub`) when creating the key pair in console.

### 1.3 Security Group (`trader-sg`)
**Inbound — only one rule:**

| Protocol | Port | Source | Reason |
|----------|------|--------|--------|
| TCP | 9654 | 0.0.0.0/0 (any) | SSH — key-only, dynamic IP friendly |

> Note: Port 8080 does NOT need to be open. `scripts/login.py` binds to `127.0.0.1:8080` — it physically cannot run on EC2. It must run on your Mac locally.

**Outbound**: Allow all (default) — bot needs TCP 443 to `api.kite.trade` and `api.telegram.org`.

### 1.4 Elastic IP
1. EC2 → Elastic IPs → Allocate → Amazon's pool
2. Actions → Associate → select your instance
3. **Free while instance is running.** Keep instance running 24/7 to avoid $0.005/hr unassociated charge.

### 1.5 SSH Config on Mac
```
# Add to ~/.ssh/config
Host trader
    HostName YOUR_ELASTIC_IP
    User ubuntu
    Port 9654
    IdentityFile ~/.ssh/trader_ec2
    ServerAliveInterval 60
```
After this: `ssh trader` to connect.

---

## Step 2: EC2 System Setup

SSH in as `ubuntu`, run all commands below.

### 2.1 OS Updates
```bash
sudo apt update && sudo apt upgrade -y
sudo apt autoremove -y
```

### 2.2 Install Dependencies
```bash
sudo apt install -y python3-pip python3-venv python3-dev build-essential \
                    fail2ban unattended-upgrades
```
Python 3.12 is the system Python on Ubuntu 24.04 — no pyenv needed.

### 2.3 Create App User and Directory
```bash
sudo useradd -r -s /bin/bash -m -d /opt/trader trader
sudo mkdir -p /opt/trader
sudo chown trader:trader /opt/trader
```

### 2.4 Clone the Repo
```bash
sudo -u trader bash
cd /opt/trader
git clone https://github.com/YOUR_REPO/trader.git .
# For private repo: git clone https://YOUR_PAT@github.com/YOUR_REPO/trader.git .
```

### 2.5 Python Virtual Environment
```bash
# As trader user in /opt/trader
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install --no-cache-dir -r requirements.txt
# Note: scikit-learn + pandas build takes 3–5 min on t2.micro — normal
```

### 2.6 Create and Secure .env
```bash
cp /opt/trader/config/.env.example /opt/trader/config/.env
chmod 600 /opt/trader/config/.env
chown trader:trader /opt/trader/config/.env
nano /opt/trader/config/.env
```
Fill in: `KITE_API_KEY`, `KITE_API_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Leave `KITE_ACCESS_TOKEN` blank — populated by daily workflow.

### 2.7 Create Writable Directories
```bash
mkdir -p /opt/trader/data /opt/trader/logs
chown -R trader:trader /opt/trader/data /opt/trader/logs
```

---

## Step 3: systemd Service

Create `/etc/systemd/system/trader.service`:
```bash
sudo nano /etc/systemd/system/trader.service
```

Paste this content:
```ini
[Unit]
Description=Python Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=trader
Group=trader
WorkingDirectory=/opt/trader
ExecStart=/opt/trader/.venv/bin/python main.py
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=300
StartLimitBurst=3

Environment=PYTHONUNBUFFERED=1
Environment=TZ=Asia/Kolkata

MemoryMax=700M
MemorySwapMax=0

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/trader/data /opt/trader/logs /opt/trader/config

StandardOutput=journal
StandardError=journal
SyslogIdentifier=trader

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable trader.service
sudo systemctl start trader.service
sudo systemctl status trader.service
```

Key settings explained:
- `After=network-online.target`: waits for network before starting (prevents Kite auth failure on boot)
- `Restart=on-failure` + `RestartSec=30`: auto-restart on crash, 30s cooldown
- `StartLimitBurst=3`: gives up after 3 failures in 5 min — prevents bad-token crash loop
- `MemoryMax=700M`: hard cap to protect OS on 1 GB machine
- `MemorySwapMax=0`: disables swap for this process — OOM kill is better than grinding swap on EBS
- `ProtectSystem=strict`: process can only write to the three listed paths

---

## Step 4: Daily Token Refresh Workflow

**Why this is needed**: `KITE_ACCESS_TOKEN` expires at midnight IST daily.

**Critical constraint**: `scripts/login.py` binds to `127.0.0.1:8080` (confirmed in code) — it **cannot** run on EC2. It must run on your Mac where a browser is available.

### Create Mac helper script `~/scripts/refresh-token.sh`:
```bash
#!/usr/bin/env bash
set -e

TRADER_DIR="/Users/abhisheksingh/Projects/trader"
EC2_HOST="trader"

echo "=== Step 1: Kite login (local) ==="
cd "$TRADER_DIR"
source .venv/bin/activate
python scripts/login.py

echo "=== Step 2: Upload .env to EC2 ==="
scp "$TRADER_DIR/config/.env" "$EC2_HOST:/opt/trader/config/.env"

echo "=== Step 3: Restart service ==="
ssh "$EC2_HOST" "sudo systemctl restart trader && sleep 3 && sudo systemctl status trader --no-pager"

echo "=== Done. ==="
```

```bash
chmod +x ~/scripts/refresh-token.sh
```

**Run every trading day before 9:15 AM IST** (safest window: 8:45–9:00 AM):
```bash
~/scripts/refresh-token.sh
```

**Token expiry note**: The token expires at midnight IST (day boundary, not 24h from generation). Do NOT run this the night before — it will be invalid by market open.

**If things look broken**: No Telegram startup message by 9:10 AM → check:
```bash
ssh trader "sudo journalctl -u trader -n 50 --no-pager"
```

---

## Step 5: Security Hardening

### 5.1 SSH Hardening
```bash
sudo nano /etc/ssh/sshd_config
```
Set/confirm these values:
```
Port 9654
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
```
```bash
sudo systemctl restart sshd
# IMPORTANT: Keep current SSH session open! Test a second session before closing.
```

### 5.2 UFW Firewall (defense-in-depth, independent of Security Group)
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 9654/tcp
sudo ufw enable
sudo ufw status verbose
```

### 5.3 Fail2ban (SSH brute-force protection)
```bash
sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 3

[sshd]
enabled = true
port    = 9654
logpath = /var/log/auth.log
EOF

sudo systemctl enable fail2ban
sudo systemctl start fail2ban
sudo fail2ban-client status sshd
```

### 5.4 Automatic Security Updates
```bash
sudo dpkg-reconfigure --priority=low unattended-upgrades
# Select "Yes" when prompted
```

---

## Step 6: Ongoing Operations

### Deploy a Code Update
```bash
# On Mac: push to GitHub
git push origin main

# On EC2: pull and restart
ssh trader "cd /opt/trader && sudo -u trader git pull && sudo systemctl restart trader"

# If requirements.txt changed:
ssh trader "cd /opt/trader && sudo -u trader .venv/bin/pip install -r requirements.txt && sudo systemctl restart trader"
```

### Update Config Only
```bash
scp config/config.yaml trader:/opt/trader/config/
ssh trader "sudo systemctl restart trader"
```

### Update .env (non-token values like Telegram IDs)
```bash
# Edit locally, then push
scp config/.env trader:/opt/trader/config/.env
ssh trader "sudo systemctl restart trader"
```

### Quick Reference Commands
```bash
# Health check from Mac
ssh trader "sudo systemctl is-active trader"

# Live logs
ssh trader "sudo journalctl -u trader -f"

# Last 100 lines
ssh trader "sudo journalctl -u trader -n 100"

# Errors in last 24 hours
ssh trader "sudo journalctl -u trader --since '24 hours ago' | grep -E 'ERROR|CRITICAL'"

# Memory usage
ssh trader "free -h && ps aux --sort=-%mem | head -3"

# Disk usage
ssh trader "df -h / && du -sh /opt/trader/logs/ /opt/trader/data/"
```

---

## Verification Checklist

After initial setup and after `refresh-token.sh`, verify:

- [ ] `ssh trader` connects without password prompt
- [ ] `sudo systemctl status trader` shows `active (running)`
- [ ] Telegram receives a startup notification
- [ ] `sudo journalctl -u trader -f` shows candle/strategy logs during market hours
- [ ] `ls -la /opt/trader/config/.env` shows `-rw------- 1 trader trader`
- [ ] `sudo ufw status` shows port 9654 allowed
- [ ] `sudo fail2ban-client status sshd` shows jail is active

---

## Resource Budget (Free Tier)

| Resource | Limit | Expected Usage |
|----------|-------|----------------|
| EC2 t2.micro | 750 hrs/month (12 months) | 720 hrs/month (24/7) |
| Elastic IP | Free while associated | 1 IP, always associated |
| EBS storage | 30 GB/month | 20 GB provisioned |
| RAM | 1 GB | ~300–500 MB steady state |
| CPU | 1 vCPU | < 5% avg, 30% pre-market spike |
| Disk growth | — | ~70 MB logs (rotating) + ~1 MB/mo SQLite |

**No code changes to the project are required.** This is purely infrastructure setup.

---

## Operations since 2026-09-05 — scheduled stop/start (cost cut ₹1,660 → ~₹900/mo)

Full plan, bill breakdown and implications: `infra_cost_plan.md`. This is the how-to.

### Daily cycle (Mon–Fri, IST)
| Time | What | Where it lives |
|---|---|---|
| 06:45 | Instance **started** | GitHub Actions `.github/workflows/ec2-schedule.yml` (cron, best-effort ±15 min) |
| boot | Kite TOTP login → `config/.env` | `scripts/kite-token-refresh.service` (oneshot; `trader.service` waits on it) |
| boot+1 min | Bot up, positions restored from SQLite + holdings | `trader.service` |
| 08:15 | Second TOTP login (belt-and-braces) | trader-user cron `--no-restart` |
| 09:00 | Token hot-reload; **effective-capital cap retried** if Kite margins were down at boot | `main.py pre_market()` |
| 16:00 | Instance **powered off** (= EC2 stop) | `scripts/trader-poweroff.timer` on the box |
| 16:30 | Backup stop (no-op if already stopped) | GitHub Actions |
| 23:55 daily | Catch-all power-off (covers a box started by hand) | `scripts/trader-poweroff.timer` |

Weekends/NSE holidays: never started on weekends; weekday holidays boot and idle (~₹30).
Elastic IP, EBS root, host key and Tailscale identity all survive stop/start.
Dashboard + SSH are unreachable while stopped.

### Why GitHub Actions starts it
A stopped instance cannot start itself; something outside must call the AWS API.
The AWS-native way (EventBridge Scheduler) needs an IAM role, and IAM user `abhishek`
has no IAM/scheduler/cost-explorer rights — only EC2. GitHub Actions is a free
external cron running one command, `aws ec2 start-instances`, with the key stored as
repo secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. Schedules only run from the
default branch (`main`) — the workflow must exist on `main`.

### Secrets — what is and isn't public
- Repo is PUBLIC. The workflow file holds only instance id + region (not secret).
- No key has ever been in a tracked file or git history (verified 2026-09-05).
  `config/.env` is git-ignored.
- GitHub secrets are encrypted, never readable back (API returns name only), masked in
  logs, and never passed to fork PRs. Only a write-access account can use them —
  i.e. exposure = "as safe as the GitHub login", not public.
- The key is the SAME broad EC2 key the Mac uses. Its values were also displayed once
  in a Claude session transcript on 2026-09-05 (private, not public). **Rotate it** at
  the next console login (see below).
- Rotate / re-set the GitHub copy from the Mac:
  `aws configure get aws_access_key_id | gh secret set AWS_ACCESS_KEY_ID -R ankuu99/trader`
  `aws configure get aws_secret_access_key | gh secret set AWS_SECRET_ACCESS_KEY -R ankuu99/trader`
- GitHub disables scheduled workflows on a public repo after 60 days without commits
  (it emails first). A commit re-arms it.

### Manual control from the Mac
```
./scripts/ec2.sh status | start | stop | ensure-running
```
`ensure-running` starts only if stopped and waits for SSH. Or use GitHub → Actions →
"EC2 schedule" → Run workflow → start/stop/status (works from the phone).

### Releases
Unchanged: `./scripts/release.sh release-YYYY-MM-DD`. `deploy.sh` now runs
`ec2.sh ensure-running` first (starts a stopped box), checks out the tag, installs
any changed systemd units (`trader.service`, `kite-token-refresh.service`,
`trader-poweroff.{service,timer}`), restarts the bot. An evening-started box powers
off at 23:55 on its own — no manual stop needed.

### Pending console work (needs root/admin login — the CLI user cannot do IAM)
1. **Rotate the `abhishek` access key** (create new → update Mac profile + the two
   GitHub secrets → delete old).
2. Preferably **go AWS-native**: IAM role for `scheduler.amazonaws.com` with
   `ec2:StartInstances`/`StopInstances` on `i-04c3a635ebb6455e2`; two EventBridge
   Scheduler rules, timezone Asia/Kolkata: `cron(45 6 ? * MON-FRI *)` start,
   `cron(0 16 ? * MON-FRI *)` stop. Then delete the GitHub workflow + secrets.
3. A scoped IAM user (Start/Stop/Describe on this instance only) for the Mac's
   `ec2.sh`, replacing the broad key.

### Verification checklist (first week)
- [ ] Telegram startup message ~06:47 each weekday
- [ ] Journal: `kite-token-refresh` finished → `Started trader` → `Live position restored`
- [ ] 09:00 log shows `Effective capital set (pre_market)` if the boot-time margins call failed
- [ ] 15:35 daily-P&L Telegram arrives; box gone by 16:01 (`./scripts/ec2.sh status`)
- [ ] `public-ipv4` unchanged; Kite orders fill
- [ ] October bill ≈ ₹900
