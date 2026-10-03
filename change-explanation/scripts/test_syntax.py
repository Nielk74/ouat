"""Standalone syntax enhancement and safe source-link rendering."""

from html.parser import HTMLParser
import json
import unittest

import report


class SyntaxInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.external, self.links, self.code_lines = [], [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs.get("id"))
            if "src" in attrs:
                self.external.append(attrs["src"])
        if tag == "a":
            self.links.append(attrs.get("href"))
        if "code-line" in attrs.get("class", "").split():
            self.code_lines.append(attrs["class"])


class SyntaxTests(unittest.TestCase):
    def test_code_reports_embed_only_the_bundled_enhancement(self):
        data = json.loads((report.ASSETS / "example-system.json").read_text(encoding="utf-8"))
        page = SyntaxInspector()
        page.feed(report.render(data))
        self.assertEqual(page.scripts, ["syntax-highlighter"])
        self.assertFalse(page.external)
        for change in data["changes"]:
            change.pop("code", None)
        page = SyntaxInspector()
        page.feed(report.render(data))
        self.assertFalse(page.scripts, "Reports without code need no highlighting runtime")

    def test_excerpt_retains_diff_lines_and_safe_language_hints(self):
        code = {"file": r"C:\project\my file.ts", "language": 'typescript" onmouseover="bad()',
                "before": "const count = 1;\n\nreturn count;", "after": "const count = 2;\n\nreturn count;"}
        rendered = report.render_code(code, "review")
        page = SyntaxInspector()
        page.feed(rendered)
        self.assertIn("file:///C:/project/my%20file.ts", page.links)
        self.assertEqual(page.code_lines, ["code-line deleted", "code-line context", "code-line context",
                                          "code-line added", "code-line context", "code-line context"])
        self.assertIn('data-file="C:\\project\\my file.ts"', rendered)
        self.assertIn('data-language="typescript&quot; onmouseover=&quot;bad()"', rendered)
        self.assertNotIn(' onmouseover="', rendered)
        self.assertIn('class="code-text">const count = 1;</span>', rendered)

    def test_relative_paths_do_not_fabricate_source_links(self):
        page = SyntaxInspector()
        page.feed(report.render_code({"file": "fictional/example.rs", "before": "", "after": "fn main() {}"}, "plan"))
        self.assertFalse(page.links)


if __name__ == "__main__":
    unittest.main()
