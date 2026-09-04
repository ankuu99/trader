# Infra Cost Plan — Life After the AWS Free Tier

**Status:** PLAN ONLY (2026-08-28). Implementation deferred. Successor to `aws_plan.md`
(the original free-tier deployment), which stays valid for how the box is built.

## Context

The account is leaving the 12-month free tier; the current always-on t2.micro will start
billing. The bot only needs compute ~07:00–16:00 IST on NSE trading days (market
09:15–15:30 plus the 08:15 TOTP refresh, 09:00 pre-market and 15:35 post-market jobs).
Everything between 16:00 and 07:00 is idle heartbeat.

Facts gathered 2026-08-28 (read-only):

| Item | Today |
|---|---|
| Instance | `t2.micro` x86_64, ap-south-1b, Ubuntu 24.04 |
| Root volume | 20 GB (default), **4.8 GB used** — OS 2.1G, /var 1.4G (journal 470M, snapd 354M), /opt 1.3G (venv) |
| Database | `market.db` **39 MB** (278k candles; 67k dead 5m/60m/1m rows from Jan–Apr 2026) + 40 MB stale `.bak` files |
| Bot memory | ~254 MB RSS (`MemoryMax=700M` in the unit); box has 954 MB |
| Network | Elastic IP `13.202.187.191`, Tailscale for SSH + dashboard, fail2ban |
| Token | cron `45 2 * * 1-5` (08:15 IST) `kite_totp_refresh.py --no-restart`; bot hot-reloads at 09:00 |
| Service | `scripts/trader.service`, `Restart=always`, `RestartSec=60`, enabled at boot |

## Hard constraints

1. **The Elastic IP stays.** SEBI's algo-trading framework requires a static IP registered
   with the broker. This also rules out non-AWS hosts (Oracle free tier, Hetzner, home
   box) — the registered IP is AWS-bound. An idle/attached EIP is billed either way
   (~$3.6/mo); accept it as a fixed cost.
2. Long-only CNC positions are held overnight, but nothing *acts* on them overnight —
   exits only fire on ticks/candles during market hours. Stopping the box outside hours
   loses no exit coverage.
3. Kite WebSocket tick stream is required (tick-speed stops) → no serverless redesign.

## Cost model (ap-south-1 on-demand, approximate)

| Configuration | Compute | IPv4 | EBS | ≈ $/mo |
|---|---|---|---|---|
| Status quo: t2.micro 24/7, 20 GB | 9.0 | 3.6 | 1.7 | **~14.5** |
| t2.micro, scheduled (≈198 h/mo) | 2.5 | 3.6 | 1.7 | ~7.8 |
| t4g.micro (arm64) 24/7 | 3.9 | 3.6 | 1.7 | ~9.2 |
| **t4g.micro, scheduled** | 1.0 | 3.6 | 1.7 | **~6.3** |
| t4g.micro, scheduled, 8 GB gp3 | 1.0 | 3.6 | 0.7 | ~5.3 |

Scheduled = start 07:00 / stop 16:00 IST Mon–Fri ≈ 9 h × 22 d = 198 h vs 730 h. NSE
holidays (~15/yr) shave another ~6%. EIP is the floor. `t4g.nano` (512 MB) is
rejected: 254 MB bot + journald + tailscale + fail2ban leaves no headroom for
pre-market warm-up spikes.

Verify these numbers against the AWS Pricing Calculator for ap-south-1 before
committing — they are from memory and the IPv4 charge is the one most likely to
have moved.

**Actual bill, August 2026 (screenshot `reviews/aws_bill_aug2026.png`, 2026-09-05): $19.18
≈ ₹1,660 (₹86.5/$).**

| Line | $ | Maps to |
|---|---|---|
| EC2 – Compute | 10.14 | t2.micro × 744 h (plan said 9.2) |
| Virtual Private Cloud | 4.10 | public IPv4 on the EIP (plan said 3.6) |
| EC2 – Other | 2.01 | 20 GB gp3 + small data transfer (plan said 1.7) |
| Tax | 2.93 | 18% GST on 16.25 |

Every line landed ~10% above the estimate; the model is right, the rates were stale.
Inventory confirmed read-only via `aws ec2 describe-*`: one t2.micro, one 20 GB gp3, one
EIP, no snapshots, nothing in other regions. **Compute is the only lever** (₹1,035/mo
incl. GST); IPv4 + EBS are a ₹625/mo floor that survives a stopped instance (an EIP on a
stopped box is still billed). Re-derived targets incl. GST: Phase 1 ≈ $10.4 / ₹900;
Phase 2 t4g.micro ≈ $8.3 / ₹720; Phase 2 with 8 GB root ≈ $6.9 / ₹600. Phase 1 is
~80% of the achievable saving. The IAM user `abhishek` lacks `ce:GetCostAndUsage` /
`budgets:ViewBudget`, so Cost Explorer must be read from the console.

## Plan

### Phase 1 — Scheduled stop/start (biggest win, no migration)

**Status 2026-09-05: IMPLEMENTED (see "As built" below) — the console/EventBridge steps
were replaced because IAM user `abhishek` cannot create roles or schedules.**

**As built:** stop = on-box `scripts/trader-poweroff.timer` (16:00 IST Mon–Fri + 23:55
daily catch-all → `systemctl poweroff`; instance-initiated shutdown behaviour is `stop`,
no AWS rights needed). Start = GitHub Actions `.github/workflows/ec2-schedule.yml`
(06:45 IST Mon–Fri `ec2:StartInstances` with the existing user's keys as repo secrets;
also a 16:30 IST backup stop and a manual start/stop/status button). Boot-time token =
`scripts/kite-token-refresh.service`. Caveats: GitHub cron is best-effort (minutes late
at busy hours — harmless, nothing needs the box before 08:15); GitHub disables schedules
on a public repo after 60 days without commits (it emails first); the repo secret is a
broad EC2 key — a scoped IAM user (Start/Stop/Describe on this instance only) is a
2-minute console job for later. `trader-restart.timer` (weekly) disabled as redundant.
Target: same instance, off 16:00→07:00 IST Mon–Fri. Expected bill ≈ $10.4 / ₹900.

**What exists today (verified 2026-09-05):**
- There is **no boot-time token refresh** — only the 08:15 IST cron
  (`45 2 * * 1-5 kite_totp_refresh.py --no-restart`) plus the 09:00 `pre_market`
  hot-reload. The earlier daily flow was *refresh-then-restart*, never
  *refresh-at-boot*. The box has not rebooted since launch (uptime 139 d); the only
  boot in the journal (2026-04-18) crash-looped on a missing `.env`.
- `trader.service` has `Restart=always`/`RestartSec=60`; `create_kite()` raises on an
  invalid token, so a 07:00 boot on yesterday's token would crash-loop every 60 s
  until 08:15 (≈75 failed starts, each one a Kite login attempt).
- **Shutdown is already a hard kill.** `main.py` only catches `KeyboardInterrupt`;
  SIGTERM (what `systemctl stop` / EC2 stop send) terminates without running the
  `finally`. Every release restart for five months has been exactly this, and it is
  safe because all state is written to SQLite as it happens: open positions, add-on
  lots, `<sym>.peak_close`, `<sym>.max_gain_pct`, `cumulative_pnl`, 15m candles.
  The 2026-09-03 restart log shows it: `Live position restored | CUMMINSIND x7 |
  held_bars=26 peak=5593 max_gain=2.59%`.
- Startup cost: candle-cache refresh + warm-up ≈ 1–3 min (positions seeded 52 s after
  `Started`). Box has 331 MB free with the bot running; a fresh boot has more.
- `timedatectl`: NTP synchronised (TOTP needs this at boot — Ubuntu's timesyncd is on).
- Last scheduled job of the day is `post_market` at 15:35 (holdings reconcile,
  benchmark refresh, daily-P&L Telegram); nothing runs after it. 16:00 stop is safe.
- `trader-restart.timer` (Mon 08:40) becomes redundant under daily boots — disable it.
- IAM user `abhishek` **can** `ec2:StopInstances` / `StartInstances` on this instance
  (dry-run passed) but has **no** IAM, EventBridge Scheduler, Cost Explorer or Budgets
  rights → the scheduler role + rules must be created from the console as the
  account owner. Manual rehearsal from the Mac needs nothing new.

**Steps:**

1. **Boot-time token refresh unit (repo change, no Python change).**
   `scripts/kite-token-refresh.service`: `Type=oneshot`, `User=trader`,
   `After=network-online.target time-sync.target`, `ExecStart=.venv/bin/python
   scripts/kite_totp_refresh.py --no-restart`, logs to journal. In `trader.service`
   add `After=kite-token-refresh.service` + `Wants=kite-token-refresh.service`
   (Wants, not Requires: if Zerodha login fails at boot the bot must still start and
   crash-loop until the 08:15 cron's second attempt — that is the existing self-heal).
   A oneshot runs once per boot, unlike `ExecStartPre=`, which would re-login on every
   crash-restart. Keep the 08:15 cron as belt-and-braces; the bot hot-reloads
   whatever is in `.env` at 09:00 regardless.
   Open point to confirm on day 1: whether the 08:15 re-login invalidates the 07:00
   token. Harmless either way (nothing trades before 09:00 and `pre_market`
   hot-reloads first), but the dashboard token badge at ~08:20 will tell.
2. **Optional hygiene:** a SIGTERM handler in `main.py` that raises `KeyboardInterrupt`
   so `feed.stop()`/`scheduler.stop()` run, and `TimeoutStopSec=30` in the unit.
   Not a prerequisite — see "shutdown is already a hard kill" above.
3. **Deploy** via `release.sh`, then on the box: copy the new unit to
   `/etc/systemd/system/`, `daemon-reload`, `enable kite-token-refresh.service`,
   `disable --now trader-restart.timer`.
4. **Rehearse once by hand, after 16:00 on a trading day, from the Mac:**
   `aws ec2 stop-instances` → wait → `start-instances`. Check: same `13.202.187.191`,
   journal shows `kite-token-refresh` → `Started trader` → positions restored →
   dashboard token VALID via Tailscale. This is the go/no-go for step 5.
5. **Schedule (console, account owner):** IAM role trusted by
   `scheduler.amazonaws.com` with `ec2:StartInstances`/`ec2:StopInstances` on this
   instance ARN; two EventBridge Scheduler rules, timezone `Asia/Kolkata`,
   `cron(0 7 ? * MON-FRI *)` → start, `cron(0 16 ? * MON-FRI *)` → stop.
   EventBridge Scheduler is free at this volume. 07:00 rather than 08:00 buys a
   75-min buffer for a failed boot-time login (the 08:15 cron retries) for ≈ ₹28/mo.
6. **First-week watch:** Telegram startup message each morning ~07:03; token badge at
   08:20; 15:35 daily P&L arrives before 16:00; positions match Kite holdings;
   Cost Explorer in October in the ₹900 band.
7. **Rollback:** disable the two scheduler rules (or `aws ec2 start-instances` from the
   Mac); the box is 24/7 again with no other change.

**Implications accepted with Phase 1:**
- **Daily restart is back.** This reverses the July decision for weekly restarts
  (memory `project_weekly_restart_architecture`): the live retrain cadence is again
  capped at ~25 bars/day because every morning's warm-up retrains from scratch. The
  model is not "cold" — warm-up replays the same persisted candle history (400 d 15m,
  725 d for day-TF names) — but backtests at `retrain_every` > 25 stay not-quite
  live-faithful. If that ever matters, the fix is per-stock model/state persistence,
  not keeping the box on.
- **Dashboard and SSH are off 16:00–07:00.** No evening phone check. Post-market
  Telegram is the closing-state record. (An S3 snapshot page is possible later.)
- **NSE holidays** on weekdays: box boots, bot idles, post-market reconciles holdings
  against itself, stops at 16:00. ≈ ₹30 each, ~15/yr. Not worth a holiday calendar
  in v1. Weekends: never started.
- **T2 CPU credits** are forfeited on stop; launch credits cover the ~2-min warm-up.
- **The 08:30 token-reminder Telegram** becomes noise (boot already refreshed).
- Elastic IP, EBS root, host key, Tailscale node identity all survive stop/start.
  Tailscale reconnects at boot; `release.sh` / `/live-review` / `/missed-opportunities`
  unchanged during the day.

### Phase 2 — arm64 (t4g.micro)

Target: halve the compute line. Requires a new instance (architecture change is not an
in-place resize).

1. Launch `t4g.micro`, Ubuntu 24.04 arm64, same SG, same subnet (ap-south-1b), 8 GB
   gp3 root (enough: ~5 GB used today, most of it OS + venv).
2. Rebuild per `aws_plan.md` Step 2 (Python 3.12, venv, `pip install -r
   requirements.txt` — numpy/scikit-learn/pandas/twisted all ship arm64 wheels;
   verify no x86-only pin), Tailscale, fail2ban, journald cap (`SystemMaxUse=100M`),
   the new token-refresh unit from Phase 1.
3. Copy `config/.env`, `config/config.yaml`, `data/market.db` (39 MB) — drop the two
   `.bak` files. Optionally `DELETE FROM candles WHERE timeframe IN ('5minute',
   '60minute','minute')` + `VACUUM` first (dead cache, −67k rows).
4. **Move the Elastic IP** to the new instance (disassociate → associate). This is the
   moment the registered IP would change if done wrong — it must be the same EIP, not a
   new one. Do it after market close.
5. Re-point `~/.ssh/config` host `trader` (same IP, new host key) and the Tailscale node
   name (`trader-ec2`) so `release.sh`, `/live-review`, `/missed-opportunities` and the
   phone dashboard keep working unchanged.
6. Run one paper session on the new box before the live cut-over; confirm effective
   capital / holdings seeding / ticker connect in the journal.
7. Terminate the t2.micro only after a full live day on t4g; delete its EBS volume
   (snapshot first, keep 30 d).

### Phase 3 — hygiene (small, do alongside Phase 2)

- `journald` `SystemMaxUse=100M` (470 MB today).
- Remove snapd if nothing uses it (354 MB, plus background refreshes on a 1-vCPU box).
- `apt clean`.
- gp2 → gp3 on whatever volume survives (in-place, ~20% cheaper, no downtime).

## Verification checklist (after each phase)

- [ ] `journalctl -u trader` on the first scheduled boot shows token refresh → startup
      → `KiteTicker connected` with no crash-loop.
- [ ] `public-ipv4` metadata unchanged after stop/start; a Kite REST call succeeds.
- [ ] 15:35 post-market ran and Telegram daily P&L arrived before the 16:00 stop.
- [ ] Positions re-seeded from holdings each morning match Kite.
- [ ] AWS Cost Explorer after the first full month is in the projected band.

## Open questions

- Does the registered-IP requirement also cover the **Tailscale** path? (No — Tailscale
  is only used inbound for SSH/dashboard; orders go out via the EIP. Confirm the SG
  still allows nothing inbound on the public IP except SSH 9654.)
- ~~Is `main.py`'s SIGTERM handling clean?~~ Answered 2026-09-05: it is a hard kill and
  has been for every release restart; safe because state is persisted as it happens.
- Does a second TOTP login (08:15 cron) invalidate the 07:00 boot token? Observe on
  day 1 via the dashboard token badge; harmless either way.
- Do we want the S3 snapshot dashboard (Phase 1 step 5b) at all, or is the phone check
  only ever during market hours?

## Not doing

- Lambda / Fargate / spot redesigns — the WebSocket tick stream and tick-speed stops
  need a long-lived process; spot interruption during a session is unacceptable.
- Moving off AWS — the SEBI-registered static IP is an AWS Elastic IP.
- Shrinking storage as a goal — EBS is ~$1.7/mo; only take the 8 GB volume as a free
  side-effect of the Phase 2 rebuild.
