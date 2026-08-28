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

## Plan

### Phase 1 — Scheduled stop/start (biggest win, no migration)

Target: same instance, off 16:00→07:00 IST on weekdays.

1. **Make the boot sequence token-safe.** Today the box boots on yesterday's token and
   `main.py` would crash-loop (`Restart=always`, 60 s) until the 08:15 cron writes a
   fresh one. Fix in the unit, not in cron:
   - Add `scripts/kite-token-refresh.service` (oneshot, `User=trader`, runs
     `kite_totp_refresh.py --no-restart`) and make `trader.service`
     `After=kite-token-refresh.service` + `Wants=kite-token-refresh.service`.
     Alternative: `ExecStartPre=` on `trader.service` — simpler, but a TOTP failure
     then blocks the bot start with no separate log; prefer the oneshot unit.
   - Keep the 08:15 cron as a belt-and-braces second refresh (harmless: the bot
     hot-reloads at 09:00 and `LiveFeed.reconnect()` is self-healing as of `588befd`).
   - TOTP refresh needs the clock to be right at boot — confirm `chrony`/`systemd-timesyncd`
     is active (TOTP drift = login failure).
2. **Make shutdown clean.** `systemctl stop trader` sends SIGTERM; confirm `main.py`
   handles it (flush, `feed.stop()`, close SQLite). Add `TimeoutStopSec=30` to the unit.
   Post-market (15:35) must have completed — a 16:00 stop leaves 25 min; do not move
   the stop earlier than 15:45.
3. **Schedule.** Amazon EventBridge Scheduler, two rules on the instance id, timezone
   `Asia/Kolkata`, `cron(0 7 ? * MON-FRI *)` → `ec2:StartInstances`,
   `cron(0 16 ? * MON-FRI *)` → `ec2:StopInstances`. Needs a small IAM role for the
   scheduler. Free tier for EventBridge Scheduler covers this many invocations
   indefinitely.
   - Holiday skipping (later, optional): a Lambda that reads the NSE holiday list and
     skips the 07:00 start, or simply pre-seed one-off "disable" rules per holiday.
     Not worth it in v1 (~$0.06/holiday-day).
4. **Verify the EIP survives stop/start.** It does for EIPs (not for auto-assigned
   IPs) — check once after the first cycle that `public-ipv4` metadata is unchanged
   and Kite login/orders still work.
5. **Dashboard while stopped.** The Tailscale node is off overnight → dashboard
   unreachable 16:00–07:00. Options: (a) accept; (b) have post-market write a static
   HTML snapshot of `/` to S3 (public-read, or behind a signed URL) so the day's
   closing state is viewable on the phone. Start with (a).
6. **Daily restart consequences** (this reverts the weekly-restart direction chosen for
   retrain cadence — see memory `project_weekly_restart_architecture`):
   - Live LRExtrema retrains from warm-up every morning; ~25 live bars/day of live
     cadence. Either accept (the 09:00 warm-up already replays 400 d of candles so the
     model is not "cold", only its live-tail is) or persist per-stock model/position
     state across restarts. Decide after observing a week of Phase 1.
   - The 2026-08-28 reconnect bug class is moot here (fresh process + fresh token
     each morning), but keep the fix — it protects the manual-restart-at-night case.
7. **Rollback:** disable the two scheduler rules; the box is back to 24/7 with no other
   change.

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
- Is `main.py`'s SIGTERM handling actually clean today, or does the 60 s
  `Restart=always` mask a hard kill? Check before Phase 1 step 2.
- Do we want the S3 snapshot dashboard (Phase 1 step 5b) at all, or is the phone check
  only ever during market hours?

## Not doing

- Lambda / Fargate / spot redesigns — the WebSocket tick stream and tick-speed stops
  need a long-lived process; spot interruption during a session is unacceptable.
- Moving off AWS — the SEBI-registered static IP is an AWS Elastic IP.
- Shrinking storage as a goal — EBS is ~$1.7/mo; only take the 8 GB volume as a free
  side-effect of the Phase 2 rebuild.
