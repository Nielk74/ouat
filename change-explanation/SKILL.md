---
name: change-explanation
description: "Use only when the user explicitly invokes $change-explanation or requests the Change Explanation skill."
---

# Change Explanation

Create a self-contained HTML explanation of actual changes or one proposed solution. Optimize for desktop readers: a small summary, focused evidence, and diagrams that explain themselves. This is an explanation workflow; a defect audit is a separate request.

## Establish scope

Use **review** for actual changes and **plan** for a proposed solution. Infer the mode from the invocation and context. Ask one focused question only when missing information changes the comparison or proposed behavior materially.

For actual changes, honor the supplied PR, revisions, files, and exclusions. For “this branch,” use the PR or stated target and compare from its merge base; record resolved commits. Infer a repository default target only from inspected configuration. A tracking upstream on the same feature branch is not a target baseline; resolve the target when unclear. For “current changes,” compare HEAD with the working tree and record staged, unstaged, and untracked inclusion explicitly. Include untracked files only when requested or clearly part of the described change.

Record `context.comparison` with base, head, inspection date, and included/excluded scope. Identify a working tree as such: a HEAD hash alone does not identify uncommitted content. Treat the report as a snapshot. In plan mode, label hypotheses and fictional snippets explicitly.

## Explain once, in the right place

Start with a required two-sentence `summary`: the main change and its consequence or material uncertainty. Important risk titles appear beside it automatically.

Then use **Context → Changes → Manual actions (when needed) → Impact → Important risks**. Keep context brief. Group changes by behavior. Each explanation, rationale, excerpt, caption, and impact contributes a distinct fact; omit redundant detail and unnecessary visuals.

Use short before/after code only where it explains behavior, usually three to eight lines per side. Actual excerpts use inspected lines and `beforeLine`/`afterLine` plus revisions when known; gaps and omissions are stated. Unknown motivation remains unknown. Documentation changes can be a short prose explanation without code or diagrams.

Attach structured `evidence` with a label, file, actual line, revision, and a verified URL when available. Prefer pinned source links for historical revisions. Local file links open the current working copy and cannot guarantee the inspected revision or line; the renderer labels them accordingly. Relative paths remain text without an explicit URL. Describe verification coverage and limitations beside the claim. Distinguish observed, inferred, and expected effects; plans have no observed implementation outcomes.

## Draw readable relationships

Read [the format reference](references/format.md) for the JSON contract and template choices. Use the smallest useful visual. Put concise actions or conditions in edge `label`; use `shortLabel` when longer detail is needed. Decision nodes ask a question, and their outgoing branches answer it. Reserve status colors for New/Changed/Removed; branch labels remain neutral and name their conditions explicitly. Use `transport: "flow"` for execution paths; `animate: true` adds persistent directional dots. Every graph must be understandable without opening Connection details. Important issue notes remain visible.

Show condition → mechanism → consequence for a problem-driven visual, using an evidence-supported scenario or explicit static failure state. Existing broken elements remain `unchanged` with an `issue`. Never infer durability, isolation, overload, process lifetime, or protocols from an icon or async call. Rendering and playback guidance lives in [rendering.md](references/rendering.md).

## Generate, verify, deliver

Resolve scripts relative to this skill folder; Python 3.12 uses no third-party packages.

```text
python <skill-folder>/scripts/report.py validate <explanation.json>
python <skill-folder>/scripts/report.py render <explanation.json> --output <explanation.html>
```

Use the requested destination or `reports/` with a descriptive filename. Keep JSON alongside HTML. Use `--force` only for your own generated output. Fix validation errors and relevant warnings; validation does not verify factual accuracy.

For complex diagrams, report brief progress while checking evidence and layout. When browser tooling is available, check desktop layout, visible arrow meanings, label collisions, source links, navigation anchors, reduced motion, and static print. Use the bundled browser helper as described in the format reference. If preview is unavailable, deliver the validated artifact and state that visual verification was not performed.

Deliver a short chat conclusion with the main limitation or user action, links to HTML and JSON, and whether it explains actual changes or a proposal. Open the HTML in the available app/browser when supported. Report generation alone does not authorize implementing proposals or performing manual actions.

Examples: [actual documentation change](assets/example-review.json), [retry proposal](assets/example-plan.json), [worker proposal](assets/example-system.json).
