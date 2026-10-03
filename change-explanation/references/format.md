# Report format v1

Author UTF-8 JSON with plain-text strings. [The schema](../assets/report.schema.json) is authoritative for fields, types, and enums; unknown fields are errors. The validator also checks references and mode rules. Use [example assets](../assets/) for complete inputs.

## Document

Required: `version: 1`, `mode: "review" | "plan"`, `title`, `context`, and `changes`. New explanations also require a concise `summary`; legacy inputs may omit it with a warning. Optional: `impact`, `manualChanges`, `risks`. Empty optional sections are omitted. Empty changes are valid when the comparison has no changes.

`context` requires `baseline`. Add `problem`, `scope`, `constraints`, `assumptions`, or `visual` only when useful. The baseline may identify revisions, specification versions, existing behavior, or an explicitly hypothetical starting point.

Each change requires `id`, `title`, `status`, and `description`. IDs start with a letter and contain letters, digits, underscores, or hyphens. Change status is `new`, `changed`, or `removed`. Optional: `why`, `code`, `visual`, `evidence`. Omit unknown motivation and repeated explanation.

### Scope and evidence

For actual reviews, record `context.comparison`: `base`, `head`, `inspectedAt`, and `included`/`excluded` scope. Only base/head are structurally required. Use resolved commits for pinned comparisons. Identify working-tree staged/unstaged/untracked inclusion and its snapshot date explicitly. Plans may omit revision metadata for hypothetical baselines.

Structured evidence requires `label`; optional fields are `file`, `line`, `revision`, `url`, and `detail`. Lines are positive source-line numbers. Use detail for relevant verification coverage or limitations. Legacy string evidence remains accepted.

Explicit URLs must be verified, absolute, and use http, https, file, codex, or vscode. Prefer pinned permalinks for historical sources. Absolute local paths become links labeled Local working copy; they open current content, not necessarily the inspected revision or line. Relative paths remain text unless given an explicit URL. Omit unavailable links.

### Code excerpts

`code` requires `before` and `after` strings, not both empty. Optional: `summary`, `file`, `symbol`, `language`, `beforeLine`, `afterLine`, `beforeRevision`, `afterRevision`.

Use only inspected lines for reviews; identify fictional snippets in plans. Keep excerpts focused and state material gaps. Positive before/after line numbers identify actual source lines; without them, numbering is labeled Excerpt lines. Excerpts are not a complete patch or patch-size metric. Do not add diff signs or HTML; highlighting comes from the renderer.

### Impacts, actions, and risks

Add an impact only when it contributes a consequence. Each requires `change` (change ID), `description`, and `basis`: `observed` for direct inspection/verification, `inferred` for reasoning from evidence, or `expected` for prediction. Plans cannot claim observed implementation outcomes. Changes need not have impacts.

Manual actions require `change` and `action`; optional `prerequisite` and `verification`. Array order is action order. Reporting an action does not authorize performing it.

Risks require `change`, `title`, `severity` (`important` or `critical`), `condition`, and `consequence`; optional `mitigation`. Include only material, supported risks.

## Templates

Every visual requires `template`; `caption` is optional and should add information rather than repeat its heading. The renderer determines positions. Use the smallest visual that explains a useful relationship.

| Template | Use for | Required data |
| --- | --- | --- |
| `before-after` | Old/new behavior or structure | `before`, `after` element arrays |
| `flow` | Steps, decisions, branches | `nodes`, `edges` |
| `dependency-map` | Changed component and consumers | `nodes`, `edges` |
| `comparison` | Rules, configuration, interfaces | `rows` |
| `state-transitions` | Events between states | `nodes`, `edges` |
| `communication` | Participants, messages, ownership | `nodes`, `edges` |

### Elements and graphs

Elements require `label` and `status`; graph nodes additionally require a local `id`. Optional fields include `kind`, `brand`, `meta`, `detail`, and `animate`; nodes also accept `group` and `issue`. Element status is `new`, `changed`, `removed`, or `unchanged`.

Choose kinds from the schema to describe the actual role. `brand` uses an ID from [the catalog](../assets/brands/catalog.json); use it only when supported. See [visual guidance](rendering.md) for evidence and license rules.

Edges require `from`, `to`, `label`, and `status`. Optional: `shortLabel` (at most 32 characters), `transport`, `animate`, `issue`. Endpoints reference local nodes. Label arrows with concise actions or conditions; use shortLabel when the full label is supporting detail. Decision nodes ask a question and outgoing labels answer it. Status colors describe changes; conditions and outcomes remain neutral and explicit.

Transport: `flow`, `request`, `message`, `read`, `write`, `config`, `trigger`, `deploy`, or `spawn`. Use flow for execution paths without implying network delivery. Cycles and self-loops are valid.

Optional `groups` express actual or proposed ownership. Each requires `id`, `label`, and `kind` (`server`, `process`, `ci-worker`, or `worker`); optional `detail`. Nodes refer to groups by ID. Each group needs a member; nested groups are unsupported.

`issue` describes a condition and consequence without changing baseline elements from `unchanged`. Do not use change status to mean broken.

`animate: true` is accepted only for new/changed elements or edges. Flow/request/read/write move dots, message moves an envelope, and deploy moves a package. Other transports and nodes receive brief emphasis. Motion illustrates direction, not measured timing or throughput; use sequence for supported order.

### Consequence scenarios

Use a supported scenario when a graph explains failure; otherwise choose a static failure visual. Every scenario field is required:

```json
"scenario": {
  "template": "interrupted-work",
  "from": "request",
  "at": "export",
  "to": "db",
  "condition": "The API process stops during this export.",
  "cause": "Request and export share a process lifetime without a durable handoff.",
  "consequence": "This unfinished attempt stores no completed result."
}
```

From/at/to are distinct existing nodes. The graph needs from→at and either from→to or at→to. Do not invent links to satisfy this contract.

| Scenario | Evidence-supported condition |
| --- | --- |
| `interrupted-work` | Shared process stops before work finishes |
| `message-loss` | This delivery does not reach the receiver |
| `bottleneck` | Arrivals outpace processing and backlog grows |
| `saturation` | Finite capacity is full and new work waits |

Interrupted-work requires from/at in the same explicit process group. Message-loss requires incoming/downstream message transports. Scenarios cannot share a graph with sequence or independently animated elements. Label hypothetical conditions and illustrative capacities; scope missing results or delivery to the illustrated attempt. Verify the outcome without motion as well as during playback.

### Ordered behavior

`sequence` contains two to five steps. Each requires `label` and exactly one target: a 1-based `edge` number or a waiting `node` ID. Edge targets must use flow/request/message/read/write/deploy and cannot independently animate; omitted transport means request. Waiting nodes need an issue explaining the wait and consequence.

```json
"sequence": [
  {"edge": 1, "label": "Request enters API"},
  {"node": "request", "label": "Request waits for export"},
  {"edge": 3, "label": "Store result, then reply"}
]
```

Order must be inspected or explicitly illustrative in a plan. A successful sequence does not explain a claimed failure. Baseline nodes/edges remain unchanged; sequence describes behavior, not change status.

### Comparisons

Rows require `label`, `before`, `after`, and `status`; optional `reason`. Use unchanged rows only for useful context. For absent values, use an explanation such as "Not present" rather than an empty string.

## Validation and preview

```text
python <skill-folder>/scripts/report.py validate explanation.json
python <skill-folder>/scripts/report.py render explanation.json --output explanation.html
node <skill-folder>/scripts/preview_check.mjs explanation.html previews <browser-executable>
```

Fix errors at reported JSON paths and relevant warnings. `validate --json` supplies machine-readable diagnostics. Exit codes: 0 success, 1 invalid input, 2 command/read/write error. Existing HTML requires `--force`; preserve unrelated artifacts.

Python 3.12 needs no third-party packages. The optional preview helper needs Node 22+ and local Chromium; it checks layout, labels/routes, contrast, source/navigation links, playback, reduced motion, and print, saving screenshots. Apply the [visual checks](rendering.md). Neither validation nor preview verifies source claims.
