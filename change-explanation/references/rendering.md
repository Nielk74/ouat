# Visual authoring and checks

The renderer owns theme, icons, layout, and playback. Supply plain-text relationships, not HTML, CSS, Mermaid, scripts, or coordinates. Omit visuals that add no information.

- Put actions and branch conditions beside arrows. Supporting descriptions may use Connection details; conclusions, risk conditions, and issue notes stay visible.
- Status colors mean new, changed, removed, or unchanged. Use words for success, failure, and branch conditions.
- Choose kinds, brands, ownership groups, and transports from inspected facts or explicit proposals. Icons and async calls do not establish durability, isolation, protocols, overload, or shared process lifetime.
- Explain a claimed failure as condition → mechanism → consequence. Existing problematic elements remain `unchanged` with an `issue`. Use the [scenario contract](format.md#consequence-scenarios) or a static failure diagram; do not distort topology to fit a pattern.
- Animate only meaningful direction, order, or a supported scenario. Motion does not establish measured timing or throughput. Keep scenarios, sequences, and independent loops in separate visuals.

Use brands from [the catalog](../assets/brands/catalog.json) only when supported. Preserve original artwork and bundled credits; individual licenses, trademark terms, and archived-mark notices apply. Do not fetch remote icons or recolor logos.

When browser tooling is available, check desktop readability, labels and routes, source links, navigation, contrast, reduced motion, and static print. For scenarios, inspect the start, failure event, and held outcome. System/Play/Pause must respect the viewer's choice; essential explanations must survive without motion.

Use the [browser helper](format.md#validation-and-preview) for these checks. If labels or routes are unreadable, shorten labels or split the diagram without removing a real relationship. If preview is unavailable, disclose that visual verification was not performed.
