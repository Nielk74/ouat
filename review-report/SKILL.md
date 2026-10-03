---
name: review-report
description: "Generate visual HTML reports explaining actual changes or one proposed solution for technical reviewers. Use for requested change reviews, explanations, or solution plans across code, architecture, UI, infrastructure, data, and documentation."
---

# Review Report

Explain what changes, why, and the consequences using the supplied JSON format and reusable visual templates. Produce a self-contained, fully dark HTML document centered on small summarized code changes and the components they affect.

## Choose the mode from the request

- **Review:** explain actual changes against a named baseline. Inspect relevant changes and surrounding code or specifications. State the scope and evidence supporting the explanation. Do not implement fixes merely because the report identifies a problem.
- **Plan:** when the user asks for a potential solution, develop one recommended solution. Existing material can inform context; an existing diff is not required or automatically reviewed. Label assumptions, proposed changes, and expected impacts. Creating the report does not authorize applying the proposal.

Choose based on user intent, not whether a diff exists. If the comparison baseline matters and is ambiguous, resolve it from context or ask. Generate reports for review, explanation, or planning requests; this skill does not require a report after every implementation task.

## Organize the explanation

Keep this order: **Context → Changes → Manual changes required (optional) → Impact → Important risks (when present)**. Plan mode uses **Proposed changes** and **Expected impact**. The renderer maintains this order and omits empty optional sections.

- Context: establish the comparison baseline, then show the current behavior and its failure mechanism. For a problem-driven review or proposal, include a baseline diagram in `context.visual`: trigger/input → where work runs → the problematic step or relationship → the consequence. Use plain, specific explanations; a topology without the causal problem is not enough. Record evidence, unknowns, and assumptions here. An illustrative baseline must remain explicitly hypothetical.
- Changes: group by meaningful behavior or design decision rather than filename. Give each change a stable ID, status, short explanation, and reason. Where code is involved, lead with a small before/after excerpt in `code`, then show the affected components. Include existing elements only when they explain a changed relationship. Highlight changed connections as well as changed components.
- Manual changes: include concrete user or operator actions needed outside the implementation, with prerequisites and verification when known. Describe actions; do not perform them solely because they appear in a report.
- Impact: link each effect to a change ID and distinguish observed, inferred, and expected effects. Verification results belong in the relevant change's evidence; describe their actual coverage.
- Risks: include important, specific conditions and consequences supported by the context. Include mitigation when available. Do not manufacture risks to fill the section or claim that an omitted section proves the absence of risk.

In Plan mode, use `expected` or `inferred` impact basis, and do not invent implementation evidence, test results, paths, or benchmarks. Review mode can also contain expected or inferred effects. For an empty review scope, use empty changes/impact arrays and explain the baseline and absence of changes in Context.

## Select templates and write data

Read [references/format.md](references/format.md) before authoring JSON. It describes the fields and template selection rules. Use [assets/example-system.json](assets/example-system.json) as a complete illustrative example of code changes and system communication, not as evidence about the user's project. [assets/example-plan.json](assets/example-plan.json) also demonstrates before/after, comparison, and state-transition templates.

Select only the visual templates that explain the relationships: `before-after`, `flow`, `dependency-map`, `comparison`, `state-transitions`, or `communication`. A visual is optional for simple changes. Keep graphs focused; split complex relationships into separate changes or diagrams. State labels are `new`, `changed`, `removed`, and `unchanged`. Both modes share the same JSON shape; the renderer labels planned elements as proposed.

Choose each node's `kind` to give it the appropriate component illustration: repository, server, config, cron, CI/CD agent, worker, process, thread, queue, message, database, and the other supported types. Optionally select `brand` from [assets/brands/catalog.json](assets/brands/catalog.json), such as `teamcity`, `jenkins`, `github`, `gitlab`, `aws`, `azure`, `postgresql`, or `rabbitmq`. Brand identifies the product; kind still identifies its role and status still indicates the change. Use a brand only when supported by inspected evidence or explicitly proposed; do not infer a project's toolchain from the icon library. The renderer embeds only selected local SVGs, preserves their artwork colors/proportions, and includes source credits. Keep individual licenses, source links, guidelines, and archived-mark notes; the library is not blanket permission to use every trademark. Do not recolor logos to match change status or fetch icons from a CDN. Use `groups` only for real or explicitly proposed ownership boundaries. Use `transport` to distinguish message delivery, requests, configuration, deployment, and local execution. Concurrency does not prove multiple OS threads; a worker role does not prove a separate process or host. Do not invent isolation, durability, protocols, or topology to make the diagram look richer.

In the baseline diagram, keep existing elements marked `unchanged`. Add `issue` to the problematic node or connection, explaining the condition and consequence. This uses a separate problem highlight; do not misuse `changed` or `removed` to mean broken. Show the proposed remedy in Changes, not in the baseline. A routine change without a meaningful failure mechanism need not invent one.

Keep Context compact and each code excerpt focused on the lines that explain the behavior, usually three to eight lines per side. Code is optional for documentation or other changes without a useful excerpt. Label illustrative paths and snippets in Plan mode; in Review mode, use inspected lines and clarify any omissions. Do not present excerpt line counts as the size of the complete patch.

Write JSON content as plain text; the renderer escapes it. Do not add bespoke HTML, CSS, scripts, Mermaid source, or node coordinates. Use `code` for summarized code changes and `evidence` for source references and verification results. The shared vector library and renderer own the graphical style.

Use the shared IDE-style theme: neutral charcoal surfaces, distinct editor/tool-window panels, orange code keywords, saturated green additions, and amber modifications. Existing elements stay gray; use salmon for risks and deleted code. Avoid dominant blue surfaces. Keep body text at 16px and code at 13–14px; small metadata should remain readable. The consistent vector icons and section-shortcut toolbar come from the renderer. Toolbar icons link only to existing sections; do not add decorative controls that imply unavailable behavior. Local JetBrains Mono is preferred for code, with system monospace fallbacks; no remote font downloads are needed.

All information stays visible. Motion is optional and limited to a few highlighted nodes or connections. On a message edge, `transport: "message"` plus `animate: true` moves a small package along the routed arrow from source to destination. Use it to explain a meaningful payload handoff, not for a dependency or state transition that passes no message. Packages loop automatically so they are still visible after the user reads Context; each relevant diagram includes a native Pause packets checkbox. This illustrates direction, not measured timing, ordering, or throughput. Other animated edges retain brief directional line emphasis. Reduced-motion and print views keep a static package. There is no page introduction animation, content reveal, tooltip-only detail, or collapsible section.

Brand icon tiles use neutral light/dark surfaces chosen for contrast, not the element's semantic status tint. Keep original logo colors and proportions. Check monochrome brand marks against their actual tile at a minimum 3:1 design target, including new/changed/removed/unchanged and problem-highlight states; inspect multicolor artwork visually rather than treating its metadata hex as the entire logo. Generic icons continue to use semantic colors. This logo check supplements, not replaces, text contrast checks.

## Validate and render

Resolve the scripts relative to this skill folder; they require Python 3 and no third-party packages.

```text
python <skill-folder>/scripts/report.py validate <report.json>
python <skill-folder>/scripts/report.py render <report.json> --output <report.html>
python <skill-folder>/scripts/report.py icons --output <icon-library.html>
```

Fix validation errors at their reported JSON paths and rerun validation. Address warnings when relevant. Rendering also validates and exits with an error instead of generating a structurally invalid report. `validate --json` returns machine-readable diagnostics. The schema is [assets/report.schema.json](assets/report.schema.json), usable by JSON-aware editors.

Keep the source JSON alongside the generated HTML so the report can be corrected without rewriting the layout. Use a user-specified destination, otherwise a `reports/` directory in the current workspace with a descriptive filename. Existing output requires `render --force`; use it for your own generated report when iterating, and preserve unrelated artifacts.

Check that the generated explanation matches the inspected evidence or stated assumptions; structural validation cannot establish factual accuracy. When browser tooling is available, inspect the report at desktop and narrow widths, especially arrow direction, clear terminal gaps, return-path separation, and boundary-heading clearance. Straightforward neighbors should connect directly; returns use separate lanes and external sinks should not weave through execution paths. Verify packet motion after a reading delay without hover/focus, its pause control, and the static reduced-motion view. The renderer owns routing; if diagnostics cannot find a readable route, simplify or split the diagram instead of inventing coordinates or omitting a real relationship. Deliver a link to the HTML and identify whether it describes actual changes or a proposal.
