#!/usr/bin/env python3
"""Validate report JSON and render reusable templates, using only the standard library."""

import argparse
import difflib
from html import escape
import json
from pathlib import Path, PureWindowsPath
import re
import sys
import textwrap
from urllib.parse import urlsplit

from diagram import RouteError, flow_signal, graph_layout, packet_symbol, path_data, route_graph
from brands import BRANDS, brand_surface, catalog_page, credits as brand_credits, selected as selected_brands, sprite as brand_sprite


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
LABELS = {"new": "New", "changed": "Changed", "removed": "Removed", "unchanged": "Existing context"}
TEMPLATES = {
    "before-after": "Before / after",
    "flow": "Process flow",
    "dependency-map": "Dependency map",
    "comparison": "Rules / data comparison",
    "state-transitions": "State transitions",
    "communication": "Processes / messages",
}
KINDS = {
    "generic": "Component", "client": "Client", "server": "Server", "service": "Service",
    "config": "Config", "cron": "Cron", "ci-worker": "CI/CD agent", "worker": "Worker",
    "process": "Process", "thread": "Thread", "queue": "Queue", "message": "Message",
    "database": "Database", "storage": "Storage", "repository": "Repository", "function": "Function", "decision": "Decision",
}


def diagnostic(path, message, hint="", level="error"):
    return {"level": level, "path": path, "message": message, "hint": hint}


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate object key "{key}".')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite number {value} is not valid JSON.")


def load_report(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=strict_object,
                          parse_constant=reject_constant), []
    except json.JSONDecodeError as error:
        return None, [diagnostic("$", f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}.",
                                 "Correct JSON punctuation and quoting at this position.")]
    except (ValueError, UnicodeError) as error:
        return None, [diagnostic("$", str(error), "Use UTF-8 JSON with unique keys and finite numbers.")]


def check_schema(value, schema, root, path="$", errors=None):
    """Evaluate the schema vocabulary used by this bundle; not a general schema engine."""
    if errors is None:
        errors = []
    if "$ref" in schema:
        target = root
        for part in schema["$ref"][2:].split("/"):
            target = target[part]
        return check_schema(value, target, root, path, errors)
    if "anyOf" in schema:
        branches = []
        for branch in schema["anyOf"]:
            while "$ref" in branch:
                target = root
                for part in branch["$ref"][2:].split("/"):
                    target = target[part]
                branch = target
            branches.append(branch)
        alternatives = [check_schema(value, branch, root, path, []) for branch in branches]
        if any(not items for items in alternatives):
            return errors
        matching = [items for branch, items in zip(branches, alternatives)
                    if branch.get("type") == ("object" if isinstance(value, dict) else "string" if isinstance(value, str) else None)]
        errors.extend(min(matching or alternatives, key=len))
        return errors
    if "oneOf" in schema:
        # Each supported visual has a unique template discriminator. Selecting its
        # branch keeps errors actionable instead of reporting every other template.
        if not isinstance(value, dict):
            errors.append(diagnostic(path, "Expected a visual object.", "Supply a template and its data fields."))
            return errors
        allowed = []
        for branch in schema["oneOf"]:
            choices = branch["properties"]["template"]["enum"]
            allowed.extend(choices)
            if value.get("template") in choices:
                return check_schema(value, branch, root, path, errors)
        suggestion = difflib.get_close_matches(str(value.get("template", "")), allowed, n=1)
        hint = f'Use "{suggestion[0]}".' if suggestion else "Choose one of: " + ", ".join(allowed) + "."
        errors.append(diagnostic(path + ".template", f"Unknown or missing template {value.get('template')!r}.", hint))
        return errors
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    expected = schema.get("type")
    if expected and type(value) is not types[expected]:
        errors.append(diagnostic(path, f"Expected {expected}, got {type(value).__name__}.", f"Use a JSON {expected}."))
        return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(diagnostic(path, f"Unsupported value {value!r}.", "Choose one of: " + ", ".join(map(str, schema["enum"])) + "."))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(diagnostic(path, "Text must not be empty.", "Supply a meaningful description."))
        elif "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(diagnostic(path, "Text does not match the required format.",
                                     "Use nonblank text; IDs start with a letter and contain letters, digits, underscores, or hyphens."))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(diagnostic(path, "Text is too long.", f"Keep at most {schema['maxLength']} characters."))
    if type(value) is int and "minimum" in schema and value < schema["minimum"]:
        errors.append(diagnostic(path, "Number is below the minimum.", f"Use a value of at least {schema['minimum']}."))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(diagnostic(path + "." + key, "Required field is missing.", f'Add "{key}" to this object.'))
        for key, item in value.items():
            if key in properties:
                check_schema(item, properties[key], root, path + "." + key, errors)
            elif schema.get("additionalProperties") is False:
                suggestion = difflib.get_close_matches(key, properties, n=1)
                hint = f'Did you mean "{suggestion[0]}"?' if suggestion else "Remove this field or use a documented field."
                errors.append(diagnostic(path + "." + key, "Unknown field.", hint))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(diagnostic(path, "Array has too few items.", f"Supply at least {schema['minItems']} item(s)."))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(diagnostic(path, "Array has too many items.", f"Keep at most {schema['maxItems']} focused steps."))
        for index, item in enumerate(value):
            check_schema(item, schema.get("items", {}), root, f"{path}[{index}]", errors)
    return errors


def check_visual(visual, path):
    diagnostics = []
    objects = []
    if "nodes" in visual:
        node_ids = set()
        group_ids = set()
        for index, group in enumerate(visual.get("groups", [])):
            if group["id"] in group_ids:
                diagnostics.append(diagnostic(f"{path}.groups[{index}].id", "Duplicate boundary ID.", "Use a unique boundary ID."))
            group_ids.add(group["id"])
            if not any(node.get("group") == group["id"] for node in visual["nodes"]):
                diagnostics.append(diagnostic(f"{path}.groups[{index}].id", "Boundary has no member nodes.", "Assign a node to this group or remove the unused boundary."))
        for index, node in enumerate(visual["nodes"]):
            if node["id"] in node_ids:
                diagnostics.append(diagnostic(f"{path}.nodes[{index}].id", f'Duplicate node ID "{node["id"]}".', "Choose a unique ID within this visual."))
            node_ids.add(node["id"])
            if "group" in node and node["group"] not in group_ids:
                diagnostics.append(diagnostic(f"{path}.nodes[{index}].group", "Unknown boundary ID.", "Declare this group in groups or correct the node's group."))
            objects.append((node, f"{path}.nodes[{index}]"))
        for index, edge in enumerate(visual["edges"]):
            for endpoint in ("from", "to"):
                if edge[endpoint] not in node_ids:
                    diagnostics.append(diagnostic(f"{path}.edges[{index}].{endpoint}", f'Node "{edge[endpoint]}" does not exist.', "Add that node or correct the endpoint."))
            objects.append((edge, f"{path}.edges[{index}]"))
        if len(node_ids) > 10:
            diagnostics.append(diagnostic(path + ".nodes", "This graph contains more than ten nodes.", "Consider separating relationships into focused diagrams.", "warning"))
        nodes = {node["id"]: node for node in visual["nodes"]}
        if "scenario" in visual:
            scenario = visual["scenario"]
            scenario_path = path + ".scenario"
            for field in ("from", "at", "to"):
                if scenario[field] not in nodes:
                    diagnostics.append(diagnostic(scenario_path + "." + field, "Scenario node does not exist.", "Reference a node declared in this graph."))
            if len({scenario[field] for field in ("from", "at", "to")}) != 3:
                diagnostics.append(diagnostic(scenario_path, "Scenario roles must identify three distinct nodes.", "Identify the upstream participant, affected component, and downstream outcome."))
            if visual.get("sequence") or any(item.get("animate") for item in visual["nodes"]+visual["edges"]):
                diagnostics.append(diagnostic(scenario_path, "Competing playback mechanisms would tell different stories.", "Use scenario alone in this graph; keep independent transfer loops or sequence in another visual."))
            incoming = [edge for edge in visual["edges"] if edge["from"] == scenario["from"] and edge["to"] == scenario["at"]]
            outgoing = [edge for edge in visual["edges"] if edge["from"] in (scenario["from"], scenario["at"]) and edge["to"] == scenario["to"]]
            if not incoming:
                diagnostics.append(diagnostic(scenario_path + ".from", "Upstream participant is not connected to the affected component.", "Select roles matching the actual graph; do not invent a connection to fit a template."))
            if not outgoing:
                diagnostics.append(diagnostic(scenario_path + ".to", "The outcome is not connected to this workflow.", "Select an existing downstream result, or use a focused static explanation."))
            if scenario["template"] == "message-loss" and (not incoming or not outgoing or any(edge.get("transport") != "message" for edge in incoming+outgoing)):
                diagnostics.append(diagnostic(scenario_path + ".template", "Message loss requires message-delivery relationships.", "Use message-loss for actual message delivery, not a synchronous request or unfinished local execution."))
            if scenario["template"] == "interrupted-work" and scenario["from"] in nodes and scenario["at"] in nodes:
                owner = nodes[scenario["at"]].get("group")
                if not owner or nodes[scenario["from"]].get("group") != owner or not any(group["id"] == owner and group["kind"] == "process" for group in visual.get("groups", [])):
                    diagnostics.append(diagnostic(scenario_path + ".at", "Shared process lifetime is not represented.", "Use interrupted-work when request and work share an explicit process boundary; do not infer this from a shared server."))
        for index, step in enumerate(visual.get("sequence", [])):
            step_path = f"{path}.sequence[{index}]"
            if ("edge" in step) == ("node" in step):
                diagnostics.append(diagnostic(step_path, "A sequence step needs exactly one target.", "Use edge (a 1-based connection number) for a transfer, or node for an explained wait."))
            elif "edge" in step:
                number = step["edge"]
                if not 1 <= number <= len(visual["edges"]):
                    diagnostics.append(diagnostic(step_path + ".edge", "Connection number is out of range.", f"Choose an existing connection from 1 to {len(visual['edges'])}."))
                elif visual["edges"][number-1].get("transport", "request") not in ("flow", "request", "message", "read", "write", "deploy"):
                    diagnostics.append(diagnostic(step_path + ".edge", "This relationship does not describe a transfer.", "Sequence a real request/data transfer; do not animate configuration, spawn, or trigger links as payloads."))
                elif visual["edges"][number-1].get("animate"):
                    diagnostics.append(diagnostic(step_path + ".edge", "Two animation mechanisms target this connection.", "Remove animate from this edge; sequence owns its ordered playback."))
            elif step["node"] not in nodes:
                diagnostics.append(diagnostic(step_path + ".node", "Sequence node does not exist.", "Use a node ID declared in this visual."))
            elif "issue" not in nodes[step["node"]]:
                diagnostics.append(diagnostic(step_path + ".node", "Waiting has no causal explanation.", "Add issue to this node explaining what it waits for and why that matters."))
    else:
        for key in ("before", "after"):
            objects.extend((obj, f"{path}.{key}[{index}]") for index, obj in enumerate(visual.get(key, [])))
    animated = 0
    for obj, obj_path in objects:
        if "brand" in obj and obj["brand"] not in BRANDS:
            suggestion = difflib.get_close_matches(obj["brand"], BRANDS, n=1)
            hint = f'Use "{suggestion[0]}".' if suggestion else "Choose an ID from assets/brands/catalog.json, or omit brand for a generic icon."
            diagnostics.append(diagnostic(obj_path + ".brand", f'Unknown local brand "{obj["brand"]}".', hint))
        if obj.get("animate"):
            animated += 1
            if obj["status"] not in ("new", "changed"):
                diagnostics.append(diagnostic(obj_path + ".animate", "Motion requires a new or changed element/connection.", "Set animate to false or correct the status."))
    if animated > 2:
        diagnostics.append(diagnostic(path, "More than two objects are animated in this visual.", "Emphasize only the most important differences.", "warning"))
    if "nodes" in visual and not any(item["level"] == "error" for item in diagnostics):
        for vertical in (False, True):
            try:
                route_graph(visual, vertical)
            except RouteError as error:
                orientation = "narrow" if vertical else "desktop"
                diagnostics.append(diagnostic(f"{path}.edges[{error.edge}]", f"No readable {orientation} route: {error}", "Split this relationship into focused diagrams or simplify redundant connections; do not add coordinates."))
    return diagnostics


def validate(report):
    schema = json.loads((ASSETS / "report.schema.json").read_text(encoding="utf-8"))
    diagnostics = check_schema(report, schema, schema)
    if diagnostics:
        return diagnostics
    if "summary" not in report:
        diagnostics.append(diagnostic("$.summary", "No opening summary is supplied.", "For new explanations, add two short sentences stating the change and its main consequence.", "warning"))
    ids = set()
    for index, change in enumerate(report["changes"]):
        if change["id"] in ids:
            diagnostics.append(diagnostic(f"$.changes[{index}].id", "Duplicate change ID.", "Give each change a unique ID."))
        ids.add(change["id"])
        for source_index, source in enumerate(change.get("evidence", [])):
            if isinstance(source, dict) and "url" in source and not safe_source_url(source["url"]):
                diagnostics.append(diagnostic(f"$.changes[{index}].evidence[{source_index}].url", "Source URL is unsafe or not absolute.", "Use a verified http, https, file, codex, or vscode source URL."))
        if "visual" in change:
            diagnostics.extend(check_visual(change["visual"], f"$.changes[{index}].visual"))
        if "code" in change:
            code = change["code"]
            if not code["before"].strip() and not code["after"].strip():
                diagnostics.append(diagnostic(f"$.changes[{index}].code", "Both code excerpts are empty.", "Supply the relevant before or after lines, or omit code."))
            if max(len(code["before"].splitlines()), len(code["after"].splitlines())) > 12:
                diagnostics.append(diagnostic(f"$.changes[{index}].code", "Code excerpt exceeds twelve lines on one side.", "Summarize the relevant change instead of copying the complete file.", "warning"))
    if "visual" in report["context"]:
        diagnostics.extend(check_visual(report["context"]["visual"], "$.context.visual"))
    for section in ("impact", "manualChanges", "risks"):
        for index, item in enumerate(report.get(section, [])):
            if item["change"] not in ids:
                diagnostics.append(diagnostic(f"$.{section}[{index}].change", f'Unknown change ID "{item["change"]}".', "Reference an ID declared in changes."))
    covered = {item["change"] for item in report["impact"]}
    for index, change in enumerate(report["changes"]):
        if change["id"] not in covered:
            diagnostics.append(diagnostic(f"$.changes[{index}].id", "This change has no associated impact.", "Add an impact referencing this ID; describe an uncertainty if the effect is not yet known."))
    if report["mode"] == "plan":
        for index, impact in enumerate(report["impact"]):
            if impact["basis"] == "observed":
                diagnostics.append(diagnostic(f"$.impact[{index}].basis", "A proposed impact cannot be observed.", 'Use "expected" or "inferred"; put current-state observations in context.'))
    return diagnostics


def text(value):
    return escape(str(value), quote=True)


def safe_source_url(value):
    if any(ord(char) < 32 or ord(char) == 127 for char in value) or any(char.isspace() for char in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme.lower() not in ("http", "https", "file", "codex", "vscode"):
        return None
    if parsed.scheme.lower() in ("http", "https") and not parsed.netloc:
        return None
    return value if parsed.netloc or parsed.path else None


def source_href(source):
    if source.get("url"):
        return safe_source_url(source["url"])
    file = source.get("file", "")
    if PureWindowsPath(file).is_absolute():
        return PureWindowsPath(file).as_uri()
    if Path(file).is_absolute():
        return Path(file).as_uri()
    return None


def render_evidence(source):
    if isinstance(source, str):
        return f'<li>{text(source)}</li>'
    href = source_href(source)
    label = text(source["label"])
    label = f'<a href="{text(href)}">{label}</a>' if href else label
    if href and urlsplit(href).scheme.lower() == "file":
        label += '<span class="source-working-copy">Local working copy</span>'
    location = source.get("file", "")
    if "line" in source:
        location += f':{source["line"]}'
    metadata = f'<code>{text(location)}</code>' if location else ''
    if "revision" in source:
        metadata += f'<span class="source-revision">@ {text(source["revision"])}</span>'
    detail = f'<p>{text(source["detail"])}</p>' if "detail" in source else ''
    return f'<li>{label}<span class="source-location">{metadata}</span>{detail}</li>'


def status_label(status, mode):
    label = LABELS[status]
    return label + " · proposed" if mode == "plan" and status != "unchanged" else label


def badge(status, mode):
    return f'<span class="badge status-{status}">{text(status_label(status, mode))}</span>'


def icon(kind, size=28, brand=None):
    if brand:
        surface = brand_surface(brand)
        return f'<svg class="entity-icon brand-art brand-surface-{surface}" width="{size}" height="{size}" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><use href="#brand-{brand}" x="4" y="4" width="56" height="56"/></svg>'
    return f'<svg class="entity-icon" width="{size}" height="{size}" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><use href="#entity-{kind}"/></svg>'


SECTION_ICONS = {"context": "eye", "changes": "diff", "manual": "wrench", "impact": "impact", "risks": "alert"}
STATUS_ICONS = {"new": "plus", "changed": "diff", "removed": "minus", "unchanged": "info"}


def ui_icon(name, size=18):
    return f'<svg class="ui-icon" width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#ui-{name}"/></svg>'


def element(obj, mode, allow_motion=True):
    motion = " pulse" if allow_motion and obj.get("animate") else ""
    detail = f'<p>{text(obj["detail"])}</p>' if "detail" in obj else ""
    kind = obj.get("kind", "generic")
    meta = f'<code class="entity-meta">{text(obj["meta"])}</code>' if "meta" in obj else ""
    return f'<div class="element status-{obj["status"]}{motion}"><div class="element-art">{icon(kind, 42, obj.get("brand"))}</div><div class="element-copy"><span class="entity-kind">{KINDS[kind]}</span>{badge(obj["status"], mode)}<h4>{text(obj["label"])}</h4>{meta}{detail}</div></div>'


def phase_style(index, count):
    return f'--phase-name: behavior-window-{count}-{index+1}; --phase-duration: {count*4}s;'


def render_graph_svg(visual, mode, prefix, vertical=False):
    geometry = route_graph(visual, vertical)
    positions, width, height = geometry["positions"], geometry["width"], geometry["height"]
    orientation = "mobile" if vertical else "desktop"
    pieces = [f'<svg class="graph graph-{orientation}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{prefix}-title {prefix}-description">',
              f'<title id="{prefix}-title">{text(TEMPLATES[visual["template"]])}</title>',
              f'<desc id="{prefix}-description">{text(visual["caption"])} Arrow labels explain each action or condition. Directed connection details follow.</desc>', '<defs>']
    strokes = {status: f"var(--{status})" for status in LABELS}
    strokes["issue"] = "var(--risk)"
    for status, color in strokes.items():
        pieces.append(f'<marker id="{prefix}-{status}-arrow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" markerUnits="userSpaceOnUse" orient="auto"><path d="M 1 1 L 11 6 L 1 11 z" fill="{color}"/></marker>')
    pieces.append('</defs>')
    for group, (gx, gy, gw, gh), _ in geometry["groups"]:
        pieces.append(f'<g class="process-boundary"><rect class="group-box" x="{gx}" y="{gy}" width="{gw}" height="{gh}" rx="8"/></g>')
    for index, (edge, route) in enumerate(zip(visual["edges"], geometry["routes"]), 1):
        path = path_data(route["points"])
        transport = edge.get("transport", "request")
        emphasis = " has-issue" if "issue" in edge else ""
        marker = "issue" if "issue" in edge else edge["status"]
        coordinates = ";".join(f"{x:g},{y:g}" for x, y in route["points"])
        pieces.append(f'<g class="edge status-{edge["status"]} transport-{transport}{emphasis}" data-edge="{index}" data-from="{edge["from"]}" data-to="{edge["to"]}"><path class="connector-halo" d="{path}"/><path class="connector" data-points="{coordinates}" d="{path}" marker-end="url(#{prefix}-{marker}-arrow)"/>')
        if edge.get("animate"):
            symbol = packet_symbol(edge)
            if symbol:
                motion_style = text(f'offset-path: path("{path}");')
                pieces.append(f'<g class="message-packet" style="{motion_style}" aria-hidden="true"><rect class="packet-body" x="-12" y="-12" width="24" height="24" rx="5"/><use class="packet-symbol" href="#ui-{symbol}" x="-10" y="-10" width="20" height="20"/></g>')
            elif flow_signal(edge):
                motion_style = text(f'offset-path: path("{path}");')
                pieces.append(f'<g class="flow-transfer" style="{motion_style}" aria-hidden="true"><circle class="flow-signal" r="6"/><circle class="flow-signal-core" r="2"/></g>')
            else:
                pieces.append(f'<path class="connector-emphasis" d="{path}"/>')
        for step_index, step in enumerate(visual.get("sequence", [])):
            if step.get("edge") == index:
                style = phase_style(step_index, len(visual["sequence"]))
                travel_style = text(f'offset-path: path("{path}");')
                symbol = {"message": "message", "deploy": "package"}.get(transport)
                artwork = f'<rect class="packet-body" x="-12" y="-12" width="24" height="24" rx="5"/><use class="packet-symbol" href="#ui-{symbol}" x="-10" y="-10" width="20" height="20"/>' if symbol else '<circle class="behavior-signal" r="7"/><circle class="behavior-signal-core" r="2"/>'
                pieces.append(f'<g class="behavior-phase behavior-transfer" data-step="{step_index+1}" style="{style}" aria-hidden="true"><g class="behavior-travel" style="{travel_style}">{artwork}</g></g>')
        pieces.append('</g>')
    for index, route in enumerate(geometry["routes"], 1):
        x, y = route["label"]
        edge = visual["edges"][index-1]
        lines = route.get("labelLines", [edge.get("shortLabel", edge["label"])])
        box_x, box_y, box_w, box_h = route.get("labelBox", (x-17, y-12, 34, 24))
        pieces.append(f'<g class="edge-label" data-label-edge="{index}" aria-hidden="true">')
        if "labelAnchor" in route:
            anchor_x, anchor_y = route["labelAnchor"]
            if not (box_x <= anchor_x <= box_x+box_w and box_y <= anchor_y <= box_y+box_h):
                pieces.append(f'<path class="edge-label-leader" d="M {anchor_x:g} {anchor_y:g} L {x:g} {y:g}"/>')
        pieces.append(f'<rect class="edge-number-box" x="{box_x}" y="{box_y}" width="{box_w}" height="{box_h}" rx="4"/><text class="edge-label-text" x="{x}" text-anchor="middle">')
        for line_index, line in enumerate(lines):
            line_y = y - (len(lines)-1)*9 + 5 + line_index*18
            pieces.append(f'<tspan x="{x}" y="{line_y}">{text(line)}</tspan>')
        pieces.append('</text></g>')
    for node in visual["nodes"]:
        x, y, w, h, lines = positions[node["id"]]
        kind = node.get("kind", "generic")
        issue = " has-issue" if "issue" in node else ""
        brand = node.get("brand")
        artwork = f"brand-{brand}" if brand else f"entity-{kind}"
        surface = f' brand-surface-{brand_surface(brand)}' if brand else ""
        pieces.append(f'<g class="status-{node["status"]} entity-{kind}{issue}{surface}" data-node="{node["id"]}"><rect class="node-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="7"/><rect class="node-art-bg" x="{x+13}" y="{y+29}" width="54" height="54" rx="7"/><use class="node-art" href="#{artwork}" x="{x+17}" y="{y+33}" width="46" height="46"/>')
        if issue:
            pieces.append(f'<use class="node-issue-icon" href="#ui-alert" x="{x+w-26}" y="{y+8}" width="17" height="17"/>')
        if node.get("animate"):
            pieces.append(f'<rect class="node-emphasis" x="{x-2}" y="{y-2}" width="{w+4}" height="{h+4}" rx="9"/>')
        for step_index, step in enumerate(visual.get("sequence", [])):
            if step.get("node") == node["id"]:
                style = phase_style(step_index, len(visual["sequence"]))
                pieces.append(f'<g class="behavior-phase behavior-wait" data-step="{step_index+1}" style="{style}" aria-hidden="true"><rect class="behavior-wait-outline" x="{x+4}" y="{y+4}" width="{w-8}" height="{h-8}" rx="5"/><g transform="translate({x+59} {y+76})"><circle class="behavior-clock-face" r="11"/><path class="behavior-clock-hands" d="M 0 -6 V 0 L 4 2"/></g></g>')
        pieces.append(f'<text class="node-kind" x="{x+80}" y="{y+22}">{text(KINDS[kind].upper())}</text>')
        for index, line in enumerate(lines):
            pieces.append(f'<text class="node-label" x="{x+80}" y="{y+48+index*22}">{text(line)}</text>')
        for index, line in enumerate(textwrap.wrap(node.get("meta", ""), width=18)):
            pieces.append(f'<text class="node-meta" x="{x+80}" y="{y+48+len(lines)*22+index*18}">{text(line)}</text>')
        pieces.append(f'<use class="node-status-icon" href="#ui-{STATUS_ICONS[node["status"]]}" x="{x+79}" y="{y+h-25}" width="14" height="14"/><text class="node-status" x="{x+98}" y="{y+h-14}">{text(status_label(node["status"], mode))}</text>')
        pieces.append('</g>')
    for group, (gx, gy, gw, _), _ in geometry["groups"]:
        pieces.append(f'<g class="group-heading"><rect class="group-heading-bg" x="{gx+1}" y="{gy+1}" width="{gw-2}" height="32" rx="7"/><use class="group-icon" href="#entity-{group["kind"]}" x="{gx+13}" y="{gy+6}" width="22" height="22"/><text class="group-label" x="{gx+43}" y="{gy+22}">{text(group["label"])} · {KINDS[group["kind"]]}</text></g>')
    pieces.append('</svg>')
    return ''.join(pieces)


SCENARIOS = {
    "interrupted-work": {
        "title": "Process stop interrupts in-flight work",
        "normal": ("Response stays open", "Work in progress", "Waiting for this result"),
        "failed": ("Response interrupted", "Execution interrupted", "No result from this attempt"),
        "stages": ("Request and work are active", "Process stops before completion", "No result is stored by this attempt"),
    },
    "message-loss": {
        "title": "A message is lost before delivery",
        "normal": ("Message sent", "In transit", "Waiting for delivery"),
        "failed": ("Sent is not received", "Delivery lost", "Not received on this attempt"),
        "stages": ("Sender hands off a message", "Message disappears before delivery", "Receiver gets no message on this attempt"),
    },
    "bottleneck": {
        "title": "Work arrives faster than it is processed",
        "normal": ("Work arriving", "Processing slowly", "Completion takes time"),
        "failed": ("More arrivals", "Backlog accumulating", "Later work waits longer"),
        "stages": ("Work keeps arriving", "Pending work piles up at the slow stage", "Some work completes; the backlog remains"),
    },
    "saturation": {
        "title": "New work reaches an occupied capacity limit",
        "normal": ("Work arriving", "Capacity filling", "Existing work is active"),
        "failed": ("New work waits", "No free slot", "New work cannot complete yet"),
        "stages": ("Available capacity is occupied", "More work arrives while slots are full", "New work must wait for capacity"),
    },
}


def render_scenario(visual, mode):
    scenario = visual["scenario"]
    template = scenario["template"]
    pattern = SCENARIOS[template]
    nodes = {node["id"]: node for node in visual["nodes"]}
    failure = '<svg class="scenario-failure-mark" width="44" height="44" viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="18"/><path d="m15 15 14 14m0-14L15 29"/></svg>'
    pieces = [f'<div class="problem-scenario scenario-{template}" data-scenario="{template}" role="group" aria-label="Consequence scenario: {text(pattern["title"])}"><div class="scenario-heading">{ui_icon("alert", 22)}<h4>{text(pattern["title"])}</h4><span>Illustrative failure scenario</span></div><p class="scenario-condition"><strong>Condition:</strong> {text(scenario["condition"])}</p>']
    if template == "interrupted-work":
        group = next(group for group in visual["groups"] if group["id"] == nodes[scenario["at"]]["group"])
        pieces.append(f'<p class="scenario-runtime">{icon("process", 22)}<strong>{text(group["label"])}</strong><span class="scenario-state-pair" aria-hidden="true"><span class="scenario-normal">Process running</span><span class="scenario-failure">PROCESS STOPPED</span></span></p>')
    pieces.append('<div class="scenario-cards">')
    for index, role in enumerate(("from", "at", "to")):
        node = nodes[scenario[role]]
        pieces.append(f'<div class="scenario-card scenario-card-{role}" data-node-ref="{node["id"]}"><div class="scenario-component">{icon(node.get("kind", "generic"), 36, node.get("brand"))}<div><span>{text(KINDS[node.get("kind", "generic")])}</span><h5>{text(node["label"])}</h5></div></div>{badge(node["status"], mode)}')
        if role == "at":
            if template in ("interrupted-work", "message-loss"):
                glyph = "message" if template == "message-loss" else "file"
                pieces.append(f'<div class="scenario-job-area" aria-hidden="true"><span class="scenario-normal scenario-job-symbol{ " scenario-message-token" if template == "message-loss" else ""}">{ui_icon(glyph, 42)}</span><span class="scenario-failure">{failure}</span></div>')
                if template == "interrupted-work":
                    pieces.append('<div class="scenario-progress-track" aria-hidden="true"><span class="scenario-progress-fill"></span></div><p class="scenario-graphic-note">Work stops unfinished</p>')
            elif template == "bottleneck":
                pieces.append('<div class="scenario-backlog" aria-hidden="true">' + ''.join(f'<span class="scenario-backlog-item scenario-item-{item}">{ui_icon("file", 24)}</span>' for item in range(1, 5)) + '<span class="scenario-slow-worker">'+ui_icon("code", 30)+'</span></div><div class="scenario-progress-track" aria-hidden="true"><span class="scenario-progress-fill"></span></div><p class="scenario-graphic-note">Pending work accumulates</p>')
            else:
                pieces.append('<div class="scenario-capacity" aria-hidden="true">' + ''.join(f'<span class="scenario-capacity-slot scenario-item-{item}">{ui_icon("code", 26)}</span>' for item in range(1, 4)) + '</div><p class="scenario-graphic-note">Illustrative slots — not a configured count</p>')
        if role == "to":
            if template in ("interrupted-work", "message-loss"):
                pieces.append('<div class="scenario-empty-result" aria-hidden="true">'+ui_icon("file", 34)+'<span class="scenario-empty-cross">×</span></div><p class="scenario-graphic-note">No '+ ('delivery on this attempt' if template == "message-loss" else 'completed result from this attempt')+'</p>')
            else:
                pieces.append('<div class="scenario-delay" aria-hidden="true"><svg width="42" height="42" viewBox="0 0 42 42"><circle cx="21" cy="21" r="17"/><path d="M21 10v11l8 4"/></svg></div><p class="scenario-graphic-note">'+ ('Throughput continues, but work queues up' if template == "bottleneck" else 'New work waits; active work is not lost')+'</p>')
        if role == "from":
            pieces.append('<div class="scenario-input" aria-hidden="true">'+ui_icon("message" if template == "message-loss" else "file", 38)+'</div>')
        pieces.append(f'<div class="scenario-state-pair scenario-component-state" aria-hidden="true"><span class="scenario-normal">{text(pattern["normal"][index])}</span><span class="scenario-failure">{text(pattern["failed"][index])}</span></div></div>')
    pieces.append('</div><ol class="scenario-story" aria-label="Failure mechanism and result">')
    pieces.extend(f'<li><span>{index:02d}</span>{text(stage)}</li>' for index, stage in enumerate(pattern["stages"], 1))
    pieces.append(f'</ol><div class="scenario-explanation"><p><strong>Cause:</strong> {text(scenario["cause"])}</p><p class="scenario-consequence"><strong>Consequence:</strong> {text(scenario["consequence"])}</p></div><p class="scenario-note">Runtime states, not change statuses. Illustrative timing and capacity; the failure state remains visible when motion is reduced or printed. <a href="#motion-controls">Motion controls</a></p></div>')
    return ''.join(pieces)


def render_graph(visual, mode, prefix):
    pieces = [render_graph_svg(visual, mode, prefix + "-desktop"), render_graph_svg(visual, mode, prefix + "-mobile", True)]
    if "scenario" in visual:
        pieces.insert(0, render_scenario(visual, mode))
    if visual.get("sequence"):
        steps = ['<ol class="behavior-sequence" aria-label="Behavior playback steps">']
        for index, step in enumerate(visual["sequence"]):
            target = f'Wait at {next(node["label"] for node in visual["nodes"] if node["id"] == step["node"])}' if "node" in step else f'Connection {step["edge"]:02d}'
            problem = " is-wait" if "node" in step else ""
            steps.append(f'<li class="behavior-step{problem}"><span class="behavior-phase behavior-step-highlight" data-step="{index+1}" style="{phase_style(index, len(visual["sequence"]))}" aria-hidden="true"></span><span class="behavior-step-number">{index+1:02d}</span><div><strong>{text(step["label"])}</strong><span>{text(target)}</span></div></li>')
        steps.append('</ol>')
        strip = ''.join(steps)
        # Display switches restart CSS animations. Pair each canvas and strip so
        # their clocks restart together, instead of misleadingly diverging.
        pieces = [f'<div class="behavior-pane behavior-pane-{orientation}">{svg}{strip}</div>' for orientation, svg in zip(("desktop", "mobile"), pieces)]
        waiting_note = " The clock marks waiting." if any("node" in step for step in visual["sequence"]) else ""
        pieces.append(f'<p class="behavior-note">Ordered illustration, not measured timing.{waiting_note} Motion does not indicate change status. <a href="#motion-controls">Motion controls</a></p>')
    details = [node for node in visual["nodes"] if "detail" in node]
    if details:
        pieces.append('<div class="node-details">')
        for node in details:
            pieces.append(f'<div>{icon(node.get("kind", "generic"), 20, node.get("brand"))}<p><strong>{text(node["label"])}</strong><span>{text(node["detail"])}</span></p></div>')
        pieces.append('</div>')
    for group in visual.get("groups", []):
        if "detail" in group:
            pieces.append(f'<p class="group-note"><strong>{text(group["label"])}:</strong> {text(group["detail"])}</p>')
    labels = {node["id"]: node["label"] for node in visual["nodes"]}
    if visual["edges"]:
        pieces.append(f'<details class="connection-details"><summary>Connection details ({len(visual["edges"])})</summary><ol class="connections" aria-label="Directed connections">')
        for index, edge in enumerate(visual["edges"], 1):
            direction = f'{text(labels[edge["from"]])} → {text(labels[edge["to"]])}'
            transport = f'<span class="transport-label">{text(edge["transport"])}</span>' if "transport" in edge else ""
            pieces.append(f'<li class="status-{edge["status"]}"><span class="connection-index">{index:02d}</span><div><span class="connection-heading"><span class="connection-direction">{direction}</span>{transport}<span class="connection-status">{text(LABELS[edge["status"]])}</span></span><span class="connection-label">{text(edge["label"])}</span></div></li>')
        pieces.append('</ol></details>')
    issues = [(node["label"], node["issue"]) for node in visual["nodes"] if "issue" in node]
    issues += [(f'Connection {index:02d}: {labels[edge["from"]]} → {labels[edge["to"]]}', edge["issue"]) for index, edge in enumerate(visual["edges"], 1) if "issue" in edge]
    if issues:
        pieces.append('<div class="issue-notes"><h4>Why this behavior is problematic</h4><ul>')
        for label, issue in issues:
            pieces.append(f'<li>{ui_icon("alert", 20)}<div><strong>{text(label)}</strong><p>{text(issue)}</p></div></li>')
        pieces.append('</ul></div>')
    return ''.join(pieces)


def highlight_code(line):
    pattern = r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\n]*|\#[^\n]*|\b(?:await|async|const|let|return|new|import|from|if|else|true|false|export|function)\b|\b\d+\b)'''
    pieces, last = [], 0
    for match in re.finditer(pattern, line):
        pieces.append(text(line[last:match.start()]))
        token = match[0]
        category = "comment" if token.startswith(("//", "#")) else "string" if token.startswith(('"', "'")) else "number" if token.isdigit() else "keyword"
        pieces.append(f'<span class="token-{category}">{text(token)}</span>')
        last = match.end()
    pieces.append(text(line[last:]))
    return ''.join(pieces)


def render_code(code, mode):
    before, after = code["before"].splitlines(), code["after"].splitlines()
    states = {"before": ["context"]*len(before), "after": ["context"]*len(after)}
    for operation, first, last, next_first, next_last in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if operation != "equal":
            states["before"][first:last] = ["deleted"]*(last-first)
            states["after"][next_first:next_last] = ["added"]*(next_last-next_first)
    file = f'<code class="code-file">{text(code["file"])}</code>' if "file" in code else '<span>Selected code</span>'
    symbol = f'<code class="code-symbol">{text(code["symbol"])}</code>' if "symbol" in code else ""
    language = f'<span class="code-language">{text(code["language"])}</span>' if "language" in code else ""
    heading = "Illustrative proposal" if mode == "plan" else "Summarized excerpt"
    pieces = [f'<div class="code-change"><div class="code-filebar">{ui_icon("file", 20)}{file}{symbol}<span class="code-kind">{heading}</span>{language}</div><div class="code-columns">']
    for side, lines in (("before", before), ("after", after)):
        title = "Before" if side == "before" else "Proposed" if mode == "plan" else "After"
        source_line = code.get(side + "Line")
        line_note = "Source lines" if source_line is not None else "Excerpt lines"
        revision = f' · {text(code[side + "Revision"])}' if side + "Revision" in code else ''
        pieces.append(f'<div class="code-side"><div class="code-side-title"><span>{ui_icon("minus" if side == "before" else "plus", 14)}{title}{revision}</span><span class="code-line-note">{line_note}</span></div><pre class="code-excerpt" aria-label="{title} code excerpt, with {line_note.lower()}"><code>')
        if not lines:
            pieces.append('<span class="code-empty">Not present</span>')
        for index, line in enumerate(lines):
            state = states[side][index]
            sign = "−" if state == "deleted" else "+" if state == "added" else " "
            number = source_line + index if source_line is not None else index + 1
            pieces.append(f'<span class="code-line {state}"><span class="code-lineno" aria-hidden="true">{number}</span><span class="code-sign" aria-hidden="true">{sign}</span><span class="code-text">{highlight_code(line)}</span></span>')
        pieces.append('</code></pre></div>')
    pieces.append(f'</div><p class="code-summary">{text(code["summary"])}</p></div>')
    return ''.join(pieces)


def render_visual(visual, mode, prefix, baseline=False):
    template = visual["template"]
    if template == "before-after":
        content = '<div class="before-after">'
        for key, heading in (("before", "Before"), ("after", "Proposed" if mode == "plan" else "After")):
            steps = ''.join(element(item, mode) for item in visual[key])
            content += f'<div><div class="column-title">{heading}</div>{steps}</div>'
        content += '</div>'
    elif template == "comparison":
        after_label = "Proposed" if mode == "plan" else "After"
        content = f'<table class="comparison"><thead><tr><th scope="col">Element / rule</th><th scope="col">Before</th><th scope="col">{after_label}</th></tr></thead><tbody>'
        for row in visual["rows"]:
            reason = f'<p class="row-reason">Why: {text(row["reason"])}</p>' if "reason" in row else ""
            content += f'<tr class="status-{row["status"]}"><td><div class="row-name">{text(row["label"])}</div>{badge(row["status"], mode)}</td><td data-label="Before">{text(row["before"])}</td><td class="after-cell" data-label="{after_label}">{text(row["after"])}{reason}</td></tr>'
        content += '</tbody></table>'
    else:
        content = render_graph(visual, mode, prefix)
    visual_icon = "diff" if template in ("before-after", "comparison") else "topology"
    heading = "Baseline behavior" if baseline else TEMPLATES[template]
    note = "Illustrative starting point" if baseline and mode == "plan" else "Before the change" if baseline else "Relationship view"
    legend = f'<div class="problem-key">{ui_icon("alert", 17)}Problem in existing behavior — not a change status</div>' if any("issue" in item for item in visual.get("nodes", [])+visual.get("edges", [])) else ""
    classes = "visual visual-baseline" if baseline else "visual"
    symbols = {packet_symbol(edge) for edge in visual.get("edges", [])} - {None}
    flows = [edge for edge in visual.get("edges", []) if flow_signal(edge)]
    packet = bool(symbols or flows)
    focus = f' aria-describedby="{prefix}-packet-note"' if packet else ""
    guidance = ""
    if packet:
        classes += " has-packets"
        meanings = []
        if "message" in symbols:
            meanings.append("Moving envelope: message delivery.")
        if "package" in symbols:
            meanings.append("Moving package: deployment artifact.")
        if flows:
            meanings.append("Moving dots: execution flow." if all(edge.get("transport") == "flow" for edge in flows) else "Moving dots: requests or data transfers.")
        meaning = " ".join(meanings)
        guidance = f'<div class="packet-guidance" id="{prefix}-packet-note">{ui_icon("message" if "message" in symbols else "package" if symbols else "topology", 18)}<span>{meaning}<span class="packet-loop-hint"> Repeats automatically; not execution order or timing.</span><span class="packet-static-hint"> System motion is reduced; select Play to animate.</span></span><a href="#motion-controls">Motion controls</a></div>'
    return f'<figure class="{classes}"{focus}><div class="visual-heading">{ui_icon(visual_icon)}{text(heading)}<span class="visual-heading-note">{note}</span></div>{legend}{guidance}<div class="visual-content">{content}</div><figcaption>{text(visual["caption"])}</figcaption></figure>'


def section(heading, anchor, number, content):
    return f'<section class="section" id="{anchor}" aria-labelledby="heading-{anchor}"><div class="section-heading"><span class="section-number">{number:02d}</span>{ui_icon(SECTION_ICONS[anchor], 22)}<h2 id="heading-{anchor}">{heading}</h2></div>{content}</section>'


def reference(change_id, titles):
    return f'<a href="#change-{change_id}">{text(titles[change_id])}</a>'


def render(report):
    mode = report["mode"]
    brands = selected_brands(report)
    sections = [("Context", "context"), ("Proposed changes" if mode == "plan" else "Changes", "changes")]
    if report.get("manualChanges"):
        sections.append(("Manual changes required", "manual"))
    sections.append(("Expected impact" if mode == "plan" else "Impact", "impact"))
    if report.get("risks"):
        sections.append(("Important risks", "risks"))
    indexes = {anchor: index for index, (_, anchor) in enumerate(sections, 1)}
    navigation = '<a class="section-link" href="#report" aria-label="Back to summary">Summary</a>' + ''.join(f'<a class="section-link" href="#{anchor}" aria-label="{heading}">{heading}</a>' for heading, anchor in sections)
    mode_name = "Proposed solution" if mode == "plan" else "Actual changes"
    topbar = f'<div class="workspace-bar"><div class="brand-mark">{ui_icon("code", 24)}<span>Change<span class="brand-muted"> explanation</span></span></div><span class="mode">{mode_name}</span></div>'
    summary = f'<p class="summary">{text(report["summary"])}</p>' if "summary" in report else ""
    if report.get("risks"):
        links = ''.join(f'<li><a href="#risk-{index}">{text(risk["title"])}</a></li>' for index, risk in enumerate(report["risks"], 1))
        summary += f'<div class="summary-risks"><strong>Important risks</strong><ul>{links}</ul></div>'
    if len(report["changes"]) > 1:
        links = ''.join(f'<li><a href="#change-{change["id"]}">{text(change["title"])}</a></li>' for change in report["changes"])
        summary += f'<details class="change-index"><summary>{len(report["changes"])} changes</summary><ol>{links}</ol></details>'
    legend = ''.join(f'<span class="legend-item status-{status}"><span class="swatch" aria-hidden="true"></span>{text(LABELS[status])}</span>' for status in LABELS)
    code_count = sum("code" in change for change in report["changes"])
    code_meta = f'<span>{code_count} summarized code changes</span>' if code_count else ''
    header = f'<header class="masthead"><h1>{text(report["title"])}</h1>{summary}<div class="report-meta">{code_meta}<div class="legend" aria-label="Change status legend">{legend}</div></div></header><nav class="section-navigation" aria-label="Explanation sections">{navigation}</nav>'
    visuals = [report["context"].get("visual", {})] + [change.get("visual", {}) for change in report["changes"]]
    has_motion = any(visual.get("scenario") or visual.get("sequence") or any(item.get("animate") for key in ("nodes", "edges", "before", "after") for item in visual.get(key, [])) for visual in visuals)
    if has_motion:
        header += '<div class="motion-controls" id="motion-controls"><fieldset aria-describedby="motion-state"><legend>Diagram motion</legend><div class="motion-options"><input type="radio" name="diagram-motion" id="motion-system" checked><label for="motion-system">System</label><input type="radio" name="diagram-motion" id="motion-play"><label for="motion-play">Play</label><input type="radio" name="diagram-motion" id="motion-pause"><label for="motion-pause">Pause</label></div></fieldset><p id="motion-state"><span class="motion-system-normal">Following system: animations on.</span><span class="motion-system-reduced">System reduced motion: static. Select Play to animate.</span><span class="motion-playing">Playing diagrams — report-only override.</span><span class="motion-paused">Diagrams paused.</span></p></div>'
    context = report["context"]
    body = '<div class="context-grid">'
    for key, label in (("problem", "Problem / goal"), ("baseline", "Comparison baseline")):
        body += f'<div class="context-block"><span class="label">{label}</span><p>{text(context[key])}</p></div>'
    body += '</div><div class="context-notes">'
    if "scope" in context:
        body += f'<h3>Scope</h3><p>{text(context["scope"])}</p>'
    if context.get("comparison"):
        comparison = context["comparison"]
        body += f'<h3>Inspected comparison</h3><p><code>{text(comparison["base"])}</code> → <code>{text(comparison["head"])}</code>'
        if "inspectedAt" in comparison:
            body += f'<span class="comparison-date">Inspected {text(comparison["inspectedAt"])}</span>'
        body += '</p>'
        for key, label in (("included", "Included"), ("excluded", "Excluded")):
            if comparison.get(key):
                body += f'<h3>{label}</h3><ul>' + ''.join(f'<li>{text(item)}</li>' for item in comparison[key]) + '</ul>'
    for key, label in (("constraints", "Constraints"), ("assumptions", "Assumptions / unknowns")):
        if context.get(key):
            body += f'<h3>{label}</h3><ul>' + ''.join(f'<li>{text(item)}</li>' for item in context[key]) + '</ul>'
    body += '</div>'
    if "visual" in context:
        body += render_visual(context["visual"], mode, "visual-context", baseline=True)
    content = section("Context", "context", indexes["context"], body)
    titles = {change["id"]: change["title"] for change in report["changes"]}
    body = ''
    for index, change in enumerate(report["changes"], 1):
        body += f'<article class="change status-{change["status"]}" id="change-{change["id"]}"><div class="change-heading"><span class="change-id">{index:02d}</span><h3>{text(change["title"])}</h3>{badge(change["status"], mode)}</div><p class="change-description">{text(change["description"])}</p>'
        if "code" in change:
            body += render_code(change["code"], mode)
        body += f'<p class="why"><strong>Why.</strong> {text(change["why"])}</p>'
        if "visual" in change:
            body += render_visual(change["visual"], mode, "visual-" + change["id"])
        if change.get("evidence"):
            label = "Basis for proposal" if mode == "plan" else "Evidence / verification"
            body += f'<div class="evidence"><strong>{label}</strong><ul>' + ''.join(render_evidence(item) for item in change["evidence"]) + '</ul></div>'
        body += '</article>'
    if not report["changes"]:
        body = '<p class="empty">No changes in the stated scope.</p>' if mode == "review" else '<p class="empty">No changes proposed.</p>'
    content += section(sections[1][0], "changes", indexes["changes"], body)
    if report.get("manualChanges"):
        body = ''
        for index, item in enumerate(report["manualChanges"], 1):
            body += f'<div class="manual-item"><div class="item-meta"><span class="mono">Step {index:02d}</span>{reference(item["change"], titles)}</div><p>{text(item["action"])}</p>'
            for key, label in (("prerequisite", "Prerequisite"), ("verification", "Verify")):
                if key in item:
                    body += f'<p class="detail"><strong>{label}:</strong> {text(item[key])}</p>'
            body += '</div>'
        content += section("Manual changes required", "manual", indexes["manual"], body)
    body = ''
    for impact in report["impact"]:
        body += f'<div class="impact-item"><div class="item-meta">{reference(impact["change"], titles)}<span class="basis">{text(impact["basis"].capitalize())}</span></div><p>{text(impact["description"])}</p></div>'
    if not report["impact"]:
        body = '<p class="empty">No change impacts identified in the stated scope.</p>'
    content += section("Expected impact" if mode == "plan" else "Impact", "impact", indexes["impact"], body)
    if report.get("risks"):
        body = ''
        for risk_index, risk in enumerate(report["risks"], 1):
            body += f'<article class="risk" id="risk-{risk_index}"><div class="item-meta"><span class="risk-severity">{text(risk["severity"])} risk</span>{reference(risk["change"], titles)}</div><h3>{text(risk["title"])}</h3>'
            for key, label in (("condition", "When"), ("consequence", "Consequence"), ("mitigation", "Mitigation")):
                if key in risk:
                    body += f'<p><strong>{label}:</strong> {text(risk[key])}</p>'
            body += '</article>'
        content += section("Important risks", "risks", indexes["risks"], body)
    note = "Proposed design · implementation and outcomes are not verified." if mode == "plan" else "Actual changes · impact labels distinguish evidence from predictions."
    footer = f'<footer class="footer"><span>{note}</span><span>Change explanation / v1</span></footer>'
    sprites = (ASSETS / "entities.svg").read_text(encoding="utf-8") + (ASSETS / "ui-icons.svg").read_text(encoding="utf-8") + brand_sprite(brands)
    body = f'{sprites}<div class="shell">{topbar}<main class="report" id="report">{header}{content}{footer}{brand_credits(brands)}</main></div>'
    page = (ASSETS / "page.html").read_text(encoding="utf-8")
    # Substitute only template tokens, never text embedded by a report.
    styles = (ASSETS / "report.css").read_text(encoding="utf-8") + "\n" + (ASSETS / "modern.css").read_text(encoding="utf-8")
    replacements = {"TITLE": text(report["title"]), "STYLE": styles, "BODY": body}
    return re.sub(r"\{\{(TITLE|STYLE|BODY)\}\}", lambda match: replacements[match[1]], page)


def emit(diagnostics, as_json):
    valid = not any(item["level"] == "error" for item in diagnostics)
    if as_json:
        print(json.dumps({"valid": valid, "diagnostics": diagnostics}, ensure_ascii=True, indent=2))
    else:
        for item in diagnostics:
            print(f'{item["level"].upper()} {item["path"]}\n  {item["message"]}')
            if item["hint"]:
                print(f'  Fix: {item["hint"]}')
        if valid:
            print("VALID: report structure, mode, templates, references, and connector routing checked.")
    return valid


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="Validate JSON and print correction guidance")
    check.add_argument("source", type=Path)
    check.add_argument("--json", action="store_true", help="Return machine-readable diagnostics")
    generate = commands.add_parser("render", help="Validate and generate self-contained HTML")
    generate.add_argument("source", type=Path)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--force", action="store_true", help="Replace an existing generated HTML file")
    icons = commands.add_parser("icons", help="Generate a self-contained visual catalog of local component and brand icons")
    icons.add_argument("--output", type=Path, required=True)
    icons.add_argument("--force", action="store_true", help="Replace your existing generated icon catalog")
    args = parser.parse_args(argv)
    try:
        if args.command != "icons":
            report, diagnostics = load_report(args.source)
            if not diagnostics:
                diagnostics = validate(report)
            if not emit(diagnostics, getattr(args, "json", False)):
                return 1
        if args.command in ("render", "icons"):
            output = args.output.resolve()
            if output.suffix.lower() != ".html":
                raise ValueError("Output must have an .html extension.")
            if args.command == "render" and output == args.source.resolve():
                raise ValueError("Output must not replace the source JSON.")
            if output == ROOT or ROOT in output.parents:
                raise ValueError("Output must be outside the skill bundle to preserve reusable assets.")
            html = render(report) if args.command == "render" else catalog_page((ASSETS / "entities.svg").read_text(encoding="utf-8"), (ASSETS / "ui-icons.svg").read_text(encoding="utf-8"), KINDS)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w" if args.force else "x", encoding="utf-8", newline="\n") as stream:
                stream.write(html)
            print(f"HTML: {output}")
        return 0
    except FileExistsError:
        print("ERROR: Output already exists. Choose another path, or use --force for your own generated report.", file=sys.stderr)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
