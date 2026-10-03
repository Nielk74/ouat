"""Regression checks for branch meaning and persistent control-flow motion."""

import copy
import json
import unittest
import xml.etree.ElementTree as ET

import report


class BranchMotionTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((report.ASSETS / "example-plan.json").read_text(encoding="utf-8"))
        self.visual = self.data["changes"][1]["visual"]

    def test_branch_colors_follow_change_status(self):
        self.assertFalse([item for item in report.validate(self.data) if item["level"] == "error"])
        for vertical in (False, True):
            svg = ET.fromstring(report.render_graph_svg(self.visual, "plan", "branch", vertical))
            for number, status in ((1, "unchanged"), (2, "changed"), (3, "new"), (4, "new")):
                edge = next(node for node in svg if node.attrib.get("data-edge") == str(number))
                self.assertIn("status-" + status, edge.attrib["class"].split())
                connector = next(node for node in edge if node.attrib.get("class") == "connector")
                self.assertEqual(connector.attrib["marker-end"], f"url(#branch-{status}-arrow)")
                label = next(node for node in svg if node.attrib.get("data-label-edge") == str(number))
                self.assertEqual(label.attrib["class"], "edge-label")

    def test_control_flow_uses_routed_dots_without_payload_imagery(self):
        self.visual["edges"][4]["transport"] = "flow"
        for vertical in (False, True):
            svg = ET.fromstring(report.render_graph_svg(self.visual, "plan", "motion", vertical))
            edge = next(node for node in svg if node.attrib.get("data-edge") == "5")
            marker = next((node for node in edge if node.attrib.get("class") == "flow-transfer"), None)
            self.assertIsNotNone(marker)
            connector = next(node for node in edge if node.attrib.get("class") == "connector")
            self.assertEqual(marker.attrib["style"], f'offset-path: path("{connector.attrib["d"]}");')
            self.assertTrue(any(node.tag.endswith("circle") for node in marker))
            self.assertFalse(any(node.tag.endswith("use") for node in marker))
            self.assertFalse(any(node.attrib.get("class") == "connector-emphasis" for node in edge))
        html = report.render_visual(self.visual, "plan", "motion")
        self.assertIn("Moving dots: execution flow", html)
        self.assertIn("not execution order or timing", html)
        self.assertIn("System motion is reduced; select Play", html)
        self.assertIn('href="#motion-controls"', html)

    def test_static_branches_need_no_extra_color_key(self):
        for item in self.visual["nodes"] + self.visual["edges"]:
            item["animate"] = False
        html = report.render_visual(self.visual, "plan", "static-branch")
        self.assertNotIn("packet-guidance", html)
        self.assertNotIn('href="#motion-controls"', html)
        self.assertNotIn("flow-transfer", html)

    def test_retry_example_keeps_persistent_flow(self):
        self.assertFalse(self.visual["nodes"][2].get("animate"))
        for number in (1, 4):
            self.assertEqual(self.visual["edges"][number].get("transport"), "flow")
            self.assertTrue(self.visual["edges"][number].get("animate"))

    def test_configuration_and_spawn_are_not_execution_transfers(self):
        for transport in ("config", "spawn"):
            visual = copy.deepcopy(self.visual)
            visual["edges"][4]["transport"] = transport
            svg = ET.fromstring(report.render_graph_svg(visual, "plan", "configuration"))
            edge = next(node for node in svg if node.attrib.get("data-edge") == "5")
            self.assertTrue(any(node.attrib.get("class") == "connector-emphasis" for node in edge))
            self.assertFalse(any(node.attrib.get("class") == "flow-transfer" for node in edge))


if __name__ == "__main__":
    unittest.main()
