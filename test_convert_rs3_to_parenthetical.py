import io
import unittest
from pathlib import Path

from convert_rs3_to_parenthetical import (
    RS3SchemaError,
    RS3StructureError,
    convert_rs3,
    normalize_edu_text,
    parse_rs3,
    schema_issues,
    validate_schema,
    validate_structure,
)
from convert_rst2qud import build_tree


REPOSITORY = Path(__file__).parent
LEGACY_ALIASES = {
    "eelaboration": "e-elaboration",
    "evaluationn": "evaluation-N",
    "evaluations": "evaluation-S",
    "mannermeans": "manner-means",
    "reasoN": "reason-N",
    "samenit": "sameunit",
}


def parse_parenthetical(text):
    tokens = text.split()
    index = 0

    def parse_node():
        nonlocal index
        if index >= len(tokens) or tokens[index] != "(":
            raise AssertionError(f"Expected '(' at token {index}")
        index += 1
        label = tokens[index]
        mode = tokens[index + 1]
        index += 2
        if label == "leaf":
            words = []
            while index < len(tokens) and tokens[index] != ")":
                words.append(tokens[index])
                index += 1
            if mode != "t" or index >= len(tokens):
                raise AssertionError("Malformed parenthetical leaf")
            index += 1
            leaf_text = " ".join(words).replace(r"\(", "(").replace(r"\)", ")")
            return ("leaf", leaf_text)

        children = []
        while index < len(tokens) and tokens[index] != ")":
            children.append(parse_node())
        if index >= len(tokens):
            raise AssertionError("Unclosed parenthetical relation")
        index += 1
        if mode not in {"l", "r", "c"} or len(children) != 2:
            raise AssertionError(f"Malformed relation {label!r}")
        return ("relation", label, mode, tuple(children))

    result = parse_node()
    if index != len(tokens):
        raise AssertionError(f"Unexpected tokens after position {index}")
    return result


def leaves(tree):
    if tree[0] == "leaf":
        return [tree[1]]
    return leaves(tree[3][0]) + leaves(tree[3][1])


def structural_shape(tree, *, legacy=False, next_leaf=None):
    if next_leaf is None:
        next_leaf = [0]
    if tree[0] == "leaf":
        leaf_number = next_leaf[0]
        next_leaf[0] += 1
        return ("leaf", leaf_number)
    relation = LEGACY_ALIASES.get(tree[1], tree[1]) if legacy else tree[1]
    return (
        relation,
        tree[2],
        structural_shape(tree[3][0], legacy=legacy, next_leaf=next_leaf),
        structural_shape(tree[3][1], legacy=legacy, next_leaf=next_leaf),
    )


def node_leaves(node):
    if node.is_leaf:
        return [node.text.strip()]
    result = []
    for child in node.children:
        result.extend(node_leaves(child))
    return result


def source_nodes(document):
    return sorted(
        (
            node
            for node in document.nodes.values()
            if node.kind == "segment" and node.parent is not None
        ),
        key=lambda node: document.segment_positions[node.node_id],
    )


def xml_document(body, relations=""):
    return io.StringIO(
        f"<rst><header><relations>{relations}</relations></header>"
        f"<body>{body}</body></rst>"
    )


class LegacyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs3 = {path.stem: path for path in (REPOSITORY / "rst").glob("*.rs3")}
        cls.trees = {
            path.stem: path for path in (REPOSITORY / "rst" / "parenthetical").glob("*.tree")
        }

    def test_all_43_legacy_pairs_are_discovered(self):
        self.assertEqual(set(self.rs3), set(self.trees))
        self.assertEqual(len(self.rs3), 43)

    def test_all_legacy_structures_match(self):
        for name in sorted(self.rs3):
            with self.subTest(document=name):
                generated = parse_parenthetical(convert_rs3(self.rs3[name], strict=False))
                published = parse_parenthetical(self.trees[name].read_text(encoding="utf-8"))
                self.assertEqual(
                    structural_shape(generated),
                    structural_shape(published, legacy=True),
                )

    def test_published_leaf_order_matches_source(self):
        discrepancies = []
        for name in sorted(self.rs3):
            document = parse_rs3(self.rs3[name])
            source = source_nodes(document)
            published = parse_parenthetical(self.trees[name].read_text(encoding="utf-8"))
            published_leaves = leaves(published)
            self.assertEqual(len(source), len(published_leaves), name)
            for node, published_text in zip(source, published_leaves):
                source_text = "".join(normalize_edu_text(node.text).replace("\\", "").split())
                legacy_text = "".join(published_text.split())
                if source_text != legacy_text:
                    discrepancies.append((name, node.node_id, source_text, legacy_text))
        self.assertEqual(
            discrepancies,
            [
                (
                    "UKW014_Transkript_p1",
                    "2",
                    "dieseganzenModellehabenZahlreicheParameter",
                    "dieseganzenModellehabenzahlreicheParameter",
                )
            ],
        )

    def test_legacy_schema_has_exactly_one_known_anomaly(self):
        found = []
        for name in sorted(self.rs3):
            document = parse_rs3(self.rs3[name])
            validate_structure(document)
            for issue in schema_issues(document):
                found.append((name, issue))
        self.assertEqual(
            found,
            [
                (
                    "UKW024_Transkript_p4",
                    "Node '3' uses relation 'list' as rst, but it is declared as multinuc",
                )
            ],
        )

    def test_strict_conversion_passes_other_legacy_documents(self):
        for name in sorted(self.rs3):
            if name == "UKW024_Transkript_p4":
                with self.assertRaisesRegex(RS3SchemaError, "relation 'list'"):
                    convert_rs3(self.rs3[name])
            else:
                with self.subTest(document=name):
                    convert_rs3(self.rs3[name])

    def test_all_compatibility_output_is_readable_by_existing_parser(self):
        for name in sorted(self.rs3):
            with self.subTest(document=name):
                document = parse_rs3(self.rs3[name])
                parsed = build_tree(convert_rs3(self.rs3[name], strict=False))
                self.assertEqual(
                    node_leaves(parsed),
                    [" ".join(node.text.split()) for node in source_nodes(document)],
                )


class SourceFidelityTests(unittest.TestCase):
    def test_text_relation_names_and_noncontiguous_ids_are_preserved(self):
        source = xml_document(
            """
            <segment id="10" parent="900" relname="span">
                Capital,adjacent? (literal) leaf t
            </segment>
            <segment id="50" parent="10" relname="e-elaboration">Satellite!</segment>
            <group id="900" type="span"/>
            """,
            '<rel name="e-elaboration" type="rst"/>',
        )
        converted = convert_rs3(source)
        self.assertEqual(
            converted,
            "( e-elaboration l ( leaf t Capital,adjacent? \\(literal\\) leaf t ) "
            "( leaf t Satellite! ) ) ",
        )
        self.assertNotIn("eelaboration", converted)

    def test_existing_parser_preserves_standalone_leaf_and_t(self):
        parsed = build_tree("( elaboration l ( leaf t leaf t ) ( leaf t t leaf ) )")
        self.assertEqual(node_leaves(parsed), ["leaf t", "t leaf"])

    def test_generated_escaped_parentheses_survive_existing_parser(self):
        source = xml_document(
            '<segment id="1" parent="9" relname="span">Keep (this), Exactly?</segment>'
            '<group id="9" type="span"/>'
        )
        parsed = build_tree(convert_rs3(source))
        self.assertEqual(node_leaves(parsed), ["Keep (this), Exactly?"])


class ValidationTests(unittest.TestCase):
    def assertStructureError(self, body, message):
        with self.assertRaisesRegex(RS3StructureError, message):
            convert_rs3(xml_document(body))

    def test_dangling_parent_is_rejected(self):
        self.assertStructureError(
            '<segment id="1" parent="missing" relname="span">text</segment>',
            "dangling parent",
        )

    def test_cycle_is_rejected(self):
        self.assertStructureError(
            '<segment id="1" parent="2" relname="elaboration">one</segment>'
            '<segment id="2" parent="1" relname="elaboration">two</segment>'
            '<segment id="3" parent="4" relname="span">root</segment>'
            '<group id="4" type="span"/>',
            "Cycle detected",
        )

    def test_multiple_substantive_roots_are_rejected(self):
        self.assertStructureError(
            '<segment id="1" parent="3" relname="span">one</segment>'
            '<segment id="2" parent="4" relname="span">two</segment>'
            '<group id="3" type="span"/><group id="4" type="span"/>',
            "one substantive root group",
        )

    def test_malformed_span_group_is_rejected(self):
        self.assertStructureError(
            '<segment id="1" parent="3" relname="span">one</segment>'
            '<segment id="2" parent="3" relname="span">two</segment>'
            '<group id="3" type="span"/>',
            "exactly one span child",
        )

    def test_malformed_multinuc_groups_are_rejected(self):
        self.assertStructureError(
            '<segment id="1" parent="2" relname="conjunction">one</segment>'
            '<group id="2" type="multinuc"/>',
            "two to five related children",
        )
        relations = (
            '<rel name="conjunction" type="multinuc"/>'
            '<rel name="list" type="multinuc"/>'
        )
        with self.assertRaisesRegex(RS3StructureError, "heterogeneous relations"):
            convert_rs3(
                xml_document(
                    '<segment id="1" parent="3" relname="conjunction">one</segment>'
                    '<segment id="2" parent="3" relname="list">two</segment>'
                    '<group id="3" type="multinuc"/>',
                    relations,
                )
            )

    def test_schema_mismatch_is_strict_only_and_structure_is_preserved(self):
        body = (
            '<segment id="1" parent="3" relname="span">one</segment>'
            '<segment id="2" parent="1" relname="list">two</segment>'
            '<group id="3" type="span"/>'
        )
        relations = '<rel name="list" type="multinuc"/>'
        document = parse_rs3(xml_document(body, relations))
        self.assertEqual(validate_structure(document), "3")
        with self.assertRaises(RS3SchemaError):
            validate_schema(document)
        with self.assertRaisesRegex(RS3SchemaError, "declared as multinuc"):
            convert_rs3(xml_document(body, relations))
        self.assertEqual(
            convert_rs3(xml_document(body, relations), strict=False),
            "( list l ( leaf t one ) ( leaf t two ) ) ",
        )


if __name__ == "__main__":
    unittest.main()
