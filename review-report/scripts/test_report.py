#!/usr/bin/env python3
"""Behavioral checks for the data contract, diagnostics, and safe standalone output."""

import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import diagram
import report
import brands


class PageInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.sections = []
        self.remote_assets = []
        self.hidden_content = []
        self.scripts = 0
        self.connection_labels = []
        self.active_graph = None
        self.uses = []
        self.shortcuts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "svg":
            self.connection_labels.append([])
            self.active_graph = self.connection_labels[-1]
        if tag == "rect" and attrs.get("class") == "edge-number-box":
            self.active_graph.append(tuple(float(attrs[key]) for key in ("x", "y", "width", "height")))
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.links.append(attrs["href"][1:])
            if "tool-link" in attrs.get("class", "").split():
                self.shortcuts.append((attrs["href"][1:], attrs.get("aria-label", "")))
        if tag == "use" and attrs.get("href", "").startswith("#"):
            self.uses.append(attrs["href"][1:])
        if tag == "section":
            self.sections.append(attrs.get("id"))
        if tag in ("details", "dialog") or "hidden" in attrs:
            self.hidden_content.append(tag)
        if tag == "script":
            self.scripts += 1
        if tag in ("link", "script", "img", "iframe"):
            url = attrs.get("src", attrs.get("href", ""))
            if url.startswith(("http:", "https:", "//")):
                self.remote_assets.append(url)

    def handle_endtag(self, tag):
        if tag == "svg":
            self.active_graph = None


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.example = json.loads((report.ASSETS / "example-plan.json").read_text(encoding="utf-8"))
        self.system = json.loads((report.ASSETS / "example-system.json").read_text(encoding="utf-8"))

    def errors(self, data):
        return [item for item in report.validate(data) if item["level"] == "error"]

    def test_all_templates_and_both_modes(self):
        visuals = [self.example["context"]["visual"]] + [change["visual"] for change in self.example["changes"] + self.system["changes"]]
        self.assertEqual({visual["template"] for visual in visuals}, set(report.TEMPLATES))
        self.assertFalse(report.validate(self.example))
        for fixture in (self.example, self.system):
            for mode in ("plan", "review"):
                data = copy.deepcopy(fixture)
                data["mode"] = mode
                self.assertFalse(self.errors(data))
                inspector = PageInspector()
                inspector.feed(report.render(data))
                self.assertEqual(inspector.sections, ["context", "changes", "manual", "impact", "risks"])
                self.assertEqual(len(inspector.ids), len(set(inspector.ids)))
                self.assertTrue(set(inspector.links + inspector.uses).issubset(set(inspector.ids)))
                self.assertFalse(inspector.remote_assets)
                self.assertFalse(inspector.hidden_content)
                self.assertEqual(inspector.scripts, 0)

    def test_rejects_broken_nodes_with_precise_path(self):
        visual = self.example["changes"][1]["visual"]
        visual["edges"][0]["to"] = "missing"
        errors = self.errors(self.example)
        self.assertTrue(any(item["path"] == "$.changes[1].visual.edges[0].to" for item in errors))

    def test_branch_connection_numbers_do_not_overlap(self):
        for fixture in (self.example, self.system):
            inspector = PageInspector()
            inspector.feed(report.render(fixture))
            for rectangles in inspector.connection_labels:
                for index, (x, y, width, height) in enumerate(rectangles):
                    for other_x, other_y, other_width, other_height in rectangles[index+1:]:
                        self.assertFalse(x < other_x+other_width and x+width > other_x and y < other_y+other_height and y+height > other_y)

    def assert_readable_routes(self, visual, vertical):
        geometry = diagram.route_graph(visual, vertical)
        nodes = {node_id: position[:4] for node_id, position in geometry["positions"].items()}
        headers = [header for _, _, header in geometry["groups"]]
        routes = geometry["routes"]

        def hits(a, b, box):
            x, y, width, height = box
            if a[0] == b[0]:
                return x < a[0] < x+width and min(a[1], b[1]) < y+height and max(a[1], b[1]) > y
            return y < a[1] < y+height and min(a[0], b[0]) < x+width and max(a[0], b[0]) > x

        labels = []
        for index, route in enumerate(routes):
            points = route["points"]
            for start, end in zip(points, points[1:]):
                self.assertNotEqual(start, end)
                self.assertTrue(start[0] == end[0] or start[1] == end[1])
                for box in [*nodes.values(), *headers]:
                    self.assertFalse(hits(start, end, box), (index, start, end, box))
            x, y, width, height = nodes[route["target"]]
            tip, previous = points[-1], points[-2]
            self.assertGreaterEqual(abs(tip[0]-previous[0]) + abs(tip[1]-previous[1]), 23)
            terminal_is_clear = (
                tip[0] == x-9 and x-previous[0] > 9 and y < tip[1] < y+height or
                tip[0] == x+width+9 and previous[0] > tip[0] and y < tip[1] < y+height or
                tip[1] == y-9 and y-previous[1] > 9 and x < tip[0] < x+width or
                tip[1] == y+height+9 and previous[1] > tip[1] and x < tip[0] < x+width
            )
            self.assertTrue(terminal_is_clear, (index, tip, previous, nodes[route["target"]]))
            label_x, label_y = route["label"]
            label = (label_x-17, label_y-12, 34, 24)
            for box in [*nodes.values(), *headers, *labels]:
                self.assertFalse(diagram.overlaps(label, box))
            for other_index, other in enumerate(routes):
                if index == other_index:
                    continue
                for a, b in zip(other["points"], other["points"][1:]):
                    self.assertFalse(hits(a, b, label))
                for a, b in zip(points, points[1:]):
                    for c, d in zip(other["points"], other["points"][1:]):
                        if a[1] == b[1] == c[1] == d[1]:
                            self.assertLessEqual(min(max(a[0], b[0]), max(c[0], d[0])), max(min(a[0], b[0]), min(c[0], d[0])))
                        elif a[0] == b[0] == c[0] == d[0]:
                            self.assertLessEqual(min(max(a[1], b[1]), max(c[1], d[1])), max(min(a[1], b[1]), min(c[1], d[1])))
            labels.append(label)

    def test_routes_avoid_nodes_headings_numbers_and_shared_segments(self):
        for fixture in (self.example, self.system):
            for visual in [fixture["context"]["visual"], *[change["visual"] for change in fixture["changes"]]]:
                if "nodes" in visual:
                    for vertical in (False, True):
                        with self.subTest(template=visual["template"], vertical=vertical):
                            self.assert_readable_routes(visual, vertical)

    def test_schedule_neighbors_use_straight_routes_not_u_turns(self):
        visual = self.system["changes"][1]["visual"]
        routes = diagram.route_graph(visual)["routes"]
        self.assertEqual(len(routes[2]["points"]), 2, "Cron must connect directly to the neighboring API.")
        for index in (0, 2, 3):
            points = routes[index]["points"]
            self.assertEqual(len(points), 2)
            self.assertEqual(points[0][1], points[1][1])
        bypass = routes[1]["points"]
        self.assertLessEqual(len(bypass), 6, "Skipping the cron node requires one detour, not a loop.")
        self.assertTrue(all(b[0] >= a[0] for a, b in zip(bypass, bypass[1:])))

    def test_thread_routes_have_separate_lanes_and_direct_database_write(self):
        visual = self.system["changes"][2]["visual"]
        geometry = diagram.route_graph(visual)
        positions, routes = geometry["positions"], geometry["routes"]
        process, first, second, database = (positions[key] for key in ("process", "thread-a", "thread-b", "db"))
        self.assertLess(first[1], process[1])
        self.assertLess(process[1], second[1])
        self.assertEqual(database[0], process[0])
        self.assertEqual(len(routes[4]["points"]), 2)
        self.assertEqual(routes[4]["points"][0][0], routes[4]["points"][1][0])
        for index, route in enumerate(routes):
            self.assertLessEqual(len(route["points"]), 4, "No zigzag detours in this focused graph.")
            for other in routes[index+1:]:
                for a, b in zip(route["points"], route["points"][1:]):
                    for c, d in zip(other["points"], other["points"][1:]):
                        if a[0] == b[0] and c[1] == d[1]:
                            self.assertFalse(min(a[1], b[1]) < c[1] < max(a[1], b[1]) and min(c[0], d[0]) < a[0] < max(c[0], d[0]))
                        if a[1] == b[1] and c[0] == d[0]:
                            self.assertFalse(min(c[1], d[1]) < a[1] < max(c[1], d[1]) and min(a[0], b[0]) < c[0] < max(a[0], b[0]))

    def test_baseline_problems_are_separate_from_change_status(self):
        visual = self.system["context"]["visual"]
        self.assertEqual({obj["status"] for obj in visual["nodes"] + visual["edges"]}, {"unchanged"})
        self.assertTrue(any("issue" in obj for obj in visual["nodes"]))
        self.assertTrue(any("issue" in obj for obj in visual["edges"]))
        html = report.render_visual(visual, "plan", "baseline", baseline=True)
        self.assertIn("Baseline behavior", html)
        self.assertIn("Illustrative starting point", html)
        self.assertIn("Problem in existing behavior", html)
        self.assertIn("Why this behavior is problematic", html)
        self.assertIn("status-unchanged entity-process has-issue", html)
        for obj in visual["nodes"] + visual["edges"]:
            if "issue" in obj:
                self.assertIn(report.text(obj["issue"]), html)
        visual["nodes"][1]["issue"] = '<script>bad()</script> {{BODY}}'
        html = report.render(self.system)
        inspector = PageInspector()
        inspector.feed(html)
        self.assertEqual(inspector.scripts, 0)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt; {{BODY}}", html)

    def test_narrow_baseline_keeps_trigger_before_its_runtime(self):
        visual = self.system["context"]["visual"]
        positions, _, _ = report.graph_layout(visual["nodes"], visual["edges"], visual["groups"], vertical=True)
        self.assertLess(positions["cron"][1], positions["request"][1])
        self.assertLess(positions["request"][1], positions["export"][1])
        self.assertLess(positions["export"][1], positions["db"][1])

    def test_invalid_problem_annotations_identify_exact_fields(self):
        self.system["context"]["visual"]["nodes"][1]["issue"] = True
        self.system["context"]["visual"]["edges"][1]["issue"] = ""
        paths = {item["path"] for item in self.errors(self.system)}
        self.assertIn("$.context.visual.nodes[1].issue", paths)
        self.assertIn("$.context.visual.edges[1].issue", paths)

    def test_missing_baseline_diagram_warns_without_blocking(self):
        del self.system["context"]["visual"]
        diagnostics = report.validate(self.system)
        self.assertFalse(self.errors(self.system))
        self.assertTrue(any(item["path"] == "$.context.visual" and item["level"] == "warning" for item in diagnostics))

    def test_crowded_routing_reports_an_actionable_json_path(self):
        self.system["context"]["visual"] = {
            "template": "flow", "caption": "Crowded parallel relationships",
            "nodes": [{"id": "a", "label": "A", "status": "unchanged"}, {"id": "b", "label": "B", "status": "unchanged"}],
            "edges": [{"from": "a", "to": "b", "label": str(index), "status": "unchanged"} for index in range(10)],
        }
        errors = self.errors(self.system)
        self.assertTrue(errors)
        self.assertTrue(all(item["path"].startswith("$.context.visual.edges[") for item in errors))
        self.assertTrue(all("route" in item["message"] and "Split" in item["hint"] for item in errors))

    def test_component_types_have_real_vector_assets(self):
        sprite = ET.fromstring((report.ASSETS / "entities.svg").read_text(encoding="utf-8"))
        symbols = {element.attrib["id"] for element in sprite.iter() if element.tag.endswith("symbol")}
        schema = json.loads((report.ASSETS / "report.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(report.KINDS), set(schema["$defs"]["kind"]["enum"]))
        self.assertEqual(symbols, {"entity-" + kind for kind in report.KINDS})

    def test_toolbar_links_only_to_existing_sections(self):
        for include_optional in (True, False):
            data = copy.deepcopy(self.system)
            if not include_optional:
                data.pop("manualChanges", None)
                data.pop("risks", None)
            inspector = PageInspector()
            inspector.feed(report.render(data))
            self.assertEqual({anchor for anchor, _ in inspector.shortcuts}, {"report", *inspector.sections})
            self.assertTrue(all(label.strip() for _, label in inspector.shortcuts))
            self.assertTrue(set(inspector.uses).issubset(set(inspector.ids)))

    def test_component_and_transport_errors_identify_fields(self):
        self.system["changes"][0]["visual"]["nodes"][0]["kind"] = "servre"
        self.system["changes"][0]["visual"]["edges"][0]["transport"] = "unknown"
        errors = self.errors(self.system)
        self.assertTrue(any(item["path"] == "$.changes[0].visual.nodes[0].kind" for item in errors))
        self.assertTrue(any(item["path"] == "$.changes[0].visual.edges[0].transport" for item in errors))

    def test_boundary_references_and_membership(self):
        visual = self.system["changes"][2]["visual"]
        visual["nodes"][0]["group"] = "missing-host"
        self.assertTrue(any(item["path"] == "$.changes[2].visual.nodes[0].group" for item in self.errors(self.system)))
        visual["nodes"][0]["group"] = "host"
        positions, _, _ = report.graph_layout(visual["nodes"], visual["edges"], visual["groups"])
        member_bottom = max(positions[node["id"]][1] + positions[node["id"]][3] for node in visual["nodes"] if node.get("group") == "host")
        self.assertGreater(positions["db"][1], member_bottom)
        visual["groups"].append({"id": "empty", "label": "Unused", "kind": "process"})
        self.assertTrue(any(item["path"] == "$.changes[2].visual.groups[1].id" for item in self.errors(self.system)))

    def test_code_excerpt_escaping_and_empty_content(self):
        code = self.system["changes"][0]["code"]
        code["after"] = '<script>alert("bad")</script> {{STYLE}}'
        inspector = PageInspector()
        html = report.render(self.system)
        inspector.feed(html)
        self.assertEqual(inspector.scripts, 0)
        self.assertIn("{{STYLE}}", html)
        self.assertIn("&lt;script&gt;", html)
        code["before"] = code["after"] = ""
        self.assertTrue(any(item["path"] == "$.changes[0].code" for item in self.errors(self.system)))

    def test_rejects_duplicate_ids_and_unlinked_impacts(self):
        self.example["changes"][1]["id"] = self.example["changes"][0]["id"]
        self.example["impact"][2]["change"] = "missing-change"
        errors = self.errors(self.example)
        self.assertTrue(any("Duplicate change" in item["message"] for item in errors))
        self.assertTrue(any(item["path"] == "$.impact[2].change" for item in errors))

    def test_discriminated_templates_and_typos(self):
        self.example["changes"][0]["visual"]["template"] = "beforeAfter"
        errors = self.errors(self.example)
        self.assertEqual(errors[0]["path"], "$.changes[0].visual.template")
        self.assertIn("before-after", errors[0]["hint"])
        self.example["changes"][0]["visual"]["template"] = "before-after"
        self.example["changes"][0]["visual"]["captin"] = "typo"
        errors = self.errors(self.example)
        self.assertTrue(any(item["path"].endswith(".captin") and "caption" in item["hint"] for item in errors))

    def test_plan_cannot_claim_observed_outcomes(self):
        self.example["impact"][0]["basis"] = "observed"
        self.assertTrue(any(item["path"] == "$.impact[0].basis" for item in self.errors(self.example)))
        self.example["mode"] = "review"
        self.assertFalse(self.errors(self.example))

    def test_motion_only_on_highlighted_changes(self):
        self.example["context"]["visual"]["nodes"][0]["animate"] = True
        self.assertTrue(any(item["path"] == "$.context.visual.nodes[0].animate" for item in self.errors(self.example)))

    def test_packages_share_message_routes_and_keep_labels_above_them(self):
        visual = self.system["changes"][0]["visual"]
        for vertical in (False, True):
            svg = ET.fromstring(report.render_graph_svg(visual, "plan", "packet-test", vertical))
            edges = [element for element in svg if element.attrib.get("data-edge")]
            packet_edges = 0
            for edge in edges:
                packets = [child for child in edge if child.attrib.get("class") == "message-packet"]
                source = visual["edges"][int(edge.attrib["data-edge"])-1]
                self.assertEqual(bool(packets), bool(source.get("animate") and source.get("transport") == "message"))
                for packet in packets:
                    packet_edges += 1
                    connector = next(child for child in edge if child.attrib.get("class") == "connector")
                    self.assertEqual(packet.attrib["style"], f'offset-path: path("{connector.attrib["d"]}");')
                    self.assertEqual(packet.attrib["aria-hidden"], "true")
                    self.assertEqual(packet[0].attrib["href"], "#ui-package")
                    self.assertFalse(any(child.attrib.get("class") == "connector-emphasis" for child in edge))
                    number_layer = next(element for element in svg if any(child.attrib.get("class") == "edge-number-box" for child in element))
                    self.assertLess(list(svg).index(edge), list(svg).index(number_layer))
            self.assertEqual(packet_edges, 1)

    def test_packet_loop_has_native_pause_without_scripts_or_new_fields(self):
        visual = self.system["changes"][0]["visual"]
        html = report.render_visual(visual, "plan", "packet-focus")
        self.assertIn('aria-describedby="packet-focus-packet-note"', html)
        self.assertIn('id="packet-focus-packet-note"', html)
        self.assertIn('for="packet-focus-pause"', html)
        self.assertIn('type="checkbox" id="packet-focus-pause"', html)
        self.assertIn('Repeats automatically; not a measured rate.', html)
        self.assertNotIn('Hover or focus', html)
        self.assertFalse(self.errors(self.system))
        visual["edges"][1]["animate"] = False
        html = report.render_visual(visual, "plan", "packet-static")
        self.assertNotIn("message-packet", html)
        self.assertNotIn("tabindex", html)
        self.assertNotIn("packet-guidance", html)

    def test_local_brand_catalog_is_complete_safe_and_attributed(self):
        self.assertGreaterEqual(len(brands.BRANDS), 50)
        self.assertTrue({"teamcity", "jenkins", "github", "gitlab", "aws", "azure", "rabbitmq", "postgresql"}.issubset(brands.BRANDS))
        ids = []
        for name, item in brands.BRANDS.items():
            self.assertTrue((report.ASSETS / "brands" / item["file"]).is_file())
            self.assertTrue(item["source"].startswith("https://"))
            self.assertTrue(item["license"]["type"])
            self.assertTrue(item["revision"])
            symbol = ET.fromstring(brands.symbol(name))
            self.assertEqual(symbol.attrib["id"], "brand-" + name)
            self.assertTrue(symbol.attrib["viewBox"])
            for node in symbol.iter():
                self.assertIn(node.tag, brands.SVG_TAGS | {"symbol"})
                self.assertNotIn("style", node.attrib)
                self.assertFalse(any(key.lower().startswith("on") for key in node.attrib))
                if "id" in node.attrib:
                    ids.append(node.attrib["id"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("creativecommons.org/licenses/by-sa/3.0", brands.credits({"jenkins"}))
        self.assertIn("https://www.jetbrains.com/", brands.credits({"teamcity"}))

    def test_brands_keep_role_status_and_inline_only_selected_assets(self):
        node = self.system["changes"][0]["visual"]["nodes"][2]
        node["brand"] = "rabbitmq"
        self.assertFalse(self.errors(self.system))
        html = report.render(self.system)
        self.assertIn('id="brand-rabbitmq"', html)
        self.assertIn('href="#brand-rabbitmq"', html)
        self.assertIn('entity-queue', html)
        self.assertIn('status-new', html)
        self.assertNotIn('id="brand-docker"', html)
        inspector = PageInspector()
        inspector.feed(html)
        self.assertFalse(inspector.remote_assets)
        self.assertEqual(inspector.scripts, 0)
        self.assertTrue(set(inspector.uses).issubset(inspector.ids))
        self.assertEqual(len(inspector.ids), len(set(inspector.ids)))

    def test_brand_tiles_select_stronger_contrast_without_changing_paint(self):
        self.assertEqual(brands.brand_surface("postgresql"), "light")
        self.assertEqual(brands.brand_surface("github"), "light")
        self.assertEqual(brands.brand_surface("docker"), "dark")
        for name, item in brands.BRANDS.items():
            if item["provider"] != "Simple Icons":
                continue
            selected = brands.brand_surface(name)
            ratio = brands.contrast_ratio(item["color"], brands.BRAND_SURFACES[selected])
            self.assertGreaterEqual(ratio, 3, name)
            self.assertGreaterEqual(ratio, max(brands.contrast_ratio(item["color"], background) for background in brands.BRAND_SURFACES.values()))
            self.assertEqual(ET.fromstring(brands.symbol(name)).attrib["fill"], item["color"])

    def test_brand_surfaces_apply_to_all_templates_and_statuses(self):
        for name in ("postgresql", "github", "docker"):
            for status in report.LABELS:
                surface = "brand-surface-" + brands.brand_surface(name)
                node = {"id": "product", "label": "Product", "kind": "database", "brand": name, "status": status}
                if status == "unchanged":
                    node["issue"] = "Existing behavior needs attention."
                visual = {"template": "communication", "caption": "Brand contrast fixture.", "nodes": [node], "edges": []}
                svg = ET.fromstring(report.render_graph_svg(visual, "review", "contrast"))
                rendered = next(element for element in svg if element.attrib.get("data-node"))
                self.assertIn(surface, rendered.attrib["class"].split())
                self.assertIn(surface, report.element(node, "review"))
                self.assertIn(surface, report.icon("database", 20, name))

    def test_unknown_brand_has_precise_correction_path(self):
        node = self.system["changes"][3]["visual"]["nodes"][0]
        node["brand"] = "team-city"
        errors = self.errors(self.system)
        self.assertTrue(any(item["path"] == "$.changes[3].visual.nodes[0].brand" and '"teamcity"' in item["hint"] for item in errors))
        self.example["changes"][0]["visual"]["after"][0]["brand"] = "unknown-product"
        self.assertTrue(any(item["path"] == "$.changes[0].visual.after[0].brand" for item in self.errors(self.example)))

    def test_icon_catalog_is_standalone_with_matching_symbol_references(self):
        html = brands.catalog_page((report.ASSETS / "entities.svg").read_text(encoding="utf-8"), (report.ASSETS / "ui-icons.svg").read_text(encoding="utf-8"), report.KINDS)
        inspector = PageInspector()
        inspector.feed(html)
        self.assertEqual(inspector.scripts, 0)
        self.assertFalse(inspector.remote_assets)
        self.assertTrue(set(inspector.uses).issubset(inspector.ids))
        self.assertEqual(len(inspector.ids), len(set(inspector.ids)))
        self.assertIn('kind: "repository"', html)
        self.assertIn('brand: "teamcity"', html)

    def test_nonmessage_animation_does_not_imply_a_payload(self):
        visual = self.example["changes"][1]["visual"]
        html = report.render_graph_svg(visual, "plan", "state-transition")
        self.assertIn('class="connector-emphasis"', html)
        self.assertNotIn("message-packet", html)

    def test_packet_animation_keeps_existing_validation_rules(self):
        edge = self.system["changes"][0]["visual"]["edges"][1]
        edge["status"] = "unchanged"
        self.assertTrue(any(item["path"] == "$.changes[0].visual.edges[1].animate" for item in self.errors(self.system)))
        edge["status"] = "new"
        edge["animate"] = "yes"
        self.assertTrue(any(item["path"] == "$.changes[0].visual.edges[1].animate" for item in self.errors(self.system)))

    def test_cycles_self_loops_and_disconnected_nodes(self):
        visual = self.example["changes"][1]["visual"]
        visual["nodes"].append({"id": "isolated", "label": "Additional context", "status": "unchanged"})
        visual["edges"].append({"from": "wait", "to": "wait", "label": "Still waiting", "status": "new"})
        self.assertFalse(self.errors(self.example))
        positions, width, height = report.graph_layout(visual["nodes"], visual["edges"])
        self.assertEqual(len(positions), len(visual["nodes"]))
        self.assertTrue(all(x >= 0 and y >= 0 and x+w < width and y+h < height for x, y, w, h, _ in positions.values()))
        self.assertIn("Still waiting", report.render(self.example))
        for vertical in (False, True):
            self.assert_readable_routes(visual, vertical)

    def test_text_is_escaped_and_template_tokens_are_not_reinterpreted(self):
        self.example["title"] = '<script>alert("x")</script> {{BODY}} & title'
        self.example["changes"][0]["description"] = '<img src="https://example.invalid/x" onerror="bad()">'
        html = report.render(self.example)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("{{BODY}}", html)
        inspector = PageInspector()
        inspector.feed(html)
        self.assertEqual(inspector.scripts, 0)
        self.assertFalse(inspector.remote_assets)

    def test_empty_scope_and_optional_sections(self):
        data = {"version": 1, "mode": "review", "title": "No changes", "context": {"problem": "Inspect current scope.", "baseline": "Same revision."}, "changes": [], "impact": [], "manualChanges": [], "risks": []}
        self.assertFalse(self.errors(data))
        inspector = PageInspector()
        inspector.feed(report.render(data))
        self.assertEqual(inspector.sections, ["context", "changes", "impact"])

    def test_required_impacts_and_strict_types(self):
        self.example["impact"] = []
        self.assertEqual(len(self.errors(self.example)), len(self.example["changes"]))
        self.example["version"] = True
        self.assertTrue(any(item["path"] == "$.version" for item in self.errors(self.example)))

    def test_cli_error_correction_and_output_preservation(self):
        with tempfile.TemporaryDirectory(prefix="review-report-test-") as temporary:
            folder = Path(temporary)
            source, output = folder / "report.json", folder / "report.html"
            source.write_text('{"version": 1,\n}', encoding="utf-8")
            cli = [sys.executable, str(Path(report.__file__))]
            result = subprocess.run(cli + ["validate", str(source), "--json"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            diagnostics = json.loads(result.stdout)
            self.assertFalse(diagnostics["valid"])
            self.assertIn("line 2", diagnostics["diagnostics"][0]["message"])
            self.assertIn("column", diagnostics["diagnostics"][0]["message"])
            source.write_text(json.dumps(self.example), encoding="utf-8")
            result = subprocess.run(cli + ["render", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = output.read_bytes()
            self.example["title"] = "Changed title"
            source.write_text(json.dumps(self.example), encoding="utf-8")
            result = subprocess.run(cli + ["render", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_bytes(), original)
            result = subprocess.run(cli + ["render", str(source), "--output", str(output), "--force"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Changed title", output.read_text(encoding="utf-8"))

    def test_duplicate_keys_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory(prefix="review-report-json-") as temporary:
            source = Path(temporary) / "bad.json"
            for contents, expected in [('{"mode":"review","mode":"plan"}', "Duplicate"), ('{"version":NaN}', "Non-finite")]:
                source.write_text(contents, encoding="utf-8")
                _, errors = report.load_report(source)
                self.assertIn(expected, errors[0]["message"])


if __name__ == "__main__":
    unittest.main()
