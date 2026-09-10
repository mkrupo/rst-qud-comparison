import io
import unittest

from convert_rs3_to_parenthetical import convert_rs3, parse_rs3
from normalize_rs3 import normalize_rs3, rs3_bytes


RST_RELATIONS = "".join(
    f'<rel name="{name}" type="rst"/>'
    for name in ("background", "evidence", "evaluation", "reason")
)
RELATIONS = RST_RELATIONS + '<rel name="joint" type="multinuc"/>'


def rs3(body, relations=RELATIONS):
    return io.StringIO(
        f"<rst><header><relations>{relations}</relations></header>"
        f"<body>{body}</body></rst>"
    )


def leaf(number):
    return f"( leaf t E{number} )"


class SatelliteNormalizationTests(unittest.TestCase):
    def assertConversion(self, body, expected):
        self.assertEqual(convert_rs3(rs3(body)), expected + " ")

    def test_n_s_s(self):
        self.assertConversion(
            '<segment id="1" parent="9" relname="span">E1</segment>'
            '<segment id="2" parent="1" relname="evidence">E2</segment>'
            '<segment id="3" parent="1" relname="evaluation">E3</segment>'
            '<group id="9" type="span"/>',
            f"( evaluation l ( evidence l {leaf(1)} {leaf(2)} ) {leaf(3)} )",
        )

    def test_s_s_n(self):
        self.assertConversion(
            '<segment id="1" parent="3" relname="background">E1</segment>'
            '<segment id="2" parent="3" relname="evidence">E2</segment>'
            '<segment id="3" parent="9" relname="span">E3</segment>'
            '<group id="9" type="span"/>',
            f"( background r {leaf(1)} ( evidence r {leaf(2)} {leaf(3)} ) )",
        )

    def test_s_n_s(self):
        self.assertConversion(
            '<segment id="1" parent="2" relname="background">E1</segment>'
            '<segment id="2" parent="9" relname="span">E2</segment>'
            '<segment id="3" parent="2" relname="evidence">E3</segment>'
            '<group id="9" type="span"/>',
            f"( evidence l ( background r {leaf(1)} {leaf(2)} ) {leaf(3)} )",
        )

    def test_s_n_s_s(self):
        self.assertConversion(
            '<segment id="1" parent="2" relname="background">E1</segment>'
            '<segment id="2" parent="9" relname="span">E2</segment>'
            '<segment id="3" parent="2" relname="evidence">E3</segment>'
            '<segment id="4" parent="2" relname="evaluation">E4</segment>'
            '<group id="9" type="span"/>',
            f"( evaluation l ( evidence l ( background r {leaf(1)} {leaf(2)} ) "
            f"{leaf(3)} ) {leaf(4)} )",
        )

    def test_multiple_satellites_around_span_nucleus(self):
        self.assertConversion(
            '<segment id="1" parent="9" relname="background">E1</segment>'
            '<segment id="2" parent="8" relname="span">E2</segment>'
            '<segment id="3" parent="2" relname="reason">E3</segment>'
            '<segment id="4" parent="9" relname="evidence">E4</segment>'
            '<group id="8" type="span" parent="9" relname="span"/>'
            '<group id="9" type="span"/>',
            f"( evidence l ( background r {leaf(1)} "
            f"( reason l {leaf(2)} {leaf(3)} ) ) {leaf(4)} )",
        )

    def test_multiple_satellites_around_multinuclear_nucleus(self):
        self.assertConversion(
            '<segment id="1" parent="9" relname="background">E1</segment>'
            '<segment id="2" parent="9" relname="joint">E2</segment>'
            '<segment id="3" parent="9" relname="joint">E3</segment>'
            '<segment id="4" parent="9" relname="evidence">E4</segment>'
            '<segment id="5" parent="9" relname="evaluation">E5</segment>'
            '<group id="9" type="multinuc"/>',
            f"( evaluation l ( evidence l ( background r {leaf(1)} "
            f"( joint c {leaf(2)} {leaf(3)} ) ) {leaf(4)} ) {leaf(5)} )",
        )

    def test_right_satellites_attach_nearest_first(self):
        self.assertConversion(
            '<segment id="1" parent="9" relname="span">E1</segment>'
            '<segment id="2" parent="1" relname="background">E2</segment>'
            '<segment id="3" parent="1" relname="evidence">E3</segment>'
            '<segment id="4" parent="1" relname="evaluation">E4</segment>'
            '<group id="9" type="span"/>',
            f"( evaluation l ( evidence l ( background l {leaf(1)} {leaf(2)} ) "
            f"{leaf(3)} ) {leaf(4)} )",
        )

    def test_left_satellites_attach_nearest_first(self):
        self.assertConversion(
            '<segment id="1" parent="4" relname="background">E1</segment>'
            '<segment id="2" parent="4" relname="evidence">E2</segment>'
            '<segment id="3" parent="4" relname="evaluation">E3</segment>'
            '<segment id="4" parent="9" relname="span">E4</segment>'
            '<group id="9" type="span"/>',
            f"( background r {leaf(1)} ( evidence r {leaf(2)} "
            f"( evaluation r {leaf(3)} {leaf(4)} ) ) )",
        )

    def test_left_side_is_attached_before_a_taller_right_satellite(self):
        self.assertConversion(
            '<segment id="1" parent="9" relname="background">E1</segment>'
            '<segment id="2" parent="9" relname="span">E2</segment>'
            '<segment id="3" parent="8" relname="joint">E3</segment>'
            '<segment id="4" parent="8" relname="joint">E4</segment>'
            '<group id="8" type="multinuc" parent="9" relname="evidence"/>'
            '<group id="9" type="span"/>',
            f"( evidence l ( background r {leaf(1)} {leaf(2)} ) "
            f"( joint c {leaf(3)} {leaf(4)} ) )",
        )

    def test_multinuc_satellite_is_transparent_to_a_unary_span_wrapper(self):
        direct = (
            '<segment id="1" parent="8" relname="background">E1</segment>'
            '<segment id="2" parent="8" relname="joint">E2</segment>'
            '<segment id="3" parent="8" relname="joint">E3</segment>'
            '<group id="8" type="multinuc"/>'
        )
        wrapped = (
            '<segment id="1" parent="9" relname="background">E1</segment>'
            '<segment id="2" parent="8" relname="joint">E2</segment>'
            '<segment id="3" parent="8" relname="joint">E3</segment>'
            '<group id="8" type="multinuc" parent="9" relname="span"/>'
            '<group id="9" type="span"/>'
        )
        self.assertEqual(convert_rs3(rs3(direct)), convert_rs3(rs3(wrapped)))

    def test_normalized_rs3_is_idempotent_and_preserves_source_information(self):
        body = (
            '<segment id="10" parent="90" relname="span"> Keep  (this). </segment>'
            '<segment id="30" parent="10" relname="evidence">E2</segment>'
            '<segment id="50" parent="10" relname="evaluation">E3</segment>'
            '<group id="90" type="span"/>'
        )
        first_document = normalize_rs3(rs3(body))
        first = rs3_bytes(first_document)
        second = rs3_bytes(normalize_rs3(io.BytesIO(first)))
        self.assertEqual(first, second)
        reparsed = parse_rs3(io.BytesIO(first))
        self.assertEqual(reparsed.nodes["10"].text, " Keep  (this). ")
        self.assertEqual(reparsed.nodes["30"].relation, "evidence")
        self.assertEqual(reparsed.nodes["50"].relation, "evaluation")
        self.assertEqual(reparsed.relation_types, first_document.relation_types)
        self.assertEqual(set(reparsed.nodes) - {"10", "30", "50", "90"}, {"91"})


if __name__ == "__main__":
    unittest.main()
