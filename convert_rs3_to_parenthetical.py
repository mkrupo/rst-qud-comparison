"""Convert the RS3 structures in this repository to parenthetical RST."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


class RS3StructureError(ValueError):
    pass


class RS3SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class Node:
    node_id: str
    kind: str
    parent: str | None
    relation: str | None
    text: str = ""


@dataclass
class Document:
    nodes: dict[str, Node]
    children: dict[str, list[str]]
    relation_types: dict[str, set[str]]
    segment_positions: dict[str, int]


def parse_rs3(source) -> Document:
    try:
        root = ElementTree.parse(source).getroot()
    except (ElementTree.ParseError, OSError) as error:
        raise RS3StructureError(f"Unable to parse RS3 XML: {error}") from error

    if root.tag != "rst":
        raise RS3StructureError(f"Expected <rst> root, found <{root.tag}>")
    body = root.find("body")
    if body is None:
        raise RS3StructureError("RS3 document has no <body>")

    relation_types = {}
    for relation in root.findall("./header/relations/rel"):
        name = relation.get("name")
        relation_type = relation.get("type")
        if not name or relation_type not in {"rst", "multinuc"}:
            raise RS3SchemaError("Malformed relation declaration in RS3 header")
        relation_types.setdefault(name, set()).add(relation_type)

    nodes = {}
    segment_positions = {}
    for element in body:
        node_id = element.get("id")
        if not node_id:
            raise RS3StructureError(f"<{element.tag}> node has no id")
        if node_id in nodes:
            raise RS3StructureError(f"Duplicate node id {node_id!r}")

        if element.tag == "segment":
            if list(element):
                raise RS3StructureError(
                    f"Segment {node_id!r} contains unsupported nested XML elements"
                )
            kind = "segment"
            segment_positions[node_id] = len(segment_positions)
            text = element.text or ""
        elif element.tag == "group" and element.get("type") in {"span", "multinuc"}:
            kind = element.get("type")
            text = ""
        else:
            raise RS3StructureError(
                f"Unsupported body node <{element.tag}> with type {element.get('type')!r}"
            )

        parent = element.get("parent")
        relation = element.get("relname")
        if parent and not relation:
            raise RS3StructureError(f"Node {node_id!r} has a parent but no relname")
        if not parent and relation:
            raise RS3StructureError(f"Root node {node_id!r} has relname={relation!r}")
        if relation and any(character.isspace() or character in "()" for character in relation):
            raise RS3StructureError(
                f"Relation {relation!r} on node {node_id!r} is not a parenthetical token"
            )
        nodes[node_id] = Node(node_id, kind, parent, relation, text)

    if not nodes:
        raise RS3StructureError("RS3 body is empty")

    children = {node_id: [] for node_id in nodes}
    for node in nodes.values():
        if node.parent:
            if node.parent not in nodes:
                raise RS3StructureError(
                    f"Node {node.node_id!r} has dangling parent {node.parent!r}"
                )
            children[node.parent].append(node.node_id)
    return Document(nodes, children, relation_types, segment_positions)


def _descendant_positions(document: Document) -> dict[str, frozenset[int]]:
    positions = {}

    def collect(node_id):
        if node_id in positions:
            return positions[node_id]
        node = document.nodes[node_id]
        result = {document.segment_positions[node_id]} if node.kind == "segment" else set()
        for child_id in document.children[node_id]:
            result.update(collect(child_id))
        positions[node_id] = frozenset(result)
        return positions[node_id]

    for node_id in document.nodes:
        collect(node_id)
    return positions


def _multinuc_children(document: Document, node_id: str):
    core = []
    satellites = []
    for child_id in document.children[node_id]:
        child = document.nodes[child_id]
        if child.relation in {None, "span"}:
            raise RS3StructureError(
                f"Multinuc group {node_id!r} has child {child_id!r} "
                f"with invalid relation {child.relation!r}"
            )
        declared = document.relation_types.get(child.relation, set())
        if declared == {"multinuc"}:
            core.append(child_id)
        elif declared == {"rst"}:
            satellites.append(child_id)
        else:
            declaration = ", ".join(sorted(declared)) if declared else "undeclared"
            raise RS3StructureError(
                f"Multinuc child {child_id!r} relation {child.relation!r} must be "
                f"declared as exactly one of rst or multinuc, not {declaration}"
            )
    return core, satellites


def validate_structure(document: Document) -> str:
    state = {}

    def visit(node_id):
        if state.get(node_id) == 1:
            raise RS3StructureError(f"Cycle detected at node {node_id!r}")
        if state.get(node_id) == 2:
            return
        state[node_id] = 1
        for child_id in document.children[node_id]:
            visit(child_id)
        state[node_id] = 2

    for node_id in document.nodes:
        visit(node_id)

    roots = [node for node in document.nodes.values() if not node.parent]
    group_roots = [node for node in roots if node.kind != "segment"]
    titles = [node for node in roots if node.kind == "segment"]
    if len(group_roots) != 1:
        raise RS3StructureError(
            f"Expected one substantive root group, found {len(group_roots)}"
        )
    if (
        len(titles) > 1
        or any(document.children[node.node_id] for node in titles)
        or any(document.segment_positions[node.node_id] != 0 for node in titles)
    ):
        raise RS3StructureError(
            "Only one initial, childless title segment is supported alongside the root group"
        )

    for node in document.nodes.values():
        children = [document.nodes[child_id] for child_id in document.children[node.node_id]]
        if node.kind == "segment":
            if not " ".join(node.text.split()):
                raise RS3StructureError(f"Segment {node.node_id!r} has empty text")
            if len(children) > 1 or any(child.relation == "span" for child in children):
                raise RS3StructureError(
                    f"Segment {node.node_id!r} must have at most one non-span child"
                )
        elif node.kind == "span":
            nuclei = [child for child in children if child.relation == "span"]
            satellites = [child for child in children if child.relation != "span"]
            if len(nuclei) != 1 or len(satellites) > 1:
                raise RS3StructureError(
                    f"Span group {node.node_id!r} requires exactly one span child "
                    "and at most one satellite"
                )
        else:
            if len(children) < 2:
                raise RS3StructureError(
                    f"Multinuc group {node.node_id!r} requires at least two "
                    "multinuclear-core children"
                )
            core, satellites = _multinuc_children(document, node.node_id)
            if len(satellites) > 1:
                raise RS3StructureError(
                    f"Multinuc group {node.node_id!r} has multiple RST satellites; "
                    "multi-satellite normalization is unsupported"
                )
            if not 2 <= len(core) <= 5:
                raise RS3StructureError(
                    f"Multinuc group {node.node_id!r} requires two to five "
                    "multinuclear-core children"
                )
            relations = {document.nodes[child_id].relation for child_id in core}
            if len(relations) != 1:
                raise RS3StructureError(
                    f"Multinuc group {node.node_id!r} has heterogeneous "
                    "multinuclear-core relations: "
                    f"{sorted(relations)}"
                )

    positions = _descendant_positions(document)
    for node in document.nodes.values():
        if not positions[node.node_id]:
            raise RS3StructureError(f"Node {node.node_id!r} contains no segments")
        if node.kind == "segment":
            constituents = [{document.segment_positions[node.node_id]}]
            constituents += [positions[child_id] for child_id in document.children[node.node_id]]
        else:
            constituents = [positions[child_id] for child_id in document.children[node.node_id]]
        constituents.sort(key=min)
        if any(max(left) >= min(right) for left, right in zip(constituents, constituents[1:])):
            raise RS3StructureError(
                f"Node {node.node_id!r} has a non-projective child ordering"
            )
        if node.kind == "multinuc":
            core, satellites = _multinuc_children(document, node.node_id)
            if satellites:
                core_positions = frozenset().union(*(positions[child_id] for child_id in core))
                satellite_positions = positions[satellites[0]]
                if not (
                    max(core_positions) < min(satellite_positions)
                    or max(satellite_positions) < min(core_positions)
                ):
                    raise RS3StructureError(
                        f"RST satellite in multinuc group {node.node_id!r} "
                        "interleaves its multinuclear core"
                    )
    return group_roots[0].node_id


def schema_issues(document: Document) -> list[str]:
    issues = []
    for node in document.nodes.values():
        if not node.parent or node.relation == "span":
            continue
        if document.nodes[node.parent].kind == "multinuc":
            continue
        expected = "rst"
        declared = document.relation_types.get(node.relation, set())
        if expected not in declared:
            declaration = ", ".join(sorted(declared)) if declared else "undeclared"
            issues.append(
                f"Node {node.node_id!r} uses relation {node.relation!r} as {expected}, "
                f"but it is declared as {declaration}"
            )
    return issues


def validate_schema(document: Document) -> None:
    issues = schema_issues(document)
    if issues:
        raise RS3SchemaError("; ".join(issues))


def normalize_edu_text(text: str) -> str:
    text = " ".join(text.split())
    return text.replace("(", r"\(").replace(")", r"\)")


def _render(document: Document, root_id: str) -> str:
    positions = _descendant_positions(document)

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
            core, satellites = _multinuc_children(document, node_id)
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
    document = parse_rs3(source)
    root_id = validate_structure(document)
    if strict:
        validate_schema(document)
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
