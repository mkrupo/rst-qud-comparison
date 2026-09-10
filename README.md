# rst-qud-comparison

# Data

The annotated data consists of 14 blog posts and chunks of 14 podcast transcripts. Some transcripts contain more than one annotated chunk, indicated by `{episode_name}_p{chunk_id}`; for example, `DELL003_Transkript_p1` and `DELL003_Transkript_p2`.

# Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

# Conversion

The repository's existing RST-to-QUD pipeline expects its input in the parenthetical RST `.tree` representation. For supported RS3 XML `.rs3` annotations, the workflow is:

```text
.rs3 -> normalized structure -> .tree -> QUD-like structural output
```

## RS3 normalization

Multi-satellite RS3 schemas require a deterministic binary normalization for parenthetical conversion and tools such as RST-Tace. The parenthetical converter applies this normalization in memory. To write separate, derived normalized RS3 files, run:

```bash
python3 normalize_rs3.py path/to/rs3-directory output/normalized-rs3
```

Strict structural and relation-schema validation is the default. The `--compatibility` option is only for legacy data whose structure is convertible but whose relation use conflicts with its RS3 declarations. See [RS3 structural normalization](docs/rs3_normalization.md) for the rule and its evaluation implications.

## RS3 XML to parenthetical RST

The converter reads `.rs3` files from an existing input directory and writes same-named `.tree` files to the requested output directory, creating it if necessary:

```bash
python3 convert_rs3_to_parenthetical.py path/to/rs3-directory output/parenthetical
```

## Parenthetical RST to QUD-like structure

Convert generated parenthetical trees from an existing input directory with:

```bash
python3 convert_rst2qud.py output/parenthetical output/qud
```

The output directory is created automatically, including its `nested/` and `unnested/` subdirectories.

The original committed parenthetical annotations can be converted directly:

```bash
python3 convert_rst2qud.py rst/parenthetical qud-output
```

# Tests

```bash
python -m unittest -v
```
