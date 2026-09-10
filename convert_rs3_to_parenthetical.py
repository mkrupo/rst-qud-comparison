"""Convert the RS3 structures in this repository to parenthetical RST."""

import argparse
from pathlib import Path

from normalize_rs3 import (
    Document,
    RS3SchemaError,
    RS3StructureError,
    descendant_positions,
    multinuc_children,
    normalize_rs3,
    parse_rs3,
    schema_issues,
    validate_schema,
    validate_structure,
)


def normalize_edu_text(text: str) -> str:
    text = " ".join(text.split())
    return text.replace("(", r"\(").replace(")", r"\)")


def _render(document: Document, root_id: str) -> str:
    positions = descendant_positions(document)

    def attach(nucleus_positions, nucleus, satellite_id):
        satellite = render(satellite_id)
        relation = document.nodes[satellite_id].relation
        satellite_positions = positions[satellite_id]
        if max(nucleus_positions) < min(satellite_positions):
            return f"( {relation} l {nucleus} {satellite} )"
        return f"( {relation} r {satellite} {nucleus} )"

    def render(node_id):
        node = document.nodes[node_id]
        child_ids = document.children[node_id]
        if node.kind == "multinuc":
            core, satellites = multinuc_children(document, node_id)
            ordered = sorted(core, key=lambda child_id: min(positions[child_id]))
            relation = document.nodes[ordered[0]].relation
            result = render(ordered[0])
            for child_id in ordered[1:]:
                result = f"( {relation} c {result} {render(child_id)} )"
            if satellites:
                core_positions = frozenset().union(
                    *(positions[child_id] for child_id in core)
                )
                result = attach(core_positions, result, satellites[0])
            return result

        if node.kind == "segment":
            nucleus_positions = frozenset({document.segment_positions[node_id]})
            result = f"( leaf t {normalize_edu_text(node.text)} )"
            satellites = child_ids
        else:
            nucleus_id = next(
                child_id
                for child_id in child_ids
                if document.nodes[child_id].relation == "span"
            )
            nucleus_positions = positions[nucleus_id]
            result = render(nucleus_id)
            satellites = [child_id for child_id in child_ids if child_id != nucleus_id]

        if satellites:
            result = attach(nucleus_positions, result, satellites[0])
        return result

    return render(root_id) + " "


def convert_rs3(source, *, strict=True) -> str:
    document = normalize_rs3(source, strict=strict)
    root_id = validate_structure(document, normalized=True)
    return _render(document, root_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a directory of RS3 XML files")
    parser.add_argument("in_path", type=Path)
    parser.add_argument("out_path", type=Path)
    parser.add_argument(
        "--compatibility",
        action="store_true",
        help="allow relation-type mismatches while retaining structural validation",
    )
    args = parser.parse_args()
    if not args.in_path.is_dir():
        parser.error("in_path must be an existing directory")
    args.out_path.mkdir(parents=True, exist_ok=True)
    inputs = sorted(args.in_path.glob("*.rs3"))
    if not inputs:
        parser.error("input directory contains no .rs3 files")
    for input_path in inputs:
        output_path = args.out_path / f"{input_path.stem}.tree"
        output_path.write_text(
            convert_rs3(input_path, strict=not args.compatibility), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
