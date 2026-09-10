# RS3 structural normalization

RS3 permits a nucleus to have several satellites, while the repository's parenthetical RST representation and RST-Tace require binary nucleus-satellite attachments. `normalize_rs3.py` supplies one deterministic structure for both evaluation paths. The parenthetical converter applies it in memory; the normalization command can instead write derived RS3 files:

```bash
python3 normalize_rs3.py path/to/rs3-directory output/normalized-rs3
```

Strict structural and relation-schema validation is the default. `--compatibility` only permits legacy relation-type inconsistencies; it does not relax structural validation or rewrite relation labels.

## Canonical rule

Starting with the annotated nucleus subtree:

1. Attach preceding (left) satellites from nearest to farthest.
2. Attach succeeding (right) satellites from nearest to farthest.
3. After each attachment, use the resulting span as the nucleus of the next attachment.

Thus a two-sided schema always processes the left side before the right side. This is an inside-to-outside convention, not a general left-branching rule. It applies recursively whether the nucleus is an EDU, a span subtree, or a multinuclear subtree. Parenthetical output continues to left-binarize n-ary multinuclear cores in textual order.

The human annotation contains the nucleus and its satellites but does not specify all binary intermediate constituents. Normalization creates span groups only for those required intermediate constituents and otherwise retains node IDs, EDU order and text, relation labels, and relation declarations. Original gold RS3 files are never overwritten; normalized RS3 is a derived evaluation representation.

At rst-converter-service commit `e3b5dedff7fd0f9e05508ba6a23119d2b77686d2`, its normalization produces the same constituent yields for all eight affected ArgMicrotext Original files currently used here. That service uses a cross-side subtree-height heuristic, however, so it can choose a different order for hypothetical two-sided schemas. This project deliberately uses the simpler left-before-right convention.

Both RST-Tace comparison and Shahmohammadi-style unlabelled Parseval comparison are therefore performed after canonical normalization. Artificial intermediate spans can participate in the resulting metrics; they must not be interpreted as additional human annotations.
