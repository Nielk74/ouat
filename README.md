# ouat

Visual reports for code reviews and technical plans.

A diff shows which lines changed. It takes more work to explain how those changes affect the system. ouat puts that explanation in one HTML file: the starting point, focused before/after code, diagrams of the affected components, and the consequences.

![A proposed change with a code excerpt and a message-flow diagram](docs/preview.png)

The project includes an agent skill (`review-report`) and a Python renderer. The agent inspects the source or develops a proposal, writes structured JSON, then uses the renderer to produce the report. You can also write the JSON yourself. The renderer checks its structure and references; the author is responsible for the explanation and evidence.

Reports open locally in a browser. CSS, diagrams, and selected icons are embedded, so there is no server to run or external asset to load.

## Try it

Use Python 3.12. The renderer and tests use only the standard library.

```sh
python review-report/scripts/report.py validate review-report/assets/example-system.json
python review-report/scripts/report.py render review-report/assets/example-system.json --output reports/my-report.html
```

Open `reports/my-report.html` in your browser. To replace a report you've already generated, add `--force`.

Two examples are included, with rendered HTML ready to open after cloning:

- [Scheduled exports](reports/example-system.html): move work out of an API request into a queue and independent workers. [Source JSON](review-report/assets/example-system.json).
- [Bounded retries](reports/example-plan.html): define retry eligibility, limits, and state transitions. [Source JSON](review-report/assets/example-plan.json).

Both are illustrative proposals. Their code and infrastructure are hypothetical.

## Use the skill

Copy the `review-report/` folder into your agent's skills directory. Keep the scripts, assets, references, and `SKILL.md` together.

Example requests:

```text
Use $review-report to explain the changes between main and this branch.
Use $review-report to propose moving scheduled exports into a worker.
```

The skill has two modes:

- **Review** explains actual changes against a stated baseline and separates observed effects from predictions.
- **Plan** explains one proposed solution, with assumptions and expected effects clearly labeled.

Reports follow context, changes, manual actions when needed, impact, and important risks. Visuals cover before/after comparisons, flows, dependencies, state transitions, and communication between components. Diagrams are laid out by the renderer; JSON contains relationships, not coordinates.

For your own report data, see the [format reference](review-report/references/format.md) and [JSON schema](review-report/assets/report.schema.json).

## Icons

Generate a local gallery of the component icons and bundled product logos:

```sh
python review-report/scripts/report.py icons --output reports/icon-library.html
```

Product logos retain their source metadata and notices in [assets/brands](review-report/assets/brands/NOTICE.txt). Individual licenses and trademark terms apply; selected marks are credited in generated reports.

## Tests

```sh
python -m unittest discover -s review-report/scripts -p "test_*.py" -v
```

The suite covers validation, escaping, diagram routing, embedded assets, and CLI output handling. CI runs it on Linux and Windows.

An optional browser check uses Node 22+ and a local Chrome or Edge executable, without npm packages:

```sh
node review-report/scripts/preview_check.mjs reports/my-report.html reports/previews "/path/to/chrome"
```

It checks layout at desktop, tablet, and phone widths, diagram routing, contrast, packet animation, and reduced motion, and saves screenshots.
