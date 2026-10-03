# ouat

Desktop HTML explanations of actual changes and proposed solutions.

A short summary states the main change and consequence. Focused code excerpts, directly labeled diagrams, and source references explain the details. Important risks are linked from the opening summary.

![A proposed change with directly labeled arrows](docs/preview.png)

The project includes the explicitly invoked `change-explanation` agent skill and a Python renderer. Reports contain their CSS, diagrams, and selected icons, so they open locally without a server or external assets.

## Use the skill

Copy the complete `change-explanation/` folder into your agent's skills directory. Invoke it explicitly:

```text
Use $change-explanation to explain the changes between main and this branch.
Use $change-explanation to propose moving scheduled exports into a worker.
```

Ordinary explanation requests do not activate the skill. It explains changes; a defect audit is a separate request. `review` mode explains actual changes against an inspected baseline; `plan` mode explains one proposed solution with assumptions and expected effects.

The agent records the comparison and scope, writes JSON, validates it, renders HTML, and delivers both files with a short chat conclusion. Source links include visible file lines and revisions. Working tree comparisons identify staged, unstaged, and untracked inclusion.

## Try the examples

Use Python 3.12. The renderer and tests require only the standard library.

```sh
python change-explanation/scripts/report.py validate change-explanation/assets/example-system.json
python change-explanation/scripts/report.py render change-explanation/assets/example-system.json --output reports/my-explanation.html
```

Open the generated HTML in a browser. Add `--force` to replace your own generated output.

- [Actual documentation change](reports/example-review.html): a brief explanation of a pinned historical README change, with a source permalink and no diagram. [JSON](change-explanation/assets/example-review.json).
- [Bounded retries](reports/example-plan.html): a proposal with directly labeled decisions and retry branches. [JSON](change-explanation/assets/example-plan.json).
- [Scheduled exports](reports/example-system.html): a proposal moving export execution into independent consumers. [JSON](change-explanation/assets/example-system.json).

The two proposals are hypothetical. The actual-change example is scoped to documentation; it does not verify runtime behavior.

## Read the reports

A labeled sticky section bar navigates the explanation. Essential conclusions, uncertainty, and risk conditions remain visible. Supporting connection descriptions expand through native Connection details and are included in print.

Diagrams put actions and branch conditions beside the arrows. Envelopes represent messages; packages represent deployment artifacts. Motion illustrates direction or a stated scenario, not measured timing, throughput, or guarantees. Failure scenarios show condition, mechanism, and consequence and retain a static outcome under reduced motion and in print.

System / Play / Pause manages report motion. System follows the browser's reduced-motion preference; Play explicitly enables motion for this report; Pause freezes playback. These controls do not occupy sticky navigation. No JavaScript is required for the reports. Readers can use a current Chromium browser for the checked CSS motion behavior.

See the [format reference](change-explanation/references/format.md), [rendering guidance](change-explanation/references/rendering.md), and [JSON schema](change-explanation/assets/report.schema.json). Legacy string evidence and reports without summaries remain accepted; new authoring requires a concise summary and structured references where available.

## Icons

```sh
python change-explanation/scripts/report.py icons --output reports/icon-library.html
```

Selected bundled logos retain their artwork and source credits. Individual licenses and trademark terms apply; see [brand notices](change-explanation/assets/brands/NOTICE.txt).

## Verification

```sh
python -m unittest discover -s change-explanation/scripts -p "test_*.py" -v
node change-explanation/scripts/preview_check.mjs reports/my-explanation.html reports/previews "/path/to/chrome"
```

The suite covers validation, source links and numbering, escaping, graph routing, label placement, embedded assets, and CLI output handling. CI runs on Linux and Windows. The optional browser helper uses Node 22+ and local Chrome or Edge without npm packages. It checks layout, labels, navigation, contrast, playback, reduced motion, and static printing and saves screenshots. Structural and visual checks do not establish factual accuracy.
