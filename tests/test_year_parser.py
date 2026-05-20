import unittest

from microsoft_job_watcher import extract_year_requirements


class YearParserTest(unittest.TestCase):
    def test_parses_common_microsoft_year_phrases(self) -> None:
        text = (
            "Master's Degree in Computer Science AND 1+ years software industry "
            "experience OR Bachelor's Degree AND 2+ years software industry "
            "experience. 1+ year(s) experience in a collaborative environment."
        )

        years, snippets = extract_year_requirements(text)

        self.assertEqual(years, (1, 2))
        self.assertTrue(snippets)

    def test_ignores_compensation_years(self) -> None:
        text = "Base pay range may vary. Benefits are reviewed every 2 years."

        years, _ = extract_year_requirements(text)

        self.assertEqual(years, ())


if __name__ == "__main__":
    unittest.main()
