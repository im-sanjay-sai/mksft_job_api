#!/usr/bin/env python3
"""Poll Microsoft Careers and print new matching US software-engineering jobs."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


BASE_URL = "https://apply.careers.microsoft.com"
SEARCH_ENDPOINT = f"{BASE_URL}/api/pcsx/search"
DEFAULT_KEYWORD = "software engineer"
DEFAULT_LOCATION = "United States"
DEFAULT_INTERVAL_MINUTES = 15
DEFAULT_MAX_PAGES = 10
DEFAULT_STOP_AFTER_SEEN_PAGES = 3
DEFAULT_WEBHOOK_MODE = "generic"
DEFAULT_OPENCLAW_HOOK_NAME = "Microsoft Jobs"
DEFAULT_OPENCLAW_WAKE_MODE = "now"
DEFAULT_OPENCLAW_TIMEOUT_SECONDS = 120
PAGE_SIZE = 10
USER_AGENT = "Mozilla/5.0 (compatible; microsoft-job-watcher/1.0)"


@dataclass(frozen=True)
class JobSummary:
    job_id: str
    display_job_id: str
    title: str
    locations: tuple[str, ...]
    standardized_locations: tuple[str, ...]
    department: str
    posted_ts: int | None
    position_path: str

    @property
    def url(self) -> str:
        return urllib.parse.urljoin(BASE_URL, self.position_path)


@dataclass(frozen=True)
class JobDetail:
    title: str
    description: str
    date_posted: str
    url: str


@dataclass(frozen=True)
class MatchResult:
    job: JobSummary
    detail: JobDetail
    years: tuple[int, ...]
    year_snippets: tuple[str, ...]
    keyword_found_in: str


class WebhookDeliveryError(RuntimeError):
    """Raised when a webhook endpoint does not accept a match payload."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def http_get_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def http_get_json(url: str, params: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    text = http_get_text(f"{url}?{query}", timeout=timeout)
    return json.loads(text)


def http_post_json(
    url: str,
    payload: dict[str, Any],
    timeout: int,
    headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    request_headers = {
        "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            if response.status >= 300:
                raise WebhookDeliveryError(
                    f"webhook POST returned HTTP {response.status}"
                )
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise WebhookDeliveryError(
            f"webhook POST returned HTTP {exc.code}{suffix}"
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise WebhookDeliveryError(f"webhook POST failed: {exc}") from exc


def init_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id TEXT PRIMARY KEY,
            first_seen_utc TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            matched INTEGER NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def reset_cache(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def has_seen(connection: sqlite3.Connection, job_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM seen_jobs WHERE job_id = ? LIMIT 1",
        (job_id,),
    ).fetchone()
    return row is not None


def mark_seen(connection: sqlite3.Connection, job: JobSummary, matched: bool) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO seen_jobs (job_id, first_seen_utc, title, url, matched)
        VALUES (?, ?, ?, ?, ?)
        """,
        (job.job_id, utc_now(), job.title, job.url, 1 if matched else 0),
    )
    connection.commit()


def parse_job_summary(raw: dict[str, Any]) -> JobSummary | None:
    job_id = raw.get("id")
    title = raw.get("name")
    position_path = raw.get("positionUrl")
    if not job_id or not title or not position_path:
        return None

    return JobSummary(
        job_id=str(job_id),
        display_job_id=str(raw.get("displayJobId") or raw.get("atsJobId") or ""),
        title=str(title),
        locations=tuple(str(value) for value in raw.get("locations") or ()),
        standardized_locations=tuple(
            str(value) for value in raw.get("standardizedLocations") or ()
        ),
        department=str(raw.get("department") or ""),
        posted_ts=int(raw["postedTs"]) if raw.get("postedTs") else None,
        position_path=str(position_path),
    )


def is_us_job(job: JobSummary) -> bool:
    if any(
        location == "US" or location.endswith(", US")
        for location in job.standardized_locations
    ):
        return True
    return any(location.startswith("United States") for location in job.locations)


def fetch_search_page(start: int, keyword: str, location: str, timeout: int) -> list[JobSummary]:
    payload = http_get_json(
        SEARCH_ENDPOINT,
        params={
            "domain": "microsoft.com",
            "query": keyword,
            "location": location,
            "start": start,
            "sort_by": "timestamp",
        },
        timeout=timeout,
    )
    positions = ((payload.get("data") or {}).get("positions") or [])
    jobs = [parse_job_summary(position) for position in positions]
    return [job for job in jobs if job is not None]


def fetch_job_detail(job: JobSummary, timeout: int) -> JobDetail:
    page = http_get_text(job.url, timeout=timeout)
    data = extract_json_ld(page)
    if data:
        return JobDetail(
            title=str(data.get("title") or job.title),
            description=clean_text(str(data.get("description") or "")),
            date_posted=str(data.get("datePosted") or ""),
            url=str(data.get("url") or job.url).replace("http://", "https://"),
        )

    return JobDetail(
        title=extract_meta_content(page, "og:title") or job.title,
        description=clean_text(extract_meta_content(page, "description") or ""),
        date_posted="",
        url=job.url,
    )


def extract_json_ld(page: str) -> dict[str, Any] | None:
    match = re.search(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    raw = html.unescape(match.group(1).strip())
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_meta_content(page: str, name: str) -> str:
    escaped_name = re.escape(name)
    patterns = (
        rf'<meta[^>]+name=["\']{escaped_name}["\'][^>]+content=["\']([^"\']*)["\']',
        rf'<meta[^>]+property=["\']{escaped_name}["\'][^>]+content=["\']([^"\']*)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(html.unescape(match.group(1)))
    return ""


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def keyword_location(title: str, description: str, keyword: str) -> str | None:
    phrase = keyword.lower()
    title_hit = phrase in title.lower()
    description_hit = phrase in description.lower()
    if title_hit and description_hit:
        return "title+description"
    if title_hit:
        return "title"
    if description_hit:
        return "description"
    return None


def extract_year_requirements(text: str) -> tuple[tuple[int, ...], tuple[str, ...]]:
    years: list[int] = []
    snippets: list[str] = []
    normalized = clean_text(text)

    patterns = (
        r"\b(\d{1,2})\s*\+\s*year(?:s|\(s\))?\b",
        r"\b(\d{1,2})\s*(?:or more|plus)\s+year(?:s|\(s\))?\b",
        r"\b(?:at least|minimum of|min\.?)\s*(\d{1,2})\s+year(?:s|\(s\))?\b",
        r"\b(\d{1,2})\s*-\s*\d{1,2}\s+year(?:s|\(s\))?\b",
        r"\b(\d{1,2})\s+year(?:s|\(s\))?\b",
    )

    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            number = int(match.group(1))
            start = max(0, match.start() - 90)
            end = min(len(normalized), match.end() + 120)
            snippet = normalized[start:end].strip()
            if not is_experience_context(snippet):
                continue
            if number not in years:
                years.append(number)
            if snippet not in snippets:
                snippets.append(snippet)

    return tuple(sorted(years)), tuple(snippets[:3])


def is_experience_context(snippet: str) -> bool:
    lower = snippet.lower()
    context_terms = (
        "experience",
        "software",
        "programming",
        "engineering",
        "development",
        "developing",
        "professional",
        "industry",
    )
    excluded_terms = (
        "valid through",
        "salary",
        "base pay",
        "compensation",
        "benefits",
    )
    return any(term in lower for term in context_terms) and not any(
        term in lower for term in excluded_terms
    )


def posted_time(job: JobSummary) -> str:
    if not job.posted_ts:
        return "unknown"
    return (
        dt.datetime.fromtimestamp(job.posted_ts, tz=dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def webhook_payload(result: MatchResult, max_years: int, all_jobs: bool = False) -> dict[str, Any]:
    job = result.job
    detail = result.detail
    return {
        "event": "microsoft_job_match",
        "sent_at_utc": utc_now(),
        "source": "microsoft-job-watcher",
        "job": {
            "id": job.job_id,
            "display_id": job.display_job_id,
            "title": detail.title or job.title,
            "department": job.department,
            "locations": list(job.locations),
            "standardized_locations": list(job.standardized_locations),
            "posted_utc": posted_time(job),
            "url": detail.url or job.url,
        },
        "match": {
            "matching_mode": "all-jobs" if all_jobs else "keyword+years",
            "keyword_found_in": result.keyword_found_in,
            "years": list(result.years),
            "year_snippets": list(result.year_snippets),
            "accepted_max_years": None if all_jobs else max_years,
        },
    }


def openclaw_agent_message(result: MatchResult, max_years: int, all_jobs: bool = False) -> str:
    job = result.job
    detail = result.detail
    locations = "; ".join(job.standardized_locations or job.locations) or "unknown"
    years = ", ".join(str(value) for value in result.years) if result.years else "unknown"
    if all_jobs:
        why_matched = "matched by all-jobs mode (all US jobs, no keyword or years filter)"
    else:
        why_matched = (
            f"keyword found in {result.keyword_found_in}; parsed years={years}; accepted <= {max_years}"
        )
    snippets = "\n".join(
        f"- {snippet}" for snippet in result.year_snippets
    ) or "- none"

    return (
        "A Microsoft job watcher found a new matching role. "
        "Send a concise alert message in plain text with short bullets. "
        "Include the title, job ID, department, location, posted time, why it matched, and the URL.\n\n"
        f"Title: {detail.title or job.title}\n"
        f"Job ID: {job.display_job_id or job.job_id}\n"
        f"Department: {job.department or 'unknown'}\n"
        f"Locations: {locations}\n"
        f"Posted UTC: {posted_time(job)}\n"
        f"Why it matched: {why_matched}\n"
        f"URL: {detail.url or job.url}\n"
        "Year snippets:\n"
        f"{snippets}"
    )


def openclaw_agent_payload(
    result: MatchResult,
    max_years: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": openclaw_agent_message(
            result,
            max_years=max_years,
            all_jobs=args.all_jobs,
        ),
        "name": args.openclaw_name,
        "wakeMode": args.openclaw_wake_mode,
        "deliver": True,
        "timeoutSeconds": args.openclaw_timeout_seconds,
    }
    if args.openclaw_channel:
        payload["channel"] = args.openclaw_channel
    if args.openclaw_to:
        payload["to"] = args.openclaw_to
    return payload


def parse_webhook_headers(values: Iterable[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        name, separator, header_value = value.partition(":")
        name = name.strip()
        header_value = header_value.strip()
        if not separator or not name or not header_value:
            raise ValueError(
                "--webhook-header must use the format 'Header-Name: value'"
            )
        headers[name] = header_value
    return headers


def resolve_webhook_headers(args: argparse.Namespace) -> dict[str, str]:
    headers = parse_webhook_headers(args.webhook_header or ())
    if not args.webhook_bearer_token_env:
        return headers

    token = os.environ.get(args.webhook_bearer_token_env, "").strip()
    if not token:
        raise ValueError(
            f"environment variable {args.webhook_bearer_token_env!r} is empty or unset"
        )

    headers.setdefault("Authorization", f"Bearer {token}")
    return headers


def evaluate_job(
    job: JobSummary,
    keyword: str,
    max_years: int,
    include_unknown_years: bool,
    timeout: int,
    all_jobs: bool = False,
) -> MatchResult | None:
    detail = fetch_job_detail(job, timeout=timeout)
    years, snippets = extract_year_requirements(detail.description)
    if all_jobs:
        return MatchResult(
            job=job,
            detail=detail,
            years=years,
            year_snippets=snippets,
            keyword_found_in="all-jobs",
        )

    found_in = keyword_location(detail.title or job.title, detail.description, keyword)
    if not found_in:
        return None

    if not years and not include_unknown_years:
        return None
    if years and min(years) > max_years:
        return None

    return MatchResult(
        job=job,
        detail=detail,
        years=years,
        year_snippets=snippets,
        keyword_found_in=found_in,
    )


def fetch_candidates(
    keyword: str,
    location: str,
    max_pages: int,
    timeout: int,
    *,
    connection: sqlite3.Connection | None = None,
    all_jobs: bool = False,
    no_cache: bool = False,
    stop_after_seen_pages: int = 0,
) -> list[JobSummary]:
    candidates: list[JobSummary] = []
    seen_ids: set[str] = set()
    seen_page_streak = 0
    for page_number in range(max_pages):
        start = page_number * PAGE_SIZE
        jobs = fetch_search_page(start, keyword=keyword, location=location, timeout=timeout)
        if not jobs:
            break
        page_has_unseen = False
        page_candidates = 0
        for job in jobs:
            if not is_us_job(job):
                continue
            if job.job_id in seen_ids:
                continue
            seen_ids.add(job.job_id)
            candidates.append(job)
            page_candidates += 1
            if (
                connection is not None
                and all_jobs
                and not no_cache
                and stop_after_seen_pages > 0
                and not has_seen(connection, job.job_id)
            ):
                page_has_unseen = True

        if (
            connection is not None
            and all_jobs
            and not no_cache
            and stop_after_seen_pages > 0
        ):
            if page_candidates == 0:
                break
            if page_has_unseen:
                seen_page_streak = 0
            else:
                seen_page_streak += 1
                if seen_page_streak >= stop_after_seen_pages:
                    break
    return candidates


def run_cycle(args: argparse.Namespace, connection: sqlite3.Connection) -> int:
    print(f"[{utc_now()}] Checking Microsoft Careers...", flush=True)
    search_keyword = "" if args.all_jobs else args.keyword
    candidates = fetch_candidates(
        keyword=search_keyword,
        location=args.location,
        max_pages=args.max_pages,
        timeout=args.timeout,
        connection=connection,
        all_jobs=args.all_jobs,
        no_cache=args.no_cache,
        stop_after_seen_pages=args.stop_after_seen_pages,
    )

    new_count = 0
    match_count = 0
    for job in candidates:
        if has_seen(connection, job.job_id) and not args.no_cache:
            continue

        new_count += 1
        try:
            result = evaluate_job(
                job=job,
                keyword=args.keyword,
                max_years=args.max_years,
                include_unknown_years=args.include_unknown_years,
                timeout=args.timeout,
                all_jobs=args.all_jobs,
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  detail fetch failed for {job.job_id} {job.title}: {exc}", flush=True)
            continue

        if args.detail_delay_seconds > 0:
            time.sleep(args.detail_delay_seconds)
        if not result:
            mark_seen(connection, job, matched=False)
            continue

        if args.webhook_url:
            try:
                payload = (
                    webhook_payload(
                        result,
                        max_years=args.max_years,
                        all_jobs=args.all_jobs,
                    )
                    if args.webhook_mode == "generic"
                    else openclaw_agent_payload(
                        result,
                        max_years=args.max_years,
                        args=args,
                    )
                )
                http_post_json(
                    args.webhook_url,
                    payload,
                    timeout=args.webhook_timeout,
                    headers=args.webhook_headers,
                )
            except WebhookDeliveryError as exc:
                print(
                    f"  webhook delivery failed for {job.job_id} {job.title}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                continue

        mark_seen(connection, job, matched=True)
        match_count += 1
        if not args.no_print_matches:
            print_match(result, max_years=args.max_years, all_jobs=args.all_jobs)

    print(
        f"[{utc_now()}] Done. Candidates={len(candidates)} new_checked={new_count} matches={match_count}",
        flush=True,
    )
    return match_count


def print_match(result: MatchResult, max_years: int, all_jobs: bool = False) -> None:
    job = result.job
    detail = result.detail
    locations = "; ".join(job.standardized_locations or job.locations) or "unknown"
    years = ", ".join(str(value) for value in result.years) if result.years else "unknown"
    years_summary = "not filtered in all-jobs mode" if all_jobs else f"{years} (accepted <= {max_years})"
    print("", flush=True)
    print("NEW MATCH", flush=True)
    print(f"  Title: {detail.title or job.title}", flush=True)
    print(f"  Job ID: {job.display_job_id or job.job_id}", flush=True)
    print(f"  Department: {job.department or 'unknown'}", flush=True)
    print(f"  Locations: {locations}", flush=True)
    print(f"  Posted UTC: {posted_time(job)}", flush=True)
    print(f"  Keyword found in: {result.keyword_found_in}", flush=True)
    print(f"  Parsed years: {years_summary}", flush=True)
    if result.year_snippets:
        print(f"  Years snippet: {result.year_snippets[0]}", flush=True)
    print(f"  URL: {detail.url or job.url}", flush=True)
    print("", flush=True)


def sleep_until_next_cycle(interval_seconds: int) -> None:
    next_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=interval_seconds)
    print(f"Sleeping until {next_time.replace(microsecond=0).isoformat()}", flush=True)
    time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Watch Microsoft Careers for new US software engineer jobs.",
    )
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD)
    parser.add_argument(
        "--all-jobs",
        action="store_true",
        help="Match all United States jobs returned by Microsoft Careers. Disables keyword and years filtering.",
    )
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--max-years", type=int, default=4)
    parser.add_argument("--interval-minutes", type=float, default=DEFAULT_INTERVAL_MINUTES)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument(
        "--stop-after-seen-pages",
        type=int,
        default=DEFAULT_STOP_AFTER_SEEN_PAGES,
        help=(
            "In all-jobs mode, stop scanning after this many consecutive pages "
            "contain only already-seen jobs. Use 0 to disable this optimization."
        ),
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--detail-delay-seconds", type=float, default=0.25)
    parser.add_argument(
        "--webhook-url",
        default="",
        help=(
            "POST each new match to this HTTP(S) webhook URL. "
            "Use --webhook-mode generic for the native watcher payload, or "
            "--webhook-mode openclaw-agent for OpenClaw /hooks/agent."
        ),
    )
    parser.add_argument(
        "--webhook-mode",
        choices=("generic", "openclaw-agent"),
        default=DEFAULT_WEBHOOK_MODE,
        help=(
            "Webhook payload shape. generic sends the watcher's structured JSON. "
            "openclaw-agent sends an OpenClaw /hooks/agent payload that can deliver alerts to chat."
        ),
    )
    parser.add_argument(
        "--webhook-timeout",
        type=int,
        default=15,
        help="Webhook POST timeout in seconds. Default: 15.",
    )
    parser.add_argument(
        "--webhook-header",
        action="append",
        default=None,
        help=(
            "Extra webhook HTTP header, formatted as 'Header-Name: value'. Repeatable. "
            "For OpenClaw hooks, use this for Authorization: Bearer <token>."
        ),
    )
    parser.add_argument(
        "--webhook-bearer-token-env",
        default="",
        help=(
            "Environment variable that holds a bearer token to inject as an "
            "Authorization header at runtime. Useful for long-running services "
            "so the token is not exposed in argv."
        ),
    )
    parser.add_argument(
        "--openclaw-name",
        default=DEFAULT_OPENCLAW_HOOK_NAME,
        help="OpenClaw hook name used in /hooks/agent payloads. Default: Microsoft Jobs.",
    )
    parser.add_argument(
        "--openclaw-channel",
        default="",
        help="OpenClaw delivery channel when --webhook-mode openclaw-agent is used (for example: telegram).",
    )
    parser.add_argument(
        "--openclaw-to",
        default="",
        help="OpenClaw delivery recipient when --webhook-mode openclaw-agent is used.",
    )
    parser.add_argument(
        "--openclaw-wake-mode",
        choices=("now", "next-heartbeat"),
        default=DEFAULT_OPENCLAW_WAKE_MODE,
        help="OpenClaw wake mode for /hooks/agent payloads. Default: now.",
    )
    parser.add_argument(
        "--openclaw-timeout-seconds",
        type=int,
        default=DEFAULT_OPENCLAW_TIMEOUT_SECONDS,
        help="Agent timeoutSeconds value for OpenClaw /hooks/agent payloads. Default: 120.",
    )
    parser.add_argument(
        "--no-print-matches",
        action="store_true",
        help="Do not print full match details; useful when a webhook handles alerts.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).with_name("seen_jobs.sqlite3"),
        help="SQLite cache path.",
    )
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore seen-cache reads. Useful for testing; still writes seen rows.",
    )
    parser.add_argument(
        "--reset-cache",
        action="store_true",
        help="Delete the seen-cache before starting.",
    )
    parser.add_argument(
        "--include-unknown-years",
        action="store_true",
        help="Include jobs when no years-of-experience phrase can be parsed.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.interval_minutes <= 0:
        raise ValueError("--interval-minutes must be greater than 0")
    if args.max_pages <= 0:
        raise ValueError("--max-pages must be greater than 0")
    if args.stop_after_seen_pages < 0:
        raise ValueError("--stop-after-seen-pages cannot be negative")
    if args.max_years < 0:
        raise ValueError("--max-years cannot be negative")
    if not args.all_jobs and not args.keyword.strip():
        raise ValueError("--keyword cannot be empty")
    if args.webhook_timeout <= 0:
        raise ValueError("--webhook-timeout must be greater than 0")
    if args.openclaw_timeout_seconds <= 0:
        raise ValueError("--openclaw-timeout-seconds must be greater than 0")
    if args.webhook_url:
        parsed = urllib.parse.urlparse(args.webhook_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("--webhook-url must be an http or https URL")
    if bool(args.openclaw_channel) != bool(args.openclaw_to):
        raise ValueError(
            "--openclaw-channel and --openclaw-to must be used together"
        )
    parse_webhook_headers(args.webhook_header or ())


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        args.webhook_headers = resolve_webhook_headers(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.reset_cache:
        reset_cache(args.db)

    connection = init_db(args.db)
    interval_seconds = int(args.interval_minutes * 60)

    while True:
        try:
            run_cycle(args, connection)
        except KeyboardInterrupt:
            print("\nStopped.", flush=True)
            return 130
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"[{utc_now()}] Check failed: {exc}", file=sys.stderr, flush=True)

        if args.once:
            return 0
        sleep_until_next_cycle(interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
