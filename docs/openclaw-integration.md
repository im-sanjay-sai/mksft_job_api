# OpenClaw Integration

This project integrates with OpenClaw through the HTTP webhook gateway. It does
not use an OpenClaw Python SDK.

## Flow

1. `microsoft_job_watcher.py` polls Microsoft Careers for broad United States
   job postings and filters locally on posted age plus software/AI role
   keywords.
2. For each new match, the watcher builds a webhook payload.
3. In default `generic` mode, the watcher sends its native JSON payload.
4. In `openclaw-agent` mode, the watcher sends an OpenClaw `/hooks/agent`
   payload to the configured webhook URL.
5. OpenClaw runs an isolated agent turn and can deliver the agent response to a
   configured channel such as Telegram.

## Payload

`openclaw-agent` mode sends these OpenClaw fields:

- `message`: prompt containing instructions for the independent OpenClaw agent,
  job title, job ID, department, location, posted time in Pacific/local
  timezone, match reason, and URL. The prompt tells the agent to alert only on
  clearly technical engineering/developer roles, skip product/program/project
  manager and other non-engineering roles with `HEARTBEAT_OK`, and omit UTC time.
- `name`: hook display name. Default: `Microsoft Jobs`.
- `agentId`: dedicated OpenClaw agent ID. Default: `microsoft-jobs`.
- `sessionKey`: OpenClaw session key. Default: `hook:microsoft-jobs`, or
  `hook:microsoft-job:<job_id>` when `--openclaw-session-per-job` is used.
- `wakeMode`: OpenClaw wake mode. Default: `now`.
- `deliver`: always `true` so OpenClaw can deliver the agent response.
- `timeoutSeconds`: agent run timeout. Default: `120`.
- `channel`: optional delivery channel, for example `telegram`.
- `to`: optional delivery recipient, for example a Telegram user ID.

The bearer token is not stored in the payload. Use
`--webhook-bearer-token-env OPENCLAW_HOOKS_TOKEN` so the watcher reads the token
from the environment at runtime and sends `Authorization: Bearer <token>`.

The independent agent instruction sent in `message` is:

```text
You are the independent Microsoft jobs alert agent. Use only the job details
below. Send an alert only for clearly technical engineering roles, such as
Software Engineer, SDE, SWE, software developer, AI engineer, applied engineer,
applied scientist, machine learning engineer, platform engineer, backend
engineer, frontend engineer, full-stack engineer, or data engineer. Ignore
product manager, program manager, project manager, business development, sales,
marketing, design, support, operations, recruiting, and other non-engineering
roles even if they mention AI, ML, software, or platforms. If the role is not
clearly an engineering/developer role, reply exactly HEARTBEAT_OK and nothing
else. For accepted roles, produce one concise Telegram-ready plain-text alert,
avoid commentary about the watcher, and do not include UTC time. Use the
provided local posted time exactly as the posted time. Include the title, job ID,
department, location, match reason, and URL.
```

## Runtime Command

Example OpenClaw + Telegram command:

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

The local deployment can run this command through a user or system service. Keep
the hook token in an environment file, not in the service command line.

## Source Map

- `microsoft_job_watcher.py`: builds generic and OpenClaw payloads, resolves
  webhook headers, and posts matches.
- `systemd/microsoft-job-watcher.service`: deployable service template.
- OpenClaw `POST /hooks/agent`: accepts `message`, `name`, `agentId`,
  `sessionKey`, `wakeMode`, `deliver`, `channel`, `to`, and `timeoutSeconds`;
  runs an isolated agent turn; and can deliver the agent response to the
  configured channel.
