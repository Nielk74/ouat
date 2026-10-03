"""Geometry regressions for readable, directly labeled connections."""

import json
from pathlib import Path
import unittest

import diagram


class DiagramLabelTests(unittest.TestCase):
    def connection(self, label="Success", short_label=None, moving=False):
        edge = {"from": "a", "to": "b", "label": label, "status": "unchanged"}
        if short_label:
            edge["shortLabel"] = short_label
        if moving:
            edge.update(animate=True, transport="message")
        return {
            "nodes": [{"id": "a", "label": "Start", "status": "unchanged"},
                      {"id": "b", "label": "Finish", "status": "unchanged"}],
            "edges": [edge],
        }

    def assert_geometry(self, visual, vertical=False):
        geometry = diagram.route_graph(visual, vertical)
        boxes = [position[:4] for position in geometry["positions"].values()]
        boxes.extend(header for _, _, header in geometry["groups"])
        labels = []
        for index, route in enumerate(geometry["routes"]):
            self.assertIn("labelBox", route, "Every arrow needs actual label geometry, not a number-only placeholder.")
            self.assertIn("labelLines", route)
            self.assertIn("labelAnchor", route)
            label = route["labelBox"]
            x, y, width, height = label
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x+width, geometry["width"])
            self.assertLessEqual(y+height, geometry["height"])
            self.assertTrue(1 <= len(route["labelLines"]) <= 2)
            expected = visual["edges"][index].get("shortLabel", visual["edges"][index]["label"])
            self.assertEqual(" ".join(route["labelLines"]), " ".join(expected.split()))
            for obstacle in boxes + labels:
                self.assertFalse(diagram.overlaps(label, obstacle), (index, label, obstacle))
            for other_index, other in enumerate(geometry["routes"]):
                if other_index == index and not diagram.packet_symbol(visual["edges"][index]):
                    continue
                for start, end in zip(other["points"], other["points"][1:]):
                    self.assertFalse(diagram.segment_hits(start, end, label), (index, other_index))
            labels.append(label)
        return geometry

    def test_arrow_explains_its_meaning_without_number_lookup(self):
        self.assert_geometry(self.connection())

    def test_short_label_preserves_full_condition_in_source(self):
        visual = self.connection("All four eligibility conditions must hold before retrying", "Yes")
        geometry = self.assert_geometry(visual)
        self.assertEqual(geometry["routes"][0]["labelLines"], ["Yes"])
        self.assertEqual(visual["edges"][0]["label"], "All four eligibility conditions must hold before retrying")

    def test_ordinary_condition_wraps_beside_a_short_connection(self):
        for label in ("Eligible failure", "Transient HTTP failure"):
            self.assert_geometry(self.connection(label))

    def test_message_label_leaves_moving_packet_corridor_clear(self):
        for vertical in (False, True):
            visual = self.connection("Deliver message", moving=True)
            geometry = self.assert_geometry(visual, vertical)
            route = geometry["routes"][0]
            x, y, width, height = route["labelBox"]
            protected = (x-14, y-14, width+28, height+28)
            self.assertFalse(any(diagram.segment_hits(a, b, protected)
                                 for a, b in zip(route["points"], route["points"][1:])))

    def test_supplied_graphs_keep_all_labels_clear(self):
        assets = Path(__file__).resolve().parents[1] / "assets"
        for filename in ("example-plan.json", "example-system.json"):
            fixture = json.loads((assets / filename).read_text(encoding="utf-8"))
            visuals = [fixture["context"]["visual"], *[change["visual"] for change in fixture["changes"]]]
            for visual in visuals:
                if "nodes" in visual:
                    for vertical in (False, True):
                        with self.subTest(filename=filename, template=visual["template"], vertical=vertical):
                            self.assert_geometry(visual, vertical)

    def test_unreadable_label_is_rejected_with_author_guidance(self):
        visual = self.connection("This deliberately verbose condition cannot reasonably fit beside a short connection " * 3)
        with self.assertRaisesRegex(diagram.RouteError, "shortLabel"):
            diagram.route_graph(visual)

    def test_canvas_does_not_add_a_blank_row_below_the_diagram(self):
        geometry = self.assert_geometry(self.connection())
        bottom = max(position[1]+position[3] for position in geometry["positions"].values())
        bottom = max(bottom, *(route["labelBox"][1]+route["labelBox"][3]
                               for route in geometry["routes"]))
        self.assertLessEqual(geometry["height"], bottom+48)

    def test_existing_reports_without_short_labels_remain_readable(self):
        assets = Path(__file__).resolve().parents[1] / "assets"
        for filename in ("example-plan.json", "example-system.json"):
            fixture = json.loads((assets / filename).read_text(encoding="utf-8"))
            visuals = [fixture["context"]["visual"], *[change["visual"] for change in fixture["changes"]]]
            for visual in visuals:
                if "nodes" not in visual:
                    continue
                for edge in visual["edges"]:
                    edge.pop("shortLabel", None)
                for vertical in (False, True):
                    with self.subTest(filename=filename, template=visual["template"], vertical=vertical):
                        self.assert_geometry(visual, vertical)

    def test_original_v1_state_conditions_preserve_complete_meaning(self):
        visual = {
            "nodes": [
                {"id": "attempting", "label": "Attempting", "status": "unchanged"},
                {"id": "waiting", "label": "Waiting to retry", "status": "new"},
                {"id": "finished", "label": "Finished", "status": "changed"},
            ],
            "edges": [
                {"from": "attempting", "to": "waiting", "label": "Eligible failure and remaining budget", "status": "new"},
                {"from": "waiting", "to": "attempting", "label": "Wait completes; budget permits another attempt", "status": "new"},
                {"from": "waiting", "to": "finished", "label": "Deadline or cancellation stops recovery", "status": "new"},
                {"from": "attempting", "to": "finished", "label": "Success or retry policy declines recovery", "status": "changed"},
            ],
        }
        for vertical in (False, True):
            with self.subTest(vertical=vertical):
                self.assert_geometry(visual, vertical)


if __name__ == "__main__":
    unittest.main()
