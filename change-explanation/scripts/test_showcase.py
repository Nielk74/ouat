"""Check explorer coverage, real recipes, standalone output, and CLI safety."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import brands
import report


class ShowcaseInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.references, self.assets, self.cards = [], [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "use":
            self.references.append(attrs.get("href", "")[1:])
        if tag in ("script", "img", "link"):
            self.assets.extend(attrs[key] for key in ("src", "href") if key in attrs)
        if "data-icon-id" in attrs:
            self.cards.append(attrs["data-icon-id"])


class ShowcaseTests(unittest.TestCase):
    def test_traffic_model_has_valid_reusable_recipe_and_stays_in_explorer(self):
        module = self.showcase_module()
        example = module.traffic_example()
        self.assertFalse(report.validate(example))
        html = module.render_showcase(report)
        for identifier in ("traffic-model", "traffic-demand", "traffic-current-diagram", "traffic-scaled-diagram"):
            self.assertIn(f'id="{identifier}"', html)
        self.assertIn("Requests", html)
        self.assertIn('class="traffic-assumptions"', html)
        self.assertNotIn('class="traffic-assumptions" open', html)
        self.assertNotIn('id="traffic-model"', report.render(example))

    def showcase_module(self):
        import showcase
        return showcase

    def test_all_visual_recipes_are_valid_and_cover_every_pattern(self):
        demos = self.showcase_module().visual_demos(report)
        templates, scenarios, transports = set(), set(), set()
        for demo in demos:
            visual = demo["visual"]
            with self.subTest(demo=demo["id"]):
                schema = json.loads((report.ASSETS / "report.schema.json").read_text(encoding="utf-8"))
                self.assertFalse(report.check_schema(visual, schema["$defs"]["visual"], schema))
                self.assertFalse(report.check_visual(visual, "$"))
                report.render_visual(visual, "review", demo["id"])
            templates.add(visual["template"])
            if "scenario" in visual:
                scenarios.add(visual["scenario"]["template"])
            transports.update(edge.get("transport", "request") for edge in visual.get("edges", []))
        self.assertEqual(templates, set(report.TEMPLATES))
        self.assertEqual(scenarios, set(report.SCENARIOS))
        self.assertEqual(transports, set(schema["$defs"]["edge"]["properties"]["transport"]["enum"]))
        self.assertTrue(any(any("node" in step for step in demo["visual"].get("sequence", [])) for demo in demos))

    def test_every_bundled_icon_is_visible_and_references_resolve(self):
        html = self.showcase_module().render_showcase(report)
        page = ShowcaseInspector()
        page.feed(html)
        glyphs = {symbol.attrib["id"] for symbol in ET.parse(report.ASSETS / "ui-icons.svg").iter() if symbol.tag.endswith("symbol")}
        expected = {"entity-" + kind for kind in report.KINDS} | {"brand-" + brand for brand in brands.BRANDS} | glyphs
        self.assertEqual(set(page.cards), expected)
        self.assertEqual(len(page.cards), len(expected))
        self.assertEqual(len(page.ids), len(set(page.ids)))
        self.assertTrue(set(page.references).issubset(page.ids))
        self.assertFalse(page.assets)
        for recipe in re.findall(r'<pre class="recipe-json"><code>(.*?)</code></pre>', html, re.S):
            from html import unescape
            self.assertIsInstance(json.loads(unescape(recipe)), dict)
        self.assertIn('id="icon-search"', html)
        self.assertIn('id="motion-pause"', html)
        self.assertIn("Replay this demo", html)
        self.assertEqual(html.count('class="problem-example"'), 13)
        self.assertNotIn('class="problem-example" open', html)

    def test_report_element_example_is_valid_and_gallery_stays_out_of_reports(self):
        sample = self.showcase_module().element_example()
        self.assertFalse(report.validate(sample))
        html = report.render(sample)
        for fragment in ("code-change", "source-location", "manual-item", "impact-item", "risk-severity", "summary-risks"):
            self.assertIn(fragment, html)
        ordinary = report.render(json.loads((report.ASSETS / "example-plan.json").read_text(encoding="utf-8")))
        self.assertNotIn("showcase-demo", ordinary)
        self.assertNotIn("icon-search", ordinary)

    def test_showcase_command_preserves_existing_files_and_skill_assets(self):
        with tempfile.TemporaryDirectory(prefix="change-showcase-test-") as temporary:
            output = Path(temporary) / "showcase.html"
            command = [sys.executable, str(Path(report.__file__)), "showcase", "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = output.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(subprocess.run(command + ["--force"], capture_output=True).returncode, 0)
        result = subprocess.run([sys.executable, str(Path(report.__file__)), "showcase", "--output", str(report.ASSETS / "forbidden-showcase.html")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((report.ASSETS / "forbidden-showcase.html").exists())


if __name__ == "__main__":
    unittest.main()
