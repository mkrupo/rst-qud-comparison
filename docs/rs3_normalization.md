# RS3 structural normalization

RS3 can represent one nucleus with several satellites as a single, flat schema. The repository's parenthetical RST representation is binary: every ordinary rhetorical relation connects one nucleus and one satellite. RST-Tace likewise expects at most one mononuclear relation at each structural node. Multi-satellite RS3 therefore needs a deterministic binary structure before either workflow can process it.

`normalize_rs3.py` validates RS3 XML and writes this derived structure without modifying the source files:

```bash
python3 normalize_rs3.py path/to/rs3-directory output/normalized-rs3
```

Strict structural and relation-schema validation is the default. `--compatibility` is only for legacy input whose structure is convertible but whose relation use conflicts with its RS3 declarations; it does not relax structural checks or rewrite relation labels.

## Normalization rule

Starting with the annotated nucleus subtree:

1. Attach preceding (left) satellites from nearest to farthest.
2. Attach succeeding (right) satellites from nearest to farthest.
3. After every attachment, treat the resulting span as the nucleus for the next attachment.

For a flat `S-N-S-S` schema, the transformation is:

```text
Human RS3 order:       S-left   N   S-right-1   S-right-2
                                  │
Left satellite first:       (S-left  N)
                                  │
Right, near to far:         ((S-left  N)  S-right-1)
                                  │
Normalized binary tree:    (((S-left  N)  S-right-1)  S-right-2)
```

This is an inside-to-outside rule, not an "always left-branching" rule. For a two-sided schema, the left side is processed before the right side. The same recursive rule applies whether the nucleus is a single EDU, a span subtree, or a multinuclear subtree. Parenthetical conversion separately left-binarizes n-ary multinuclear cores in textual order.

## Derived structure and evaluation

The original annotation identifies the nucleus and its satellites but does not specify every binary intermediate constituent. Normalization introduces only the span groups needed to make those attachments binary. It preserves EDU order and text, relation names and declarations, and existing node IDs; new IDs are assigned only to generated span groups.

Normalized RS3 is a derived evaluation representation, not a replacement for the human annotation. Original RS3 files should remain unchanged.

```text
human RS3
   │
   ▼
normalize_rs3.py
   │
   ▼
normalized RS3
   ├──► RST-Tace comparison
   └──► RS3 → parenthetical RST → QUD-like structural output
```

Because evaluation operates on the normalized representation, generated intermediate spans can participate in constituent-based scores. Results should therefore be understood as comparison after this documented canonical normalization.
