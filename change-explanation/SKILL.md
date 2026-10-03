---
name: change-explanation
description: "Use only when the user explicitly invokes $change-explanation or requests the Change Explanation skill."
---

# Change Explanation

Create a self-contained HTML explanation of actual changes or one proposed solution. Lead with a short summary; include only details that help the reader understand the change. A defect audit is a separate request.

## Establish scope

Use `review` for actual changes and `plan` for a proposal. Honor supplied revisions, files, and exclusions. Ask one focused question only when missing information materially changes the comparison or proposal.

For “this branch,” compare from the merge base of the PR or stated target. Infer a default target only from inspected configuration; a feature branch's tracking upstream is not its target. For “current changes,” compare HEAD with the working tree and record staged, unstaged, and untracked inclusion. Include untracked files only when requested or clearly in scope.

Record resolved revisions, inspection date, and included/excluded scope in `context.comparison`. Working trees are snapshots, not identified by HEAD alone. Label hypotheses and fictional snippets in plans.

## Explain the change

Read [format.md](references/format.md). State each fact once. Add motivation, problem context, impacts, manual actions, and risks only when they contribute useful information. Unknown motivation may be omitted.

Use inspected before/after excerpts only when helpful, with source lines and revisions when known. Attach structured evidence; distinguish observed, inferred, and expected effects. State relevant verification limits beside the claim. Prefer verified pinned source links; local links open the current working copy.

Use diagrams only for relationships that prose or code cannot explain clearly. Label arrows directly; decision branches answer the node's question. Status colors describe changes, not success/failure. Keep conclusions and issue notes visible. Follow [rendering.md](references/rendering.md) for visual checks.

## Generate and deliver

Use Python 3.12; no third-party packages are required:

```text
python <skill-folder>/scripts/report.py validate <explanation.json>
python <skill-folder>/scripts/report.py render <explanation.json> --output <explanation.html>
```

Use the requested destination or `reports/`; keep JSON alongside HTML. Fix errors and relevant warnings. Use `--force` only for your own output. Validation does not establish factual accuracy.

Check the report in available browser tooling; disclose when visual verification was unavailable. Deliver HTML and JSON links, identify review or proposal, and state any material limitation or action. Open the HTML when supported. Generation does not authorize implementation or manual actions.
