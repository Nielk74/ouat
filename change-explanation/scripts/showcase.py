"""Build an explorer-only gallery from the real report renderer and local assets."""

import copy
from html import escape
import json
import re
import xml.etree.ElementTree as ET

import brands


def transfer(transport, animate=False):
    roles = {
        "flow": ("function", "Next step", "function", "Continue", "Continue execution"),
        "request": ("client", "Client", "server", "API", "Call API"),
        "message": ("service", "Producer", "queue", "Queue", "Publish message"),
        "read": ("service", "Service", "database", "Database", "Read records"),
        "write": ("worker", "Worker", "storage", "Storage", "Save result"),
        "config": ("config", "Configuration", "service", "Service", "Apply settings"),
        "trigger": ("cron", "Schedule", "worker", "Worker", "Trigger work"),
        "deploy": ("repository", "Build artifacts", "server", "Server", "Deploy artifact"),
        "spawn": ("process", "Process", "thread", "Thread", "Start thread"),
    }
    kind_a, label_a, kind_b, label_b, label = roles[transport]
    return {"template": "communication",
            "nodes": [{"id": "a", "label": label_a, "kind": kind_a, "status": "unchanged"},
                      {"id": "b", "label": label_b, "kind": kind_b, "status": "new"}],
            "edges": [{"from": "a", "to": "b", "label": label, "status": "new", "transport": transport, "animate": animate}]}


def visual_demos(renderer):
    plan = json.loads((renderer.ASSETS / "example-plan.json").read_text(encoding="utf-8"))
    system = json.loads((renderer.ASSETS / "example-system.json").read_text(encoding="utf-8"))
    demos = []

    def add(identifier, group, title, description, visual):
        visual.pop("caption", None)
        demos.append({"id": identifier, "group": group, "title": title, "description": description, "visual": visual})

    layout_examples = [
        ("before-after", "Before / after", "Recovery is added between a failed attempt and the result.", plan["changes"][0]["visual"]),
        ("flow", "Process flow", "A decision controls whether the request retries or returns.", plan["changes"][1]["visual"]),
        ("comparison", "Rules / data comparison", "Compare retry limits against the existing contract.", plan["changes"][2]["visual"]),
        ("state-transitions", "State transitions", "Requests move between attempting, waiting, and finished.", plan["changes"][3]["visual"]),
        ("communication", "Processes / messages", "A queue separates the API from background work.", system["changes"][0]["visual"]),
    ]
    for template, title, description, source in layout_examples:
        visual = copy.deepcopy(source)
        for key in ("nodes", "edges", "before", "after"):
            for item in visual.get(key, []):
                item.pop("animate", None)
        add("layout-" + template, "layouts", title, description, visual)
    dependency = {"template": "dependency-map", "caption": "This illustrative build agent reads a repository and receives configuration. The removed configuration relationship is explicitly labeled.",
                  "groups": [{"id": "build", "label": "Build", "kind": "ci-worker", "detail": "An illustrative ownership boundary; a boundary does not imply network isolation."}],
                  "nodes": [{"id": "repo", "label": "Source repository", "kind": "repository", "status": "unchanged", "brand": "github"},
                            {"id": "config", "label": "Old configuration", "kind": "config", "status": "removed"},
                            {"id": "agent", "label": "Build agent", "kind": "ci-worker", "status": "changed", "brand": "teamcity", "group": "build", "meta": "build / test", "detail": "Metadata gives the component a concrete role."}],
                  "edges": [{"from": "repo", "to": "agent", "label": "Read source", "transport": "read", "status": "unchanged"},
                            {"from": "config", "to": "agent", "label": "Remove old settings", "shortLabel": "Old settings", "transport": "config", "status": "removed"}]}
    add("layout-dependency-map", "layouts", "Dependency map", "The build agent keeps its source dependency and removes old settings.", dependency)

    for transport, title, description in (
        ("flow", "Execution flow", "A dot shows the direction of execution."),
        ("message", "Message delivery", "An envelope follows the delivery route."),
        ("deploy", "Deployment artifact", "A package follows the deployment route."),
        ("request", "Synchronous request", "A dot follows the request; reads and writes use the same motion."),
        ("config", "Brief connection emphasis", "The connection highlights twice; use Replay to repeat it."),
    ):
        add("motion-" + transport, "motion", title, description, transfer(transport, True))
    pulse = copy.deepcopy(layout_examples[0][3])
    pulse["after"] = [{"label": "Updated component", "kind": "service", "status": "changed", "animate": True}]
    add("motion-element", "motion", "Brief component emphasis", "An outline briefly highlights the changed component.", pulse)
    node_pulse = transfer("flow")
    node_pulse["nodes"][1]["animate"] = True
    add("motion-node", "motion", "Brief node emphasis", "An outline briefly highlights the new node.", node_pulse)
    sequence = {"template": "communication", "caption": "Illustrative ordered playback: submit a request, wait for an available slot, then save the result. Four-second steps explain order rather than measured latency.",
                "nodes": [{"id": "client", "label": "Caller", "kind": "client", "status": "unchanged"},
                          {"id": "worker", "label": "Worker", "kind": "worker", "status": "unchanged", "issue": "This example waits for a free execution slot before saving the result."},
                          {"id": "store", "label": "Results", "kind": "storage", "status": "unchanged"}],
                "edges": [{"from": "client", "to": "worker", "label": "Submit request", "transport": "request", "status": "unchanged"},
                          {"from": "worker", "to": "store", "label": "Save result", "transport": "write", "status": "unchanged"}],
                "sequence": [{"edge": 1, "label": "Submit"}, {"node": "worker", "label": "Wait for a slot"}, {"edge": 2, "label": "Save"}]}
    add("motion-sequence", "motion", "Ordered transfers and waiting", "The worker waits for a free slot between submission and saving.", sequence)
    patterns = {
        "interrupted-work": ("Interrupted work", "A shared process stops before work finishes; this attempt produces no completed result.", "The process stops during execution.", "Request and work share one process lifetime.", "This attempt is interrupted and stores no completed result; a later retry remains possible."),
        "message-loss": ("Message loss", "A message disappears before reaching the receiver.", "A message is lost before delivery.", "This delivery attempt loses the message in transit.", "The downstream participant receives no message on this attempt; later delivery remains possible."),
        "bottleneck": ("Bottleneck", "Pending work accumulates while processing continues slowly.", "Work arrives faster than it can be processed.", "Processing throughput is lower than the arrival rate.", "A backlog grows and later work takes longer; processing has not stopped."),
        "saturation": ("Capacity saturation", "All illustrative slots are occupied; new work waits while existing work stays active.", "New work arrives while capacity is full.", "The affected component has no free execution slot.", "New work waits for capacity; existing work continues and is not lost."),
    }
    for template, (title, description, condition, cause, consequence) in patterns.items():
        shared = template == "interrupted-work"
        lost = template == "message-loss"
        visual = {"template": "communication", "caption": description + " This is an illustrative condition, not a finding about a project.",
                  "nodes": [{"id": "from", "label": "API request" if shared else "Producer", "kind": "function" if shared else "service", "status": "unchanged"},
                            {"id": "at", "label": "Build result" if shared else "Delivery" if lost else "Worker", "kind": "function" if shared else "queue" if lost else "worker", "status": "unchanged", "issue": cause},
                            {"id": "to", "label": "Consumer" if lost else "Results", "kind": "worker" if lost else "storage", "status": "unchanged"}],
                  "edges": [{"from": "from", "to": "at", "label": "Send message" if lost else "Start work", "transport": "message" if lost else "request", "status": "unchanged"},
                            {"from": "at", "to": "to", "label": "Deliver message" if lost else "Save result", "transport": "message" if lost else "write", "status": "unchanged"}],
                  "scenario": {"template": template, "from": "from", "at": "at", "to": "to", "condition": condition, "cause": cause, "consequence": consequence}}
        if shared:
            visual["groups"] = [{"id": "runtime", "label": "API process", "kind": "process"}]
            visual["nodes"][0]["group"] = visual["nodes"][1]["group"] = "runtime"
        add("scenario-" + template, "motion", title, description, visual)
    schema = json.loads((renderer.ASSETS / "report.schema.json").read_text(encoding="utf-8"))
    for transport in schema["$defs"]["edge"]["properties"]["transport"]["enum"]:
        add("transport-" + transport, "connections", transport.capitalize(), "", transfer(transport))
    return demos


def element_example():
    return {"version": 1, "mode": "review", "title": "A sample timeout change", "summary": "The timeout increases from 5 to 10 seconds.",
            "context": {"baseline": "A five-second timeout.",
                        "comparison": {"base": "demo-base", "head": "demo-head", "inspectedAt": "Example", "included": ["Client timeout"], "excluded": ["Other settings"]},
                        "constraints": ["Preserve the response shape."]},
            "changes": [{"id": "sample-timeout", "title": "Increase the timeout", "status": "changed", "description": "Requests have five extra seconds to complete.",
                         "evidence": [{"label": "Timeout setting", "file": "example/client.py", "line": 40, "revision": "demo-head"}],
                         "code": {"file": "example/client.py", "symbol": "request()", "language": "python", "beforeLine": 40, "afterLine": 40, "beforeRevision": "demo-base", "afterRevision": "demo-head",
                                  "before": "timeout = 5\nresponse = request(timeout=timeout)\nreturn response", "after": "timeout = 10\nresponse = request(timeout=timeout)\nreturn response"}}],
            "manualChanges": [{"change": "sample-timeout", "action": "Update any environment override.", "prerequisite": "Locate the override.", "verification": "Check the effective timeout."}],
            "impact": [{"change": "sample-timeout", "description": "The source contains the new timeout.", "basis": "observed"},
                       {"change": "sample-timeout", "description": "Calls may wait longer before timing out.", "basis": "inferred"},
                       {"change": "sample-timeout", "description": "Fewer timeouts would need measurement.", "basis": "expected"}],
            "risks": [{"change": "sample-timeout", "title": "Longer resource occupancy", "severity": "important", "condition": "Slow upstream responses.", "consequence": "Connections remain open longer.", "mitigation": "Check the end-to-end deadline."}]}


def recipe(value):
    serialized = escape(json.dumps(value, ensure_ascii=False, indent=2))
    return f'<details class="demo-recipe"><summary>JSON recipe</summary><div class="recipe-actions"><button type="button" data-copy-json>Copy JSON</button><span class="copy-status" role="status"></span></div><pre class="recipe-json"><code>{serialized}</code></pre></details>'


def render_showcase(renderer):
    r = renderer
    demos = visual_demos(r)
    schema = json.loads((r.ASSETS / "report.schema.json").read_text(encoding="utf-8"))
    for demo in demos:
        errors = r.check_schema(demo["visual"], schema["$defs"]["visual"], schema) + r.check_visual(demo["visual"], demo["id"])
        if errors:
            raise ValueError(f'Invalid showcase example {demo["id"]}: {errors}')
    ui_source = (r.ASSETS / "ui-icons.svg").read_text(encoding="utf-8")
    glyphs = [node.attrib["id"] for node in ET.fromstring(ui_source).iter() if node.tag.endswith("symbol")]
    cards = []

    def icon_card(identifier, title, category, artwork, selection, extra=""):
        searchable = escape(f"{identifier} {title} {category}".lower(), quote=True)
        cards.append(f'<div class="icon-card" data-icon-id="{identifier}" data-category="{escape(category, quote=True)}" data-search="{searchable}"><span class="icon-tile">{artwork}</span><span class="icon-category">{escape(category)}</span><h3>{escape(title)}</h3><code>{escape(selection)}</code>{extra}</div>')

    for kind, title in r.KINDS.items():
        icon_card("entity-" + kind, title, "Generic components", r.icon(kind, 52), f'"kind": "{kind}"')
    for identifier in glyphs:
        name = identifier[3:]
        icon_card(identifier, name.replace("-", " ").capitalize(), "Renderer glyphs", r.ui_icon(name, 40), identifier)
    for item in brands.CATALOG["icons"]:
        brand = item["id"]
        extra = '<span class="archived-mark">Archived mark</span>' if item.get("editionNote") else ''
        extra += f'<a href="{escape(item["source"], quote=True)}">Source / brand terms</a>'
        icon_card("brand-" + brand, item["title"], item["category"], r.icon("generic", 52, brand), f'"brand": "{brand}"', extra)

    controls = r.motion_controls([demo["visual"] for demo in demos], showcase=True)
    sections = (("layouts", "Layouts"), ("motion", "Motion"), ("connections", "Connections"), ("icons", "Icons"), ("elements", "Elements"))
    nav = '<a href="#report">Overview</a>' + ''.join(f'<a href="#{identifier}">{escape(title)}</a>' for identifier, title in sections)
    body = (r.ASSETS / "entities.svg").read_text(encoding="utf-8") + ui_source + brands.sprite(brands.BRANDS)
    body += '<main class="showcase" id="report"><header class="showcase-hero"><h1>Change Explanation</h1><p class="summary">Explore layouts, motion and icons. Open a recipe to reuse a pattern.</p><p class="showcase-note">Illustrative examples.</p><div class="legend" aria-label="Change status legend">'
    body += ''.join(f'<span class="legend-item status-{status}"><span class="swatch" aria-hidden="true"></span>{escape(title)}</span>' for status, title in r.LABELS.items())
    body += '</div></header>'
    body += f'<div class="showcase-toolbar"><nav class="section-navigation" aria-label="Showcase sections">{nav}</nav>{controls}</div>'
    for identifier, title in sections[:3]:
        body += f'<section class="showcase-section" id="{identifier}"><h2>{escape(title)}</h2>'
        for demo in (demo for demo in demos if demo["group"] == identifier):
            replay = '<button type="button" class="demo-replay">Replay this demo</button>' if identifier == "motion" else ''
            body += f'<article class="showcase-demo" id="{demo["id"]}"><div class="demo-heading"><h3>{escape(demo["title"])}</h3>{replay}</div>'
            if demo["description"]:
                body += f'<p class="demo-description">{escape(demo["description"])}</p>'
            body += r.render_visual(demo["visual"], "review", "showcase-" + demo["id"]) + recipe(demo["visual"]) + '</article>'
        body += '</section>'
    categories = ["Generic components", "Renderer glyphs"] + list(dict.fromkeys(item["category"] for item in brands.CATALOG["icons"]))
    options = ''.join(f'<option>{escape(category)}</option>' for category in categories)
    body += '<section class="showcase-section icon-library" id="icons"><h2>Icons</h2>'
    body += f'<div class="icon-search-controls"><label>Search icons<input type="search" id="icon-search" placeholder="Try queue, Python, or TeamCity" aria-controls="showcase-icon-grid"></label><label>Category<select id="icon-category"><option value="">All icons</option>{options}</select></label><button type="button" id="icon-reset">Reset</button><output id="icon-count" role="status">{len(cards)} icons</output></div><p id="icon-empty" hidden>No icons match. Clear your search or choose another category.</p><div class="icon-grid" id="showcase-icon-grid">{"".join(cards)}</div>'
    body += '<p class="catalog-note">Logos preserve their original artwork and neutral contrast surfaces. Archived marks are labeled. Check the individual source and brand terms before reuse.</p>' + brands.credits(brands.BRANDS) + '</section>'
    body += '<section class="showcase-section" id="elements"><h2>Elements</h2><div class="showcase-statuses">'
    for status, title in r.LABELS.items():
        body += r.element({"label": title, "kind": "service", "status": status}, "review")
    body += '</div><article class="showcase-demo" id="sample-explanation"><div class="demo-heading"><h3>A complete small explanation</h3></div>'
    example = element_example()
    errors = r.validate(example)
    if errors:
        raise ValueError(f"Invalid showcase report example: {errors}")
    rendered = r.render(example)
    body += '<div class="showcase-report-example">' + re.search(r'<header class="masthead">.*?</header>', rendered, re.S).group() + ''.join(re.findall(r'<section class="section".*?</section>', rendered, re.S)) + '</div>' + recipe(example) + '</article></section>'
    body += '</main>'
    body += '<script>' + (r.ASSETS / "showcase.js").read_text(encoding="utf-8") + '</script>'
    styles = '\n'.join((r.ASSETS / name).read_text(encoding="utf-8") for name in ("report.css", "modern.css", "showcase.css"))
    page = (r.ASSETS / "page.html").read_text(encoding="utf-8")
    values = {"TITLE": "Change Explanation — showcase", "STYLE": styles, "BODY": body}
    return re.sub(r"\{\{(TITLE|STYLE|BODY)\}\}", lambda match: values[match[1]], page).replace('Skip to report</a>', 'Skip to showcase</a>')
