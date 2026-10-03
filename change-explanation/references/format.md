# Report format v1

Author UTF-8 JSON. `assets/report.schema.json` is the authoritative field/type contract; `scripts/report.py validate` adds reference and mode checks. Unknown fields are errors so misspellings do not silently disappear. All strings are plain text, including evidence.

The renderer applies the same IDE-style charcoal theme to all templates. New elements are saturated green, modifications amber, and existing context neutral gray, with explicit status labels and matching vector icons. A labeled sticky section bar provides shortcuts. Essential content remains visible; native Connection details holds supporting edge descriptions. Theme colors and layout belong to the assets, not the report JSON.

## Document

Required fields: `version: 1`, `mode: "review" | "plan"`, `title`, `context`, `changes`, and `impact`. New explanations require a concise `summary`; legacy inputs may omit it with a warning. Optional: `manualChanges`, `risks`. Empty optional arrays omit their sections. Empty `changes` and `impact` are allowed for a scope with no changes.

`context` requires `problem` and `baseline`. Optional fields: `scope` (string), `constraints` (strings), `assumptions` (strings), `visual` (one template), and `comparison` (scope provenance). A baseline can be a Git base/head pair, versions of a specification, current behavior, or an explicitly hypothetical starting point. Never silently convert an assumption into a current-state fact.

For problem-driven reports, `context.visual` explains the baseline behavior before the remedy: input/trigger, execution location, failure mechanism, and consequence. Keep existing nodes and connections `unchanged`; annotate the problematic ones with `issue`. This is a causal explanation, not merely a map of services. In Plan mode, hypothetical baseline behavior is explicitly labeled illustrative. A visual is optional when it adds no useful context; routine changes need no invented failure mechanism.

Each change requires `id`, `title`, `status`, `description`, and `why`. IDs use letters, digits, underscores, and hyphens, starting with a letter. Optional: `code`, `visual`, `evidence` (legacy strings or structured source objects). Change status is `new`, `changed`, or `removed`. Each change needs at least one associated impact, even if that impact explains a remaining uncertainty or unchanged external behavior.


### Scope and source references

`context.comparison` requires `base` and `head` strings; optional `inspectedAt` (date/time string), `included` and `excluded` string arrays. Use resolved commit hashes for pinned comparisons. For working trees, identify staged/unstaged/untracked inclusion explicitly and state that uncommitted content is a snapshot. Plan mode may omit revision metadata for a hypothetical baseline.

A structured evidence item requires `label`; optional `file`, `line` (positive integer), `revision`, `url`, and `detail`. Explicit URLs must be verified and use http, https, file, codex, or vscode. Unsafe or relative URLs are rejected. Absolute local paths become file links; relative paths remain visible text unless an explicit URL is supplied. Never fabricate source permalinks or imply a local file URI opens an editor at a particular line. The actual line and revision remain visible alongside the link. File links are labeled Local working copy: they open current local content, even when the evidence records a historical revision. Prefer a verified pinned source permalink for historical evidence. Use `detail` for verification coverage or limitations, not a duplicate change description.

```json
{
  "label": "Inspect timeout configuration",
  "file": "src/client.py",
  "line": 40,
  "revision": "inspected commit hash",
  "url": "https://example.com/verified/source/permalink",
  "detail": "Inspected source only; runtime behavior has not been tested."
}
```

The URL above illustrates shape only; replace it with a verified reference or omit it. See `assets/example-review.json` for a real pinned documentation change without a diagram.

### Small code changes

`code` requires `summary`, `before`, and `after`, all strings. Before/after may be empty for an added/deleted excerpt, but not both. Optional: `file`, `symbol`, `language`, `beforeLine`, `afterLine` (positive source-line integers), `beforeRevision`, `afterRevision`. Use ordinary multiline strings; do not supply diff signs or HTML. The renderer computes highlighted changed lines and supplies restrained token colors.

Keep excerpts to the relevant lines, usually three to eight per side. More than twelve lines on a side produces a warning. The panel labels the result as a summarized excerpt in Review mode and an illustrative proposal in Plan mode. When `beforeLine` or `afterLine` is supplied, that side displays actual source lines and its revision. Otherwise its numbers are clearly labeled Excerpt lines. Identify fictional paths or pseudocode in Context or the summary. Include actual file references and verified source lines for real reviews; selected excerpts are not a complete patch or a line-count metric.

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

For a graph, each edge requires `from`, `to`, `label`, and `status`; optional `shortLabel` (nonblank, at most 32 characters), `animate`, `transport`, and `issue`. Use a concise full `label` when possible; `shortLabel` preserves longer supporting descriptions without making readers decode a number. Use `kind: "decision"` with a question and clear Yes/No branches for decision points. Arrow colors follow change status, while branch labels and plates remain neutral; express success, failure, and conditions in words. Transport is one of `flow`, `request`, `message`, `read`, `write`, `config`, `trigger`, `deploy`, `spawn`. Use `flow` for execution paths without implying a network protocol or payload. The renderer distinguishes asynchronous messages, configuration, and deployment connections. Endpoints reference local node IDs. Labels describe a dependency, a condition, an event, or the data being passed. Self-loops and cycles are valid, including retry and state transitions. Nodes are laid out automatically; concise labels sit directly beside their arrows. Native Connection details retains exact direction, full descriptions, transport, and status. Desktop uses a layered horizontal canvas; narrow screens show an equivalent vertical canvas. Orthogonal paths avoid nodes and ownership headings, use distinct ports, and leave a visible gap before the destination. Crossings have a small background separation and are not junctions. Label plates and their association leaders avoid nodes, arrowheads, other labels, and unrelated routes. Geometry diagnostics identify an unreadable edge and suggest splitting the diagram.

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

`animate: true` is accepted only for `new` and `changed` elements/connections. Pair it with `transport: "flow"` for an execution path, or `request`, `read`, or `write` for a synchronous transfer: a small neutral dot follows the arrow. Use `transport: "message"` to move an envelope, or `transport: "deploy"` to move a deployment-artifact package. No coordinates are needed. Choose transport from the actual or explicitly proposed behavior; spawn/config/trigger links are not payload transfers and retain brief directional line emphasis. Nodes/elements use a brief outline pulse. Moving markers stay upright, leave terminal space clear, and keep label plates beside the transfer corridor. They loop every three seconds, including after the reader spends time in Context. The cadence illustrates direction only, not measured throughput, latency, or ordering; use a sequence when supported order matters. Page and text remain stationary. More than two animated objects in a visual produces a warning. Connection status is a compact badge beside the direction and transport, wrapping naturally on narrow screens; the explanation is on the next line.

One native, keyboard-accessible **System / Play / Pause** control above Context manages all report motion without occupying sticky navigation. System is the default and respects `prefers-reduced-motion`; it explains why the report is static. Play is explicit consent to animate this page despite that preference, without modifying the operating system. Pause freezes ongoing playback, including after Play under reduced motion. System reduced-motion views keep static markers and all explanations; printing is always static regardless of the selected mode. Do not assume an animation is broken before checking the actual viewer preference.

### Consequence scenarios

For a problem-driven graph, choose a `scenario` that shows the failure mechanism and its visible outcome. All four patterns use the same small contract:

```json
"scenario": {
  "template": "interrupted-work",
  "from": "request",
  "at": "export",
  "to": "db",
  "condition": "The API process stops while this export is running.",
  "cause": "The request and export share the API process lifetime, without a durable handoff.",
  "consequence": "This unfinished export is interrupted; this attempt stores no completed result."
}
```

Every field is required. `from`, `at`, and `to` identify three distinct existing graph nodes: upstream participant, affected component, and downstream outcome. The graph must contain a `from → at` edge and a `from → to` or `at → to` edge. The scenario references the normal workflow; it does not add fictional transport links. If the real relationship cannot be represented this way, choose a focused static explanation instead.

| Pattern | Choose it when supported | Visible mechanism and consequence |
| --- | --- | --- |
| `interrupted-work` | Work and its initiating request share a process lifetime, and that process stops before completion | Progress stops unfinished, the process becomes STOPPED, the job gains an interruption mark, and this attempt stores no completed result |
| `message-loss` | A message fails to reach the receiver on the illustrated attempt | An envelope travels, disappears with a loss mark, and the receiver remains without that delivery |
| `bottleneck` | Arrivals outpace a slower stage | Pending work accumulates while processing continues; later work waits longer |
| `saturation` | A finite resource has no free capacity for new work | Slots fill, the component becomes full, and new work waits while existing work remains active |

`interrupted-work` requires `from` and `at` to share an explicit `groups` boundary with `kind: "process"`; a shared server is not sufficient. `message-loss` requires the incoming and downstream relationships to use `transport: "message"`. A scenario cannot share its graph with `sequence` or `animate` elements: independent loops could imply success after the illustrated failure. Separate those explanations into different visuals.

Use inspected facts or explicitly conditional hypotheses for `condition`, `cause`, and `consequence`. Awaiting an operation alone does not establish CPU saturation, throughput, or queue capacity; a queue icon does not establish durability. Message loss is not a stand-in for unfinished local execution. The missing-result symbol concerns **this attempt**, not deletion of the database's prior records or a guarantee that retrying can never succeed. Bottleneck and saturation graphics show illustrative items/slots, not measured or configured counts. The validator checks structure and relationships, not whether the evidence supports the diagnosis.

The renderer owns the twelve-second cycle: activity develops, the failure condition becomes visible, and the outcome is held for the latter half before replay. Condition, cause, consequence, and the three labeled stages always remain readable. Static reduced-motion and print views show the held failure state rather than an unexplained busy state. Baseline change statuses stay `unchanged`; stopped, lost, backlogged, and full are separate runtime states. The original topology remains beneath the focused scenario for context. Verify the start, transition, and held outcome, not just that an animation exists.

### Ordered baseline behavior

Graph templates optionally accept `sequence`, an ordered array of two to five steps. Each step requires a plain-text `label` and exactly one target:

- `edge`: a **1-based connection number**, matching the connection array and supporting list order. It must be an execution flow, request, message, read, write, or deployment transfer; an omitted transport means request. Do not also set `animate` on that edge.
- `node`: a local node ID for a waiting step. That node must have an `issue` explaining what it waits for and the consequence.

```json
"sequence": [
  {"edge": 1, "label": "Request enters API"},
  {"node": "request", "label": "Request waits for export"},
  {"edge": 3, "label": "Store result; then reply"}
]
```

Array order is authored causal order, not inferred from topology. In Context, existing nodes and edges remain `unchanged`; sequence is distinct from delta emphasis. Request/read/write signals use a neutral dot rather than pretending synchronous calls are queued messages. Messages and deployment artifacts retain their proper glyphs. The waiting step shows a clock and moving problem outline; a synchronized step strip explains each phase. The renderer loops fixed illustrative four-second phases, not measured durations. All labels and issue notes remain visible when motion is disabled; static views show the transfer markers and waiting indication without claiming an active phase. Keep factual order supported by inspection, or explicitly mark it illustrative in Plan mode. A normal completion sequence does not depict a failed attempt: use a consequence scenario or explicit failure-state diagram when interruption, loss, or overload is the problem. Split longer explanations instead of supplying geometry or timing fields.

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

It checks desktop/tablet/narrow layout, visible sections, node/arrow text and boundary-title fit, arrow direction and destination gaps, paths avoiding nodes/headings, distinct connector segments, unobstructed readable arrow labels, actual marker trajectory and automatic looping after a reading delay, synchronized sequence phases, consequence-scenario start and held outcome, representative text contrast (including diff tokens and problem explanations), and bounded decorative emphasis. It records the native preference before emulation and verifies System/Play/Pause under reduced motion plus static printing. It saves baseline/change screenshots. This is a focused preview check, not a complete accessibility audit or an evidence check for the claimed mechanism. Python validation/rendering does not require this browser helper.
