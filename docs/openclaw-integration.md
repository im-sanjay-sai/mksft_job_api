# OpenClaw Integration

This project integrates with OpenClaw through the HTTP webhook gateway. It does
not use an OpenClaw Python SDK.

## Flow

1. `microsoft_job_watcher.py` polls Microsoft Careers for matching United
   States job postings.
2. For each new match, the watcher builds a webhook payload.
3. In default `generic` mode, the watcher sends its native JSON payload.
4. In `openclaw-agent` mode, the watcher sends an OpenClaw `/hooks/agent`
   payload to the configured webhook URL.
5. OpenClaw runs an isolated agent turn and can deliver the agent response to a
   configured channel such as Telegram.

## Payload

`openclaw-agent` mode sends these OpenClaw fields:

- `message`: prompt containing job title, job ID, department, location, posted
  time, match reason, URL, and year snippets.
- `name`: hook display name. Default: `Microsoft Jobs`.
- `wakeMode`: OpenClaw wake mode. Default: `now`.
- `deliver`: always `true` so OpenClaw can deliver the agent response.
- `timeoutSeconds`: agent run timeout. Default: `120`.
- `channel`: optional delivery channel, for example `telegram`.
- `to`: optional delivery recipient, for example a Telegram user ID.

The bearer token is not stored in the payload. Use
`--webhook-bearer-token-env OPENCLAW_HOOKS_TOKEN` so the watcher reads the token
from the environment at runtime and sends `Authorization: Bearer <token>`.

## Runtime Command

Example OpenClaw + Telegram command:

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

The local deployment can run this command through a user or system service. Keep
the hook token in an environment file, not in the service command line.

## Source Map

- `microsoft_job_watcher.py`: builds generic and OpenClaw payloads, resolves
  webhook headers, and posts matches.
- `systemd/microsoft-job-watcher.service`: deployable service template.
- OpenClaw `POST /hooks/agent`: accepts `message`, `name`, `wakeMode`,
  `deliver`, `channel`, `to`, and `timeoutSeconds`; runs an isolated agent turn;
  and can deliver the agent response to the configured channel.
