# Microsoft Job Watcher

Small Python watcher for Microsoft Careers. It polls every 15 minutes by
default, looks only at United States postings, and reports new jobs where:

- `software engineer` appears in the title or job description
- the parsed experience requirement has a minimum value less than or equal to 4 years

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
python3 microsoft_job_watcher.py --include-unknown-years
python3 microsoft_job_watcher.py --webhook-url http://127.0.0.1:8787/matches --no-print-matches
python3 microsoft_job_watcher.py --all-jobs --include-unknown-years --max-pages 200 --stop-after-seen-pages 3 --webhook-url http://127.0.0.1:18789/hooks/agent --webhook-mode openclaw-agent --webhook-bearer-token-env OPENCLAW_HOOKS_TOKEN --openclaw-channel telegram --openclaw-to YOUR_TELEGRAM_USER_ID --no-print-matches
python3 microsoft_job_watcher.py --reset-cache --once
```

Options:

- `--interval-minutes`: poll interval. Default: `15`.
- `--max-pages`: number of Microsoft search pages to read. Microsoft returns
  10 jobs per page. Default: `10`.
- `--stop-after-seen-pages`: in `--all-jobs` mode, stop after this many
  consecutive pages contain only already-seen jobs. Default: `3`. Use `0` to
  disable this optimization.
- `--max-years`: max acceptable years of experience. Default: `4`.
- `--keyword`: keyword or phrase to match in title/description. Default:
  `software engineer`.
- `--all-jobs`: match all United States jobs returned by Microsoft Careers.
  This disables keyword and years filtering.
- `--webhook-url`: POST each new match to this HTTP(S) endpoint as JSON.
- `--webhook-mode`: `generic` or `openclaw-agent`. Default: `generic`.
- `--webhook-timeout`: webhook timeout in seconds. Default: `15`.
- `--webhook-header`: extra webhook HTTP header in `Header-Name: value`
  format. Repeat this option for multiple headers.
- `--webhook-bearer-token-env`: environment variable name containing a bearer
  token to inject as the `Authorization` header at runtime.
- `--openclaw-name`: name shown in OpenClaw `/hooks/agent` runs. Default:
  `Microsoft Jobs`.
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
- `--include-unknown-years`: report jobs even when the script cannot find an
  experience requirement. Default is conservative and excludes unknown years.
- `--reset-cache`: delete the seen-job cache before running.

## Webhook payload

When `--webhook-url` is set, each new match is POSTed as JSON:

```json
{
  "event": "microsoft_job_match",
  "sent_at_utc": "2026-05-20T18:00:00+00:00",
  "source": "microsoft-job-watcher",
  "job": {
    "id": "abc123",
    "display_id": "1720000",
    "title": "Software Engineer II",
    "department": "Engineering",
    "locations": ["United States"],
    "standardized_locations": ["Redmond, WA, US"],
    "posted_utc": "2026-05-20T17:00:00+00:00",
    "url": "https://apply.careers.microsoft.com/us/en/job/abc123/software-engineer"
  },
  "match": {
    "keyword_found_in": "title+description",
    "years": [2],
    "year_snippets": ["2+ years software engineering experience."],
    "accepted_max_years": 4
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
  --all-jobs \
  --include-unknown-years \
  --max-pages 200 \
  --stop-after-seen-pages 3 \
  --webhook-url http://127.0.0.1:18789/hooks/agent \
  --webhook-mode openclaw-agent \
  --webhook-bearer-token-env OPENCLAW_HOOKS_TOKEN \
  --openclaw-channel telegram \
  --openclaw-to YOUR_TELEGRAM_USER_ID \
  --no-print-matches
```

In `openclaw-agent` mode, the watcher sends an OpenClaw-compatible payload that
asks the agent to deliver a concise job alert into the configured chat channel.
This is the safer option for services because the hook token stays in the
environment instead of showing up in process arguments.

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

## Notes on the years filter

Microsoft descriptions are prose, not a strict structured field. The script
extracts phrases like `2+ years software industry experience` and accepts the
job when the minimum parsed years value is less than or equal to `--max-years`.
This catches common Microsoft phrasing such as:

- Master's degree and 1+ years
- Bachelor's degree and 2+ years
- 2+ years programming experience

If a posting has no parseable years requirement, it is skipped unless
`--include-unknown-years` is set.
