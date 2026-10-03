"""Teaching examples must show distinct mechanisms and preserve static outcomes."""

import copy
import json
import unittest
import xml.etree.ElementTree as ET

import report


class ProblemExampleTests(unittest.TestCase):
    def examples(self):
        from problem_examples import problem_demos
        return problem_demos()

    def test_problem_stories_are_valid_and_cover_distinct_gaps(self):
        examples = self.examples()
        self.assertEqual(len(examples), 9)
        schema = json.loads((report.ASSETS / "report.schema.json").read_text(encoding="utf-8"))
        for example in examples:
            with self.subTest(example=example["id"]):
                visual = example["visual"]
                self.assertFalse(report.check_schema(visual, schema["$defs"]["visual"], schema))
                self.assertFalse(report.check_visual(visual, "$"))
                self.assertTrue(all(item["status"] == "unchanged" for item in visual["nodes"] + visual["edges"]))
                report.render_visual(visual, "review", example["id"])

    def test_new_scenarios_have_distinct_pedagogical_outcomes(self):
        expected = {"timeout": "story-progress-fill", "duplicate-effect": "story-receipt",
                    "out-of-order": "story-result", "partial-failure": "story-step"}
        for example in self.examples():
            visual = example["visual"]
            if "scenario" not in visual:
                continue
            pattern = visual["scenario"]["template"]
            with self.subTest(pattern=pattern):
                root = ET.fromstring(report.render_scenario(visual, "review"))
                classes = {value for node in root.iter() for value in node.attrib.get("class", "").split()}
                self.assertIn(expected[pattern], classes)
                self.assertTrue({"story-initial", "story-middle", "story-outcome"}.issubset(classes))
                self.assertNotIn("scenario-empty-result", classes)
                self.assertIn(visual["scenario"]["consequence"], ''.join(root.itertext()))

    def test_duplicate_effect_requires_the_failed_acknowledgement_path(self):
        visual = copy.deepcopy(next(item["visual"] for item in self.examples() if item["id"] == "problem-duplicate-effect"))
        scenario = visual["scenario"]
        visual["edges"] = [edge for edge in visual["edges"] if not (edge["from"] == scenario["at"] and edge["to"] == scenario["from"])]
        self.assertTrue(any("acknowledgement" in item["message"] for item in report.check_visual(visual, "$")))

    def test_ordered_values_are_paired_distinct_and_escaped(self):
        visual = copy.deepcopy(next(item["visual"] for item in self.examples() if item["id"] == "problem-out-of-order"))
        scenario = visual["scenario"]
        scenario["earlier"] = '<script>old</script>'
        html = report.render_scenario(visual, "review")
        self.assertNotIn('<script>old</script>', html)
        self.assertIn('&lt;script&gt;old&lt;/script&gt;', html)
        scenario["later"] = scenario["earlier"]
        self.assertTrue(report.check_visual(visual, "$"))
        del scenario["later"]
        self.assertTrue(report.check_visual(visual, "$"))


if __name__ == "__main__":
    unittest.main()
