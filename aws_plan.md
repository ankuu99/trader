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
