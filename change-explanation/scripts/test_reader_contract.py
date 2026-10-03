"""Reader-facing provenance, source navigation, and compatibility checks."""

from html.parser import HTMLParser
import unittest

import report


class ReaderPage(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = []
        self.words = []
        self.line_numbers = []
        self.in_line_number = False
        self.in_noncontent = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("style", "script"):
            self.in_noncontent = True
        if tag == "a":
            self.hrefs.append(attrs.get("href", ""))
        if tag == "span" and "code-lineno" in attrs.get("class", "").split():
            self.in_line_number = True

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.in_noncontent = False
        if tag == "span":
            self.in_line_number = False

    def handle_data(self, value):
        if self.in_noncontent:
            return
        self.words.append(value)
        if self.in_line_number and value.strip().isdigit():
            self.line_numbers.append(int(value.strip()))

    @property
    def text(self):
        return " ".join(self.words)


class ReaderContractTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "version": 1,
            "mode": "review",
            "title": "Retry eligible failures",
            "summary": "Transient failures gain a bounded retry; successful requests keep their current behavior.",
            "context": {"problem": "Eligible failures currently end the request.", "baseline": "base-sha to head-sha"},
            "changes": [{"id": "retry", "title": "Retry eligible failures", "status": "changed",
                         "description": "Eligible failures now retry once.", "why": "Recover from temporary failures."}],
            "impact": [{"change": "retry", "description": "Eligible requests can recover on the second attempt.", "basis": "inferred"}],
        }

    def errors(self):
        return [item for item in report.validate(self.data) if item["level"] == "error"]

    def test_small_change_needs_no_redundant_narrative_or_impact(self):
        del self.data["context"]["problem"]
        del self.data["changes"][0]["why"]
        del self.data["impact"]
        self.assertFalse(self.errors())
        html = report.render(self.data)
        self.assertNotIn('id="impact"', html)
        self.assertNotIn('href="#impact"', html)
        self.assertNotIn('class="why"', html)
        self.assertIn("base-sha to head-sha", ReaderPage(html).text)

    def test_visual_and_code_can_explain_themselves(self):
        self.data["changes"][0]["visual"] = {
            "template": "flow", "nodes": [{"id": "call", "label": "Call", "status": "changed"}], "edges": [],
        }
        self.data["changes"][0]["code"] = {"before": "call()", "after": "retry(call)"}
        self.assertFalse(self.errors())
        html = report.render(self.data)
        self.assertNotIn("<figcaption>", html)
        self.assertNotIn('class="code-summary"', html)
        self.assertIn('aria-label="Process flow"', html)
        self.assertIn("Excerpt lines", ReaderPage(html).text)

    def test_motion_meaning_is_explained_once_per_page(self):
        visual = {"template": "flow", "nodes": [
            {"id": "call", "label": "Call", "status": "unchanged"},
            {"id": "retry", "label": "Retry", "status": "new"}],
            "edges": [{"from": "call", "to": "retry", "label": "Eligible failure", "status": "new", "transport": "flow", "animate": True}]}
        self.data["context"]["visual"] = visual
        self.data["changes"][0]["visual"] = visual
        html = report.render(self.data)
        self.assertEqual(html.count('id="motion-key"'), 1)
        self.assertEqual(html.count('aria-describedby="motion-key"'), 2)
        self.assertNotIn('class="packet-guidance"', html)

    def evidence(self, **extra):
        item = {"label": "Inspected retry eligibility", "file": "src/client.py", "line": 42,
                "revision": "head-sha", **extra}
        self.data["changes"][0]["evidence"] = ["Existing plain-text verification remains supported.", item]
        return item

    def test_structured_evidence_keeps_legacy_strings_and_source_identity(self):
        url = "https://example.com/repo/blob/head-sha/src/client.py#L42"
        self.evidence(url=url, detail="Inspected eligibility only; no live-server test was run.")
        self.assertFalse(self.errors())
        page = ReaderPage(report.render(self.data))
        self.assertIn(url, page.hrefs)
        for expected in ("Existing plain-text verification", "src/client.py", "42", "head-sha", "no live-server test"):
            self.assertIn(expected, page.text)

    def test_absolute_workspace_source_is_linked_without_inventing_a_remote(self):
        self.evidence(file="C:/workspace/My Project/client.py")
        self.assertFalse(self.errors())
        page = ReaderPage(report.render(self.data))
        self.assertTrue(any(href.startswith("file:///C:/workspace/My%20Project/client.py") for href in page.hrefs), page.hrefs)
        self.assertFalse(any(href.startswith(("http:", "https:")) for href in page.hrefs))

    def test_historical_local_reference_discloses_current_working_copy(self):
        self.evidence(file="C:/workspace/client.py", revision="historical-sha")
        page = ReaderPage(report.render(self.data))
        self.assertIn("Local working copy", page.text)
        self.assertIn("historical-sha", page.text)

    def test_relative_source_remains_visible_without_a_fabricated_link(self):
        self.evidence()
        self.assertFalse(self.errors())
        page = ReaderPage(report.render(self.data))
        self.assertIn("src/client.py", page.text)
        self.assertFalse(any("src/client.py" in href for href in page.hrefs))

    def test_source_urls_reject_executable_or_ambiguous_targets(self):
        for url in ("javascript:alert(1)", "data:text/html,unsafe", "//example.com/file", "src/client.py", "https://example.com/\nfile"):
            with self.subTest(url=url):
                self.evidence(url=url)
                self.assertTrue(any(item["path"].endswith(".url") for item in self.errors()), self.errors())

    def test_supported_source_link_schemes_are_preserved(self):
        for url in ("http://localhost/source#L42", "https://example.com/source#L42", "file:///C:/workspace/client.py",
                    "codex://review?pr=https%3A%2F%2Fexample.com%2Fpr%2F1", "vscode://file/C:/workspace/client.py:42"):
            with self.subTest(url=url):
                self.evidence(url=url)
                self.assertFalse(self.errors())
                self.assertIn(url, ReaderPage(report.render(self.data)).hrefs)

    def test_structured_evidence_requires_a_reader_facing_label(self):
        item = self.evidence()
        del item["label"]
        self.assertTrue(any(item["path"].endswith(".label") for item in self.errors()), self.errors())

    def test_line_numbers_are_positive_integer_source_coordinates(self):
        for line in (0, -2, True, 1.5):
            with self.subTest(line=line):
                self.evidence(line=line)
                self.assertTrue(any(item["path"].endswith(".line") for item in self.errors()), self.errors())

    def test_code_uses_actual_lines_and_visible_revisions(self):
        self.data["changes"][0]["code"] = {
            "summary": "Wrap the call in a bounded retry.", "file": "src/client.py", "language": "python",
            "before": "response = call()\nreturn response", "after": "response = retry(call)\nreturn response",
            "beforeLine": 20, "afterLine": 44, "beforeRevision": "base-sha", "afterRevision": "head-sha",
        }
        self.assertFalse(self.errors())
        page = ReaderPage(report.render(self.data))
        self.assertEqual(page.line_numbers, [20, 21, 44, 45])
        self.assertIn("base-sha", page.text)
        self.assertIn("head-sha", page.text)
        for field in ("beforeLine", "afterLine"):
            for invalid in (0, -1, True):
                with self.subTest(field=field, invalid=invalid):
                    self.data["changes"][0]["code"][field] = invalid
                    self.assertTrue(any(item["path"].endswith("." + field) for item in self.errors()), self.errors())
            self.data["changes"][0]["code"][field] = 1

    def test_comparison_preserves_inspected_working_tree_scope(self):
        self.data["context"]["comparison"] = {
            "base": "base-sha", "head": "head-sha + working tree", "inspectedAt": "2026-10-03T12:00:00+02:00",
            "included": ["staged changes", "unstaged src/client.py"], "excluded": ["untracked scratch.txt"],
        }
        self.assertFalse(self.errors())
        page = ReaderPage(report.render(self.data))
        for expected in ("base-sha", "head-sha + working tree", "2026-10-03", "staged changes", "unstaged src/client.py", "untracked scratch.txt"):
            self.assertIn(expected, page.text)
        del self.data["context"]["comparison"]["head"]
        self.assertTrue(any(item["path"] == "$.context.comparison.head" for item in self.errors()))

    def test_short_edge_labels_are_nonblank_and_bounded(self):
        self.data["changes"][0]["visual"] = {
            "template": "flow", "caption": "Failure eligibility controls the retry branch.",
            "nodes": [{"id": "call", "label": "Call", "status": "changed"}, {"id": "retry", "label": "Retry", "status": "new"}],
            "edges": [{"from": "call", "to": "retry", "label": "The failure is transient and the retry budget remains.", "shortLabel": "Eligible failure", "status": "new"}],
        }
        self.assertFalse(self.errors())
        self.assertIn("Eligible failure", ReaderPage(report.render(self.data)).text)
        for invalid in (" ", "x" * 33):
            with self.subTest(label=invalid):
                self.data["changes"][0]["visual"]["edges"][0]["shortLabel"] = invalid
                self.assertTrue(any(item["path"].endswith(".shortLabel") for item in self.errors()), self.errors())

    def test_missing_summary_warns_without_breaking_legacy_reports(self):
        del self.data["summary"]
        diagnostics = report.validate(self.data)
        self.assertFalse(self.errors())
        self.assertTrue(any(item["path"] == "$.summary" and item["level"] == "warning" for item in diagnostics), diagnostics)


if __name__ == "__main__":
    unittest.main()
