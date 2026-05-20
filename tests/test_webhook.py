import json
import unittest
from unittest import mock

from microsoft_job_watcher import (
    JobDetail,
    JobSummary,
    MatchResult,
    http_post_json,
    parse_webhook_headers,
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
        years=(2,),
        year_snippets=("2+ years software engineering experience.",),
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
        payload = webhook_payload(sample_match(), max_years=4)

        self.assertEqual(payload["event"], "microsoft_job_match")
        self.assertEqual(payload["source"], "microsoft-job-watcher")
        self.assertEqual(payload["job"]["id"], "abc123")
        self.assertEqual(payload["job"]["title"], "Software Engineer II")
        self.assertEqual(payload["match"]["years"], [2])
        self.assertEqual(payload["match"]["accepted_max_years"], 4)

    def test_parses_repeatable_headers(self) -> None:
        headers = parse_webhook_headers(
            ("Authorization: Bearer token", "X-Agent: openclaw")
        )

        self.assertEqual(headers["Authorization"], "Bearer token")
        self.assertEqual(headers["X-Agent"], "openclaw")

    def test_rejects_bad_header_format(self) -> None:
        with self.assertRaises(ValueError):
            parse_webhook_headers(("Authorization Bearer token",))

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


if __name__ == "__main__":
    unittest.main()
