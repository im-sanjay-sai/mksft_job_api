# Microsoft Job Watcher

Small Python watcher for Microsoft Careers. It polls every 15 minutes by
default, fetches broad United States postings, and reports new jobs where one
of the configured software/AI role keywords appears in the title or job
description. By default, alerts are limited to jobs Microsoft says were posted
within the last 2 hours.

Default role keywords:

- `software engineer`
- `software engineering`
- `software developer`
- `software development`
- `ai engineer`
- `ai engineering`
- `artificial intelligence`
- `machine learning`
- `deep learning`
- `ml engineer`
- `coreai`
- `swe`

The script uses the public Microsoft Careers search endpoint and each job's
public detail page. It stores seen job IDs in SQLite so repeat runs do not report
the same job again.

## Requirements

- Linux machine
- Python 3.9 or newer
- Internet access

No Python packages are required.

## Run once

```bash
cd microsoft-job-watcher
python3 microsoft_job_watcher.py --once
```

## Run forever

```bash
cd microsoft-job-watcher
python3 microsoft_job_watcher.py
```

By default it polls every 15 minutes.

## Useful options

```bash
python3 microsoft_job_watcher.py --once --max-pages 20
python3 microsoft_job_watcher.py --interval-minutes 5
python3 microsoft_job_watcher.py --all-jobs --once
python3 microsoft_job_watcher.py --keyword "software engineer" --keyword "ai engineer"
python3 microsoft_job_watcher.py --full-scan-interval-hours 12
python3 microsoft_job_watcher.py --max-posted-age-hours 2
python3 microsoft_job_watcher.py --webhook-url http://127.0.0.1:8787/matches --no-print-matches
python3 microsoft_job_watcher.py --max-pages 200 --stop-after-seen-pages 3 --full-scan-interval-hours 24 --max-posted-age-hours 2 --display-timezone America/Los_Angeles --webhook-url http://127.0.0.1:18789/hooks/agent --webhook-mode openclaw-agent --webhook-bearer-token-env OPENCLAW_HOOKS_TOKEN --openclaw-agent-id microsoft-jobs --openclaw-session-key hook:microsoft-jobs --openclaw-channel telegram --openclaw-to YOUR_TELEGRAM_USER_ID --no-print-matches
python3 microsoft_job_watcher.py --reset-cache --once
```

Options:

- `--interval-minutes`: poll interval. Default: `15`.
- `--max-pages`: number of Microsoft search pages to read. Microsoft returns
  10 jobs per page. Default: `200`.
- `--stop-after-seen-pages`: stop after this many consecutive pages contain
  only already-seen jobs. Default: `3`. Use `0` to disable this optimization.
- `--full-scan-interval-hours`: periodically run a full scan by disabling
  `--stop-after-seen-pages`. Default: `24`. Use `0` to disable full scans.
- `--max-posted-age-hours`: only alert on jobs posted within this many hours.
  Default: `2`. Use `0` to disable the age filter. Jobs without a Microsoft
  posted timestamp are skipped while this filter is enabled.
- `--search-query`: optional Microsoft Careers API query. Default is empty,
  so the watcher fetches broad US results and filters locally.
- `--keyword`: role keyword or phrase to match in title/description. Repeatable
  and comma-separated values are accepted. Defaults are listed above.
- `--all-jobs`: match all United States jobs returned by Microsoft Careers.
  This disables local role keyword filtering.
- `--display-timezone`: timezone used in printed alerts and webhook local
  timestamps. Default: `America/Los_Angeles` for Pacific time.
- `--webhook-url`: POST each new match to this HTTP(S) endpoint as JSON.
- `--webhook-mode`: `generic` or `openclaw-agent`. Default: `generic`.
- `--webhook-timeout`: webhook timeout in seconds. Default: `15`.
- `--webhook-header`: extra webhook HTTP header in `Header-Name: value`
  format. Repeat this option for multiple headers.
- `--webhook-bearer-token-env`: environment variable name containing a bearer
  token to inject as the `Authorization` header at runtime.
- `--openclaw-name`: name shown in OpenClaw `/hooks/agent` runs. Default:
  `Microsoft Jobs`.
- `--openclaw-agent-id`: dedicated OpenClaw `agentId` for `/hooks/agent`
  payloads. Default: `microsoft-jobs`.
- `--openclaw-session-key`: OpenClaw `sessionKey` for `/hooks/agent` payloads.
  Default: `hook:microsoft-jobs`.
- `--openclaw-session-per-job`: use `hook:microsoft-job:<job_id>` as the
  `sessionKey` so each job gets an isolated session.
- `--openclaw-channel`: delivery channel for `openclaw-agent` mode, for example
  `telegram`.
- `--openclaw-to`: delivery recipient for `openclaw-agent` mode, for example a
  Telegram user ID.
- `--openclaw-wake-mode`: OpenClaw wake mode for `openclaw-agent` mode.
  Default: `now`.
- `--openclaw-timeout-seconds`: `timeoutSeconds` passed to OpenClaw
  `/hooks/agent`. Default: `120`.
- `--no-print-matches`: suppress full match details on stdout. Useful when a
  webhook handles alerts.
- `--reset-cache`: delete the seen-job cache before running.
- `--max-years` and `--include-unknown-years`: deprecated compatibility
  options. They are accepted but ignored because experience filtering has been
  removed.

## Webhook payload

When `--webhook-url` is set, each new match is POSTed as JSON:

```json
{
  "event": "microsoft_job_match",
  "sent_at_local": "2026-05-20T11:00:00-07:00",
  "sent_timezone": "America/Los_Angeles",
  "source": "microsoft-job-watcher",
  "job": {
    "id": "abc123",
    "display_id": "1720000",
    "title": "Software Engineer II",
    "department": "Engineering",
    "locations": ["United States"],
    "standardized_locations": ["Redmond, WA, US"],
    "posted_local": "2026-05-20T10:00:00-07:00",
    "posted_timezone": "America/Los_Angeles",
    "url": "https://apply.careers.microsoft.com/us/en/job/abc123/software-engineer"
  },
  "match": {
    "matching_mode": "role-keywords",
    "keyword_found_in": "title+description",
    "matched_keywords": ["software engineer", "software engineering"]
  }
}
```

If webhook delivery fails, the match is not marked as seen. The next polling
cycle will retry it.

## OpenClaw + Telegram

The watcher now supports a native OpenClaw webhook mode. Point it at
`/hooks/agent`, pass your hook token in an `Authorization` header, and tell it
where to deliver alerts.

Detailed integration and runtime notes live in
[`docs/openclaw-integration.md`](docs/openclaw-integration.md).

Example:

```bash
python3 microsoft_job_watcher.py \
  --interval-minutes 15 \
  --max-pages 200 \
  --stop-after-seen-pages 3 \
  --full-scan-interval-hours 24 \
  --max-posted-age-hours 2 \
  --display-timezone America/Los_Angeles \
  --webhook-url http://127.0.0.1:18789/hooks/agent \
  --webhook-mode openclaw-agent \
  --webhook-bearer-token-env OPENCLAW_HOOKS_TOKEN \
  --openclaw-agent-id microsoft-jobs \
  --openclaw-session-key hook:microsoft-jobs \
  --openclaw-channel telegram \
  --openclaw-to YOUR_TELEGRAM_USER_ID \
  --no-print-matches
```

In `openclaw-agent` mode, the watcher sends an OpenClaw-compatible payload that
asks the agent to deliver a concise job alert into the configured chat channel.
The hook message tells the independent OpenClaw agent to use only the provided
job details, alert only on clearly technical engineering/developer roles, skip
product/program/project manager and other non-engineering roles with
`HEARTBEAT_OK`, use the local posted time, and omit UTC time.
This is the safer option for services because the hook token stays in the
environment instead of showing up in process arguments.

## Integration learning

The clean split is:

- This repo is the watcher and outbound webhook sender. It polls Microsoft,
  deduplicates jobs, applies deterministic filters like United States location,
  posted age, and role keywords, then POSTs to OpenClaw.
- OpenClaw is the webhook receiver, agent-turn runner, and delivery layer. The
  `/hooks/agent` endpoint receives the watcher payload, runs an agent turn, and
  can deliver the resulting alert to Telegram.
- Long-term preferences belong on the OpenClaw side when a dedicated agent is
  configured. Examples: which job families to prioritize, how to summarize, and
  when to skip a marginal match.
- Mechanical safety filters belong in this repo. Examples: do not notify for
  jobs older than `--max-posted-age-hours`, do not resend already matched job
  IDs, and keep hook tokens in environment variables.

If a future integration needs dedicated behavior, configure the dedicated
OpenClaw agent first, then have the watcher send that `agentId`. If the watcher
sends a `sessionKey`, OpenClaw must either allow request session keys with safe
prefixes or use its configured default session key.

For a fresh baseline, you can save the current jobs locally (for example
`data/baseline_us_jobs_current.json`) and mark them as seen so only new jobs
listed after that point alert you.

## Run with systemd

Copy the project to a stable location, for example:

```bash
sudo mkdir -p /opt/microsoft-job-watcher
sudo cp microsoft_job_watcher.py /opt/microsoft-job-watcher/
```

Then copy `systemd/microsoft-job-watcher.service` to:

```bash
/etc/systemd/system/microsoft-job-watcher.service
```

Edit the `User`, `Group`, and paths in the service file, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now microsoft-job-watcher
sudo journalctl -u microsoft-job-watcher -f
```

## Notes on filtering

The watcher no longer filters on years of experience. It fetches broad US
results, then checks the title and job description for configured role
keywords. This intentionally favors catching more roles over strict precision.
By default, it suppresses notifications for jobs posted more than 2 hours before
the scan time.

Delivered matches stay suppressed by the SQLite cache. Jobs that were seen but
did not match are allowed to be rechecked, so description edits and keyword
changes can still surface later.

Incremental scans stop after `--stop-after-seen-pages` consecutive pages contain
only already-seen US jobs. Every `--full-scan-interval-hours`, the watcher runs
a full scan of `--max-pages` pages and ignores that shortcut so older/backfilled
postings can still be evaluated. The posted-age filter still prevents old jobs
from notifying during those full scans.
