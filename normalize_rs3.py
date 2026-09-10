"""Validate and canonically normalize the RS3 structures used by this project."""

import argparse
import copy
from dataclasses import dataclass, replace
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
    node_order: list[str]
    header: ElementTree.Element | None
    root_attributes: dict[str, str]
    body_attributes: dict[str, str]


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
    node_order = []
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
        node_order.append(node_id)

    if not nodes:
        raise RS3StructureError("RS3 body is empty")

    document = Document(
        nodes,
        {},
        relation_types,
        segment_positions,
        node_order,
        copy.deepcopy(root.find("header")),
        dict(root.attrib),
        dict(body.attrib),
    )
    _rebuild_children(document)
    return document


def _rebuild_children(document: Document) -> None:
    document.children = {node_id: [] for node_id in document.nodes}
    for node in document.nodes.values():
        if node.parent:
            if node.parent not in document.nodes:
                raise RS3StructureError(
                    f"Node {node.node_id!r} has dangling parent {node.parent!r}"
                )
            document.children[node.parent].append(node.node_id)


def descendant_positions(document: Document) -> dict[str, frozenset[int]]:
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


def multinuc_children(document: Document, node_id: str):
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


def validate_structure(document: Document, *, normalized=False) -> str:
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
            satellites = children
            if any(child.relation == "span" for child in children):
                raise RS3StructureError(
                    f"Segment {node.node_id!r} cannot have a span child"
                )
        elif node.kind == "span":
            nuclei = [child for child in children if child.relation == "span"]
            satellites = [child for child in children if child.relation != "span"]
            if len(nuclei) != 1:
                raise RS3StructureError(
                    f"Span group {node.node_id!r} requires exactly one span child"
                )
        else:
            if len(children) < 2:
                raise RS3StructureError(
                    f"Multinuc group {node.node_id!r} requires at least two "
                    "multinuclear-core children"
                )
            core, satellite_ids = multinuc_children(document, node.node_id)
            satellites = [document.nodes[child_id] for child_id in satellite_ids]
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
        if normalized and len(satellites) > 1:
            raise RS3StructureError(
                f"Normalized node {node.node_id!r} still has multiple RST satellites"
            )

    positions = descendant_positions(document)
    for node in document.nodes.values():
        if not positions[node.node_id]:
            raise RS3StructureError(f"Node {node.node_id!r} contains no segments")
        if node.kind == "segment":
            constituents = [{document.segment_positions[node.node_id]}]
        else:
            constituents = []
        constituents += [positions[child_id] for child_id in document.children[node.node_id]]
        constituents.sort(key=min)
        if any(max(left) >= min(right) for left, right in zip(constituents, constituents[1:])):
            raise RS3StructureError(
                f"Node {node.node_id!r} has a non-projective child ordering"
            )
        if node.kind == "multinuc":
            core, satellites = multinuc_children(document, node.node_id)
            core_positions = frozenset().union(*(positions[child_id] for child_id in core))
            for satellite_id in satellites:
                satellite_positions = positions[satellite_id]
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
        declared = document.relation_types.get(node.relation, set())
        if "rst" not in declared:
            declaration = ", ".join(sorted(declared)) if declared else "undeclared"
            issues.append(
                f"Node {node.node_id!r} uses relation {node.relation!r} as rst, "
                f"but it is declared as {declaration}"
            )
    return issues


def validate_schema(document: Document) -> None:
    issues = schema_issues(document)
    if issues:
        raise RS3SchemaError("; ".join(issues))


def _copy_document(document: Document) -> Document:
    return Document(
        dict(document.nodes),
        {node_id: list(children) for node_id, children in document.children.items()},
        {name: set(types) for name, types in document.relation_types.items()},
        dict(document.segment_positions),
        list(document.node_order),
        copy.deepcopy(document.header),
        dict(document.root_attributes),
        dict(document.body_attributes),
    )


def _satellites_and_nucleus(document: Document, node_id: str, positions):
    node = document.nodes[node_id]
    if node.kind == "segment":
        satellites = list(document.children[node_id])
        nucleus_positions = frozenset({document.segment_positions[node_id]})
    elif node.kind == "span":
        nucleus_id = next(
            child_id
            for child_id in document.children[node_id]
            if document.nodes[child_id].relation == "span"
        )
        satellites = [
            child_id for child_id in document.children[node_id] if child_id != nucleus_id
        ]
        nucleus_positions = positions[nucleus_id]
    else:
        core, satellites = multinuc_children(document, node_id)
        nucleus_positions = frozenset().union(*(positions[child_id] for child_id in core))
    return satellites, nucleus_positions


def _ordered_satellites(document: Document, node_id: str):
    positions = descendant_positions(document)
    satellites, nucleus_positions = _satellites_and_nucleus(document, node_id, positions)
    left = []
    right = []
    for satellite_id in satellites:
        satellite_positions = positions[satellite_id]
        if max(satellite_positions) < min(nucleus_positions):
            left.append(satellite_id)
        elif max(nucleus_positions) < min(satellite_positions):
            right.append(satellite_id)
        else:
            raise RS3StructureError(
                f"Satellite {satellite_id!r} interleaves the nucleus of node {node_id!r}"
            )
    left.sort(key=lambda child_id: max(positions[child_id]), reverse=True)
    right.sort(key=lambda child_id: min(positions[child_id]))
    return left + right


def normalize_document(document: Document, *, strict=True) -> Document:
    """Return a normalized copy; never mutate the parsed source document."""
    validate_structure(document)
    if strict:
        validate_schema(document)
    normalized = _copy_document(document)
    numeric_ids = [int(node_id) for node_id in normalized.nodes if node_id.isdigit()]
    next_id = max(numeric_ids, default=0) + 1

    def new_group_id():
        nonlocal next_id
        while str(next_id) in normalized.nodes:
            next_id += 1
        result = str(next_id)
        next_id += 1
        return result

    def visit(node_id):
        for child_id in list(normalized.children[node_id]):
            visit(child_id)
        ordered = _ordered_satellites(normalized, node_id)
        if len(ordered) < 2:
            return

        node = normalized.nodes[node_id]
        outer_parent = node.parent
        outer_relation = node.relation
        current_id = node_id
        for satellite_id in ordered[1:]:
            group_id = new_group_id()
            normalized.nodes[current_id] = replace(
                normalized.nodes[current_id], parent=group_id, relation="span"
            )
            normalized.nodes[satellite_id] = replace(
                normalized.nodes[satellite_id], parent=group_id
            )
            normalized.nodes[group_id] = Node(group_id, "span", None, None)
            normalized.node_order.append(group_id)
            current_id = group_id
        normalized.nodes[current_id] = replace(
            normalized.nodes[current_id], parent=outer_parent, relation=outer_relation
        )
        _rebuild_children(normalized)

    roots = [node.node_id for node in normalized.nodes.values() if not node.parent]
    for root_id in roots:
        visit(root_id)
    validate_structure(normalized, normalized=True)
    if strict:
        validate_schema(normalized)
    return normalized


def normalize_rs3(source, *, strict=True) -> Document:
    return normalize_document(parse_rs3(source), strict=strict)


def rs3_bytes(document: Document) -> bytes:
    root = ElementTree.Element("rst", document.root_attributes)
    if document.header is not None:
        root.append(copy.deepcopy(document.header))
    body = ElementTree.SubElement(root, "body", document.body_attributes)
    for node_id in document.node_order:
        node = document.nodes[node_id]
        attributes = {"id": node.node_id}
        if node.kind != "segment":
            attributes["type"] = node.kind
        if node.parent:
            attributes["parent"] = node.parent
            attributes["relname"] = node.relation
        if node.kind == "segment":
            element = ElementTree.SubElement(body, "segment", attributes)
            element.text = node.text
        else:
            ElementTree.SubElement(body, "group", attributes)
    tree = ElementTree.ElementTree(root)
    ElementTree.indent(tree, space="  ")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def write_normalized_rs3(source, output, *, strict=True) -> None:
    Path(output).write_bytes(rs3_bytes(normalize_rs3(source, strict=strict)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a directory of RS3 XML files")
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
        write_normalized_rs3(
            input_path,
            args.out_path / input_path.name,
            strict=not args.compatibility,
        )


if __name__ == "__main__":
    main()
