# Report format v1

Author UTF-8 JSON. `assets/report.schema.json` is the authoritative field/type contract; `scripts/report.py validate` adds reference and mode checks. Unknown fields are errors so misspellings do not silently disappear. All strings are plain text, including evidence.

The renderer applies the same IDE-style charcoal theme to all templates. New elements are saturated green, modifications amber, and existing context neutral gray, with explicit status labels and matching vector icons. A compact toolbar provides section-anchor shortcuts; all report content remains visible. Theme colors and layout belong to the assets, not the report JSON.

## Document

Required fields: `version: 1`, `mode: "review" | "plan"`, `title`, `context`, `changes`, and `impact`. Optional: `summary`, `manualChanges`, `risks`. Empty optional arrays omit their sections. Empty `changes` and `impact` are allowed for a scope with no changes.

`context` requires `problem` and `baseline`. Optional fields: `scope` (string), `constraints` (strings), `assumptions` (strings), and `visual` (one template). A baseline can be a Git base/head pair, versions of a specification, current behavior, or an explicitly hypothetical starting point. Never silently convert an assumption into a current-state fact.

For problem-driven reports, `context.visual` explains the baseline behavior before the remedy: input/trigger, execution location, failure mechanism, and consequence. Keep existing nodes and connections `unchanged`; annotate the problematic ones with `issue`. This is a causal explanation, not merely a map of services. In Plan mode, hypothetical baseline behavior is explicitly labeled illustrative. A missing baseline visual produces a guidance warning when changes are present; no failure mechanism should be invented for a routine change.

Each change requires `id`, `title`, `status`, `description`, and `why`. IDs use letters, digits, underscores, and hyphens, starting with a letter. Optional: `code`, `visual`, `evidence` (strings). Change status is `new`, `changed`, or `removed`. Each change needs at least one associated impact, even if that impact explains a remaining uncertainty or unchanged external behavior.

### Small code changes

`code` requires `summary`, `before`, and `after`, all strings. Before/after may be empty for an added/deleted excerpt, but not both. Optional: `file`, `symbol`, `language`. Use ordinary multiline strings; do not supply diff signs or HTML. The renderer computes highlighted changed lines and supplies restrained token colors.

Keep excerpts to the relevant lines, usually three to eight per side. More than twelve lines on a side produces a warning. The panel labels the result as a summarized excerpt in Review mode and an illustrative proposal in Plan mode. The displayed line numbers are relative to each excerpt, not source-file line numbers. Identify fictional paths or pseudocode in Context or the summary. Include actual file references and verified source lines for real reviews; selected excerpts are not a complete patch or a line-count metric.

```json
{
  "file": "src/api/exports.ts",
  "language": "typescript",
  "summary": "Move execution out of the request; return a queued job handle.",
  "before": "await buildExport(accountId);",
  "after": "await exportQueue.publish({ id: jobId, accountId });"
}
```

Each impact requires `change` (change ID), `description`, and `basis` (`observed`, `inferred`, or `expected`). `observed` means directly supported by inspection or verification; `inferred` means reasoned from available material; `expected` means predicted. Plan mode does not accept `observed` impacts.

Each manual change requires `change` and `action`; optional `prerequisite` and `verification`. Array order is the action order.

Each risk requires `change`, `title`, `severity` (`important` or `critical`), `condition`, and `consequence`; optional `mitigation`. Keep only material risks, with concrete causal explanations.

## Template selection

| Template | Choose it for | Required data |
| --- | --- | --- |
| `before-after` | Old and new behavior, UI, or structure | `before`, `after`: arrays of elements |
| `flow` | Steps, decisions, branches, data movement | `nodes`, `edges` |
| `dependency-map` | A changed component and affected consumers | `nodes`, `edges` |
| `comparison` | Rules, configuration, fields, interfaces | `rows`: comparisons |
| `state-transitions` | Events and changes between states | `nodes`, `edges` with event labels |
| `communication` | Processes, threads, messages, queues, and ownership | `nodes`, `edges`; optional `groups` |

Every visual requires `template` and `caption`. Caption explains the relationship or difference, rather than merely naming the diagram. The renderer determines positions; no coordinates are accepted. A template identifies a relationship, not a technical domain: the same flow can explain code, deployment, or a human process.

### Elements and graph nodes

An element requires `label` and `status`; optional `kind`, `brand`, `meta`, `detail`, and `animate` (boolean, defaults false). Status: `new`, `changed`, `removed`, `unchanged`. `meta` is a short technical label, such as a queue name, config value, or process identifier. A graph node has the same fields plus required `id`, optional `group`, and optional `issue` (nonblank text). IDs are local to that diagram. Every before/after element and graph node is displayed with a status label. Existing context remains readable.

`issue` explains why that node or connection is problematic. It adds a red problem indicator and an always-visible causal note without changing the element's change status. For example, a baseline process stays `unchanged` while `issue` explains that a long inline job keeps its request open. State the condition and consequence, not just “bad design.” This annotation is separate from important risks introduced by the proposal.

`kind` selects a reusable vector illustration, defaulting to `generic`:

| Kinds | Meaning |
| --- | --- |
| `server`, `client`, `service` | Host or serving endpoint, caller, logical service |
| `config`, `cron`, `ci-worker` | Configuration, scheduled trigger, CI/CD agent |
| `worker`, `process`, `thread` | Execution role, isolated runtime process, actual execution thread |
| `queue`, `message`, `database`, `storage` | Buffered handoff, payload, records, stored artifacts |
| `repository` | Source-code repository; independent of its hosting provider |
| `function`, `decision`, `generic` | Code unit, logic condition, other component |

Use the type supported by the code or proposal. Async tasks are not necessarily OS threads; queues are not necessarily durable. Describe relevant guarantees in the caption or evidence instead of relying on the icon.

`brand` optionally selects a local logo independently of the role: `{ "kind": "ci-worker", "brand": "teamcity", "label": "Build agent", "status": "changed" }`. Use IDs from `assets/brands/catalog.json`; the validator rejects unknown IDs with correction guidance. Brands include TeamCity, Jenkins, GitHub/GitLab/Bitbucket, AWS/Azure/Google Cloud, Docker/Kubernetes, databases, messaging, observability, security, runtimes, and collaboration tools. A generic repository needs only `kind: "repository"`; a GitHub repository can additionally specify `brand: "github"`. Do not infer that a project uses a product simply because its mark is available.

The renderer preserves brand geometry and colors, adds a light icon tile when needed for a dark mark, and keeps change status on the surrounding component. Selected logos are embedded inline for offline use; no external assets are loaded. The catalog records each SVG's upstream download, source, revision, license information, guidelines, and any archived-mark note. Some icons come from an older pinned set and are labeled archived. Brand terms and individual licenses still apply; missing license metadata is not permission. Credits and required license links are included in generated HTML. Inspect the visual library with `python <skill-folder>/scripts/report.py icons --output icon-library.html`.

For a graph, each edge requires `from`, `to`, `label`, and `status`; optional `animate`, `transport`, and `issue`. Transport is one of `request`, `message`, `read`, `write`, `config`, `trigger`, `deploy`, `spawn`. The renderer distinguishes asynchronous messages, configuration, and deployment connections. Endpoints reference local node IDs. Labels describe a dependency, a condition, an event, or the data being passed. Self-loops and cycles are valid, including retry and state transitions. Nodes are laid out automatically; numbered connections map to an always-visible list retaining exact direction and labels. Desktop uses a layered horizontal canvas; narrow screens show an equivalent vertical canvas. Orthogonal paths avoid nodes and ownership headings, use distinct ports, and leave a visible gap before the destination. Crossings have a small background separation and are not junctions. Connection numbers avoid nodes, arrowheads, and other paths. Geometry diagnostics identify an unreadable edge and suggest splitting the diagram.

`groups` is optional for any graph template. Each boundary requires `id`, `label`, `kind` (`server`, `process`, `ci-worker`, or `worker`); optional `detail`. Assign a node using `group: "boundary-id"`. Each declared boundary needs a member; IDs must be unique. Groups show ownership, not merely proximity. The layout keeps other nodes outside the boundary. Nested boundaries are not part of v1; use a process node and explicit spawn links inside a host, or a separate diagram for deeper ownership.

```json
{
  "template": "communication",
  "caption": "The process owns a thread inside the worker host; the database remains outside it.",
  "groups": [{"id": "host", "label": "Worker host", "kind": "server"}],
  "nodes": [
    {"id": "process", "label": "Consumer", "kind": "process", "group": "host", "status": "new"},
    {"id": "thread", "label": "Thread A", "kind": "thread", "group": "host", "status": "new"},
    {"id": "db", "label": "Results", "kind": "database", "status": "unchanged"}
  ],
  "edges": [
    {"from": "process", "to": "thread", "label": "Assign job", "transport": "spawn", "status": "new"},
    {"from": "thread", "to": "db", "label": "Persist result", "transport": "write", "status": "new"}
  ]
}
```

`animate: true` is accepted only for `new` and `changed` elements/connections. Use it sparingly for the most significant difference. Nodes/elements use a brief local outline pulse. Edges with `transport: "message"` move a small package from source toward destination using the same routed path; other animated edges retain brief directional line emphasis. No extra animation field or coordinates are needed. Choose message transport only for an actual or explicitly proposed payload transfer, not merely to obtain this effect. The package remains upright and leaves terminal space clear. Number plates sit beside package routes so both remain visible. Packages loop automatically every three seconds, including after the user reads Context, with a keyboard-accessible native Pause packets checkbox per relevant diagram. The cadence illustrates direction only: it is not measured throughput, latency, or ordering. Page and text remain stationary. More than two animated objects in a visual produces a warning. Reduced-motion and print rendering keep static packages and never animate.

### Before / after example

```json
{
  "template": "before-after",
  "caption": "Successful requests follow the existing path; only transient failures gain a retry.",
  "before": [
    {"label": "Request", "status": "unchanged"},
    {"label": "Failure ends the request", "status": "removed"}
  ],
  "after": [
    {"label": "Request", "status": "unchanged"},
    {"label": "Bounded retry", "status": "new", "animate": true},
    {"label": "Result or final error", "status": "changed"}
  ]
}
```

### Graph example

```json
{
  "template": "dependency-map",
  "caption": "The client remains unchanged; the service gains a dependency on a retry policy.",
  "nodes": [
    {"id": "client", "label": "Client", "status": "unchanged"},
    {"id": "service", "label": "Service", "status": "changed"},
    {"id": "policy", "label": "Retry policy", "status": "new"}
  ],
  "edges": [
    {"from": "client", "to": "service", "label": "Existing request", "status": "unchanged"},
    {"from": "service", "to": "policy", "label": "Consult before retrying", "status": "new"}
  ]
}
```

### Comparisons

Each row requires `label`, `before`, `after`, `status`; optional `reason`. Status accepts all four values. Mark an unchanged row as such if it provides useful context. Use a literal explanation such as "Not present" for an absent value; do not use an empty string.

```json
{
  "template": "comparison",
  "caption": "Retry limits change while the successful response contract stays the same.",
  "rows": [
    {"label": "Attempts", "before": "1", "after": "At most 3", "status": "changed", "reason": "Bound recovery work."},
    {"label": "Response", "before": "Existing payload", "after": "Existing payload", "status": "unchanged"}
  ]
}
```

## Diagnostics and correction

Logo contrast is a separate preview check from text contrast. Monochrome brand marks use the stronger of neutral light/dark tiles (minimum 3:1 design target), independent of change status or problem highlighting. The browser helper measures the rendered tile and repeats graph checks under each status and issue state. Multicolor official marks retain curated tiles and need visual inspection; their metadata hex alone cannot establish whole-logo contrast. Do not alter logo colors to repair a background problem.

Commands:

```text
python <skill-folder>/scripts/report.py validate report.json
python <skill-folder>/scripts/report.py validate report.json --json
python <skill-folder>/scripts/report.py render report.json --output report.html
```

Errors prevent rendering and give a JSON path and correction hint. Invalid JSON gives line/column; duplicate keys and non-finite numbers are rejected. Warnings flag unusually large graphs or excessive emphasis without inventing an arbitrary diagram-size limit. The validator checks this schema's vocabulary plus semantic references; it is not a general-purpose JSON Schema implementation.

Exit code 0: valid input or successful render. Exit code 1: invalid input. Exit code 2: read/write or command error. Existing HTML is preserved unless `--force` is supplied. Neither validation nor rendering verifies source accuracy, performs manual actions, or changes the system described by the report.

For optional browser verification, `scripts/preview_check.mjs` uses Node 22+ and a local Chromium executable without npm packages:

```text
node <skill-folder>/scripts/preview_check.mjs report.html previews <browser-executable>
```

It checks desktop/tablet/narrow layout, visible sections, node text and boundary-title fit, arrow direction and destination gaps, paths avoiding nodes/headings, distinct connector segments, unobstructed connection numbers, package trajectory and automatic looping after a reading delay, labeled pause/resume controls, representative text contrast (including diff tokens and problem explanations), brief decorative emphasis, and static packages with reduced motion. It saves baseline/change screenshots. This is a focused preview check, not a complete accessibility audit. Python validation/rendering does not require this browser helper.
