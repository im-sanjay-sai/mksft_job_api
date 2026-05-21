import datetime as dt
import tempfile
import unittest
from pathlib import Path

from microsoft_job_watcher import (
    DEFAULT_KEYWORDS,
    JobSummary,
    full_scan_due,
    init_db,
    keyword_match,
    mark_seen,
    parse_keywords,
    seen_match_status,
    set_state,
)


class FilterTest(unittest.TestCase):
    def test_default_keywords_cover_software_and_ai_roles(self) -> None:
        keywords = parse_keywords(None)

        self.assertIn("software engineer", keywords)
        self.assertIn("software engineering", keywords)
        self.assertIn("ai engineer", keywords)
        self.assertIn("artificial intelligence", keywords)
        self.assertEqual(keywords, DEFAULT_KEYWORDS)

    def test_parses_repeatable_and_comma_separated_keywords(self) -> None:
        keywords = parse_keywords(("software engineer, ai engineer", "SWE"))

        self.assertEqual(keywords, ("software engineer", "ai engineer", "SWE"))

    def test_matches_title_or_description_keywords(self) -> None:
        match = keyword_match(
            title="AI Engineer",
            description="Build a software engineering platform.",
            keywords=("ai engineer", "software engineering"),
        )

        self.assertEqual(match, ("title+description", ("ai engineer", "software engineering")))

    def test_full_scan_is_due_when_missing_or_stale(self) -> None:
        now = dt.datetime(2026, 5, 20, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            connection = init_db(Path(directory) / "seen.sqlite3")

            self.assertTrue(full_scan_due(connection, 24, now=now))

            set_state(
                connection,
                "last_full_scan_utc",
                (now - dt.timedelta(hours=23)).isoformat(),
            )
            self.assertFalse(full_scan_due(connection, 24, now=now))

            set_state(
                connection,
                "last_full_scan_utc",
                (now - dt.timedelta(hours=25)).isoformat(),
            )
            self.assertTrue(full_scan_due(connection, 24, now=now))

    def test_seen_cache_can_upgrade_rejected_job_to_matched(self) -> None:
        job = JobSummary(
            job_id="abc123",
            display_job_id="1720000",
            title="Data Engineer",
            locations=("United States",),
            standardized_locations=("Redmond, WA, US",),
            department="Engineering",
            posted_ts=1_700_000_000,
            position_path="/us/en/job/abc123/data-engineer",
        )
        with tempfile.TemporaryDirectory() as directory:
            connection = init_db(Path(directory) / "seen.sqlite3")

            mark_seen(connection, job, matched=False)
            self.assertFalse(seen_match_status(connection, job.job_id))

            mark_seen(connection, job, matched=True)
            self.assertTrue(seen_match_status(connection, job.job_id))

            mark_seen(connection, job, matched=False)
            self.assertTrue(seen_match_status(connection, job.job_id))


if __name__ == "__main__":
    unittest.main()
