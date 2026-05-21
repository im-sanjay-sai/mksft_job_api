import json
import unittest
from types import SimpleNamespace
from unittest import mock

from microsoft_job_watcher import (
    JobDetail,
    JobSummary,
    MatchResult,
    fetch_candidates,
    http_post_json,
    openclaw_agent_payload,
    parse_webhook_headers,
    resolve_webhook_headers,
    webhook_payload,
)


def sample_match() -> MatchResult:
    return MatchResult(
        job=JobSummary(
            job_id="abc123",
            display_job_id="1720000",
            title="Software Engineer",
            locations=("United States",),
            standardized_locations=("Redmond, WA, US",),
            department="Engineering",
            posted_ts=1_700_000_000,
            position_path="/us/en/job/abc123/software-engineer",
        ),
        detail=JobDetail(
            title="Software Engineer II",
            description="2+ years software engineering experience.",
            date_posted="2026-05-20",
            url="https://apply.careers.microsoft.com/us/en/job/abc123/software-engineer",
        ),
        matched_keywords=("software engineer", "software engineering"),
        keyword_found_in="title+description",
    )


class FakeResponse:
    status = 204

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return b""


class WebhookTest(unittest.TestCase):
    def test_builds_structured_payload(self) -> None:
        payload = webhook_payload(sample_match())

        self.assertEqual(payload["event"], "microsoft_job_match")
        self.assertNotIn("sent_at_utc", payload)
        self.assertIn("sent_at_local", payload)
        self.assertEqual(payload["sent_timezone"], "America/Los_Angeles")
        self.assertEqual(payload["source"], "microsoft-job-watcher")
        self.assertEqual(payload["job"]["id"], "abc123")
        self.assertEqual(payload["job"]["title"], "Software Engineer II")
        self.assertNotIn("posted_utc", payload["job"])
        self.assertEqual(payload["job"]["posted_local"], "2023-11-14T14:13:20-08:00")
        self.assertEqual(payload["job"]["posted_timezone"], "America/Los_Angeles")
        self.assertEqual(payload["match"]["matching_mode"], "role-keywords")
        self.assertEqual(
            payload["match"]["matched_keywords"],
            ["software engineer", "software engineering"],
        )

    def test_builds_all_jobs_payload(self) -> None:
        payload = webhook_payload(sample_match(), all_jobs=True)

        self.assertEqual(payload["match"]["matching_mode"], "all-jobs")
        self.assertEqual(
            payload["match"]["matched_keywords"],
            ["software engineer", "software engineering"],
        )

    def test_parses_repeatable_headers(self) -> None:
        headers = parse_webhook_headers(
            ("Authorization: Bearer token", "X-Agent: openclaw")
        )

        self.assertEqual(headers["Authorization"], "Bearer token")
        self.assertEqual(headers["X-Agent"], "openclaw")

    def test_rejects_bad_header_format(self) -> None:
        with self.assertRaises(ValueError):
            parse_webhook_headers(("Authorization Bearer token",))

    def test_resolves_bearer_token_from_env(self) -> None:
        args = SimpleNamespace(
            webhook_header=None,
            webhook_bearer_token_env="OPENCLAW_HOOKS_TOKEN",
        )

        with mock.patch.dict("os.environ", {"OPENCLAW_HOOKS_TOKEN": "secret-token"}):
            headers = resolve_webhook_headers(args)

        self.assertEqual(headers["Authorization"], "Bearer secret-token")

    def test_posts_json_payload(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        payload = {"event": "test"}
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            http_post_json(
                "http://127.0.0.1:8787/matches",
                payload,
                timeout=7,
                headers={"X-Test": "yes"},
            )

        request = captured["request"]
        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "http://127.0.0.1:8787/matches")
        self.assertEqual(json.loads(request.data.decode("utf-8")), payload)
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertEqual(request.headers["X-test"], "yes")

    def test_builds_openclaw_agent_payload(self) -> None:
        payload = openclaw_agent_payload(
            sample_match(),
            args=SimpleNamespace(
                all_jobs=False,
                openclaw_name="Microsoft Jobs",
                openclaw_agent_id="microsoft-jobs",
                openclaw_session_key="hook:microsoft-jobs",
                openclaw_session_per_job=False,
                openclaw_wake_mode="now",
                openclaw_timeout_seconds=120,
                openclaw_channel="telegram",
                openclaw_to="1234567890",
                display_timezone="America/Los_Angeles",
            ),
        )

        self.assertEqual(payload["name"], "Microsoft Jobs")
        self.assertEqual(payload["agentId"], "microsoft-jobs")
        self.assertEqual(payload["sessionKey"], "hook:microsoft-jobs")
        self.assertEqual(payload["wakeMode"], "now")
        self.assertTrue(payload["deliver"])
        self.assertEqual(payload["timeoutSeconds"], 120)
        self.assertEqual(payload["channel"], "telegram")
        self.assertEqual(payload["to"], "1234567890")
        self.assertIn("Software Engineer II", payload["message"])
        self.assertIn("Why it matched", payload["message"])
        self.assertIn("Posted America/Los_Angeles", payload["message"])
        self.assertNotIn("Posted UTC", payload["message"])
        self.assertIn("independent Microsoft jobs alert agent", payload["message"])
        self.assertIn("Software Engineer", payload["message"])
        self.assertIn("SDE", payload["message"])
        self.assertIn("applied engineer", payload["message"])
        self.assertIn("product manager", payload["message"])
        self.assertIn("HEARTBEAT_OK", payload["message"])

    def test_builds_openclaw_agent_payload_for_all_jobs(self) -> None:
        payload = openclaw_agent_payload(
            sample_match(),
            args=SimpleNamespace(
                all_jobs=True,
                openclaw_name="Microsoft Jobs",
                openclaw_agent_id="microsoft-jobs",
                openclaw_session_key="hook:microsoft-jobs",
                openclaw_session_per_job=False,
                openclaw_wake_mode="now",
                openclaw_timeout_seconds=120,
                openclaw_channel="telegram",
                openclaw_to="1234567890",
                display_timezone="America/Los_Angeles",
            ),
        )

        self.assertIn("all-jobs mode", payload["message"])

    def test_builds_openclaw_per_job_session_key(self) -> None:
        payload = openclaw_agent_payload(
            sample_match(),
            args=SimpleNamespace(
                all_jobs=False,
                openclaw_name="Microsoft Jobs",
                openclaw_agent_id="microsoft-jobs",
                openclaw_session_key="hook:microsoft-jobs",
                openclaw_session_per_job=True,
                openclaw_wake_mode="now",
                openclaw_timeout_seconds=120,
                openclaw_channel="telegram",
                openclaw_to="1234567890",
                display_timezone="America/Los_Angeles",
            ),
        )

        self.assertEqual(payload["sessionKey"], "hook:microsoft-job:abc123")

    def test_fetch_candidates_stops_after_seen_pages_in_all_jobs_mode(self) -> None:
        pages = {
            0: [
                JobSummary(
                    job_id="seen-1",
                    display_job_id="1",
                    title="Seen Job",
                    locations=("United States",),
                    standardized_locations=("Redmond, WA, US",),
                    department="Engineering",
                    posted_ts=1,
                    position_path="/job/1",
                )
            ],
            10: [
                JobSummary(
                    job_id="unseen-2",
                    display_job_id="2",
                    title="Unseen Job",
                    locations=("United States",),
                    standardized_locations=("Redmond, WA, US",),
                    department="Engineering",
                    posted_ts=2,
                    position_path="/job/2",
                )
            ],
        }

        with mock.patch("microsoft_job_watcher.fetch_search_page", side_effect=lambda start, keyword, location, timeout: pages.get(start, [])), mock.patch(
            "microsoft_job_watcher.has_seen",
            side_effect=lambda connection, job_id: job_id.startswith("seen-"),
        ):
            candidates = fetch_candidates(
                keyword="",
                location="United States",
                max_pages=5,
                timeout=30,
                connection=object(),
                all_jobs=True,
                no_cache=False,
                stop_after_seen_pages=1,
            )

        self.assertEqual([job.job_id for job in candidates], ["seen-1"])


if __name__ == "__main__":
    unittest.main()
