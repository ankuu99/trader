# TD-007: Infra cost follow-ups (Phase 1 done; scoped IAM user, Phase 2 t4g, skip NSE holidays)

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

## Infra cost — leaving AWS free tier (raised 2026-08-28) — Phase 1 IMPLEMENTED 2026-09-05 (box off 16:00→06:45 IST; see `infra_cost_plan.md` "As built"). Aug bill $19.18/₹1,660 → expect ~₹900. Later: scoped IAM user for the GitHub secret; Phase 2 (t4g) only worth ~₹180/mo more
- Today: t2.micro x86 (ap-south-1b), 20 GB EBS, Elastic IP 13.202.187.191,
  Tailscale for SSH/dashboard, fail2ban, TOTP cron 08:15 IST. Bot RSS ~254 MB.
  Est. on-demand: ~$9 compute + ~$3.6 public IPv4 (charged since Feb-2024, even
  idle EIP) + ~$1.7 EBS ≈ $14–15/mo.
- Compute is only needed ~07:00–16:00 IST on trading days. Candidate plan (see
  brainstorm in memory `project_infra_cost_plan`): KEEP the Elastic IP — SEBI's
  algo framework mandates a registered static IP (~$3.6/mo fixed, even while the
  box is stopped); move to t4g.micro (arm64), EventBridge Scheduler start 07:00 /
  stop 16:00 Mon–Fri (skip NSE holidays later) → ~$6–7/mo. Non-AWS hosts only
  work if the static IP can move with us (it can't — EIPs are AWS-bound).
- Disk (2026-08-28): 20 GB is just the default root volume; 4.8 GB used — OS
  2.1G /usr, /var 1.4G (journal 470M, snapd 354M, apt/cache 500M), /opt 1.3G
  (venv). market.db is 39 MB (278k candles, 15m back to 2024-07; dead 5m/60m/
  1m cache from Jan–Apr 2026 ≈ 67k rows) + 40 MB of stale .bak files. EBS can't
  shrink in place; an 8 GB volume via snapshot-restore saves ~$1/mo — low value.
- Nightly stop = DAILY restart: (a) TOTP refresh must run at boot BEFORE the
  service (ExecStartPre / systemd ordering), else main.py boots on the expired
  token and crash-loops until 08:15; (b) reverts the weekly-restart retrain
  cadence concern (~25 live bars/day) — needs model-state persistence or accept;
  (c) dashboard unreachable 16:00–07:00; (d) post-market 15:35 must finish before
  stop; (e) the EIP stays attached to the stopped instance so the SEBI-registered
  IP never changes.
