import math

from minerva.curriculum import (
    _build_maps,
    _build_text,
    flatten,
    l2_to_cosine,
    load_document,
    lookup_node,
    normalize_assessment_key,
    node_path,
    resolve_topic,
    search,
)


class TestL2ToCosine:
    def test_zero_distance_gives_one(self):
        assert l2_to_cosine(0.0) == 1.0

    def test_sqrt2_gives_zero(self):
        # Normalised orthogonal vectors → L2 = √2, cosine similarity = 0
        assert abs(l2_to_cosine(math.sqrt(2))) < 1e-9

    def test_midpoint(self):
        # d=1.0 → 1 - (1²/2) = 0.5
        assert l2_to_cosine(1.0) == 0.5


class TestFlatten:
    def test_excludes_root_node(self, curriculum_tree):
        codes = [n.code for n in flatten(curriculum_tree)]
        assert "root" not in codes

    def test_includes_all_non_root_nodes(self, curriculum_tree):
        codes = {n.code for n in flatten(curriculum_tree)}
        assert codes == {"A1", "A1a", "A1b", "B1", "B1a"}

    def test_depth_first_order(self, curriculum_tree):
        codes = [n.code for n in flatten(curriculum_tree)]
        assert codes.index("A1") < codes.index("A1a")
        assert codes.index("A1b") < codes.index("B1")


class TestSearch:
    def test_finds_by_exact_code(self, curriculum_tree):
        nodes = flatten(curriculum_tree)
        results = search(nodes, "A1a")
        assert any(n.code == "A1a" for n in results)

    def test_finds_by_label_substring(self, curriculum_tree):
        nodes = flatten(curriculum_tree)
        results = search(nodes, "opioid")
        assert any(n.code == "A1a" for n in results)

    def test_case_insensitive(self, curriculum_tree):
        nodes = flatten(curriculum_tree)
        assert search(nodes, "OPIOID") == search(nodes, "opioid")

    def test_no_match_returns_empty(self, curriculum_tree):
        nodes = flatten(curriculum_tree)
        assert search(nodes, "zzznomatch") == []


class TestNodePath:
    def test_direct_child_of_root(self, curriculum_tree):
        path = node_path(curriculum_tree, "A1")
        assert [n.code for n in path] == ["A1"]

    def test_grandchild_includes_full_chain(self, curriculum_tree):
        path = node_path(curriculum_tree, "A1a")
        assert [n.code for n in path] == ["A1", "A1a"]

    def test_unknown_code_returns_empty(self, curriculum_tree):
        assert node_path(curriculum_tree, "ZZZZ") == []

    def test_root_excluded_from_path(self, curriculum_tree):
        path = node_path(curriculum_tree, "B1a")
        assert all(n.code != "root" for n in path)


class TestResolveTopic:
    def test_topic_without_node_returns_topic_only(self):
        resolved = resolve_topic("primary", None, "Rocuronium")

        assert resolved is not None
        assert resolved.node is None
        assert resolved.exam == "primary_frca"
        assert resolved.topic == "Rocuronium"

    def test_canonical_exam_is_preserved(self):
        resolved = resolve_topic("final_frca", None, "Airway")

        assert resolved is not None
        assert resolved.exam == "final_frca"

    def test_missing_topic_and_node_returns_none(self):
        assert resolve_topic("primary", None, None) is None

    def test_unknown_node_returns_none(self):
        assert resolve_topic("primary", "ZZZ", None) is None

    def test_lookup_node_finds_primary_node(self):
        result = lookup_node("primary", "1_PBC")

        assert result is not None
        node, exam = result
        assert node.code == "1_PBC"
        assert exam == "primary_frca"

    def test_node_without_exam_infers_exam(self):
        resolved = resolve_topic(None, "1_PBC", None)

        assert resolved is not None
        assert resolved.node is not None
        assert resolved.node.code == "1_PBC"
        assert resolved.exam == "primary_frca"
        assert resolved.topic == resolved.node.label


class TestNormalizeAssessmentKey:
    def test_accepts_legacy_primary_alias(self):
        assert normalize_assessment_key("primary") == "primary_frca"

    def test_accepts_legacy_final_alias(self):
        assert normalize_assessment_key("final") == "final_frca"

    def test_accepts_canonical_keys(self):
        assert normalize_assessment_key("primary_frca") == "primary_frca"
        assert normalize_assessment_key("final_frca") == "final_frca"

    def test_unknown_returns_none(self):
        assert normalize_assessment_key("unknown") is None


class TestLoadDocument:
    def test_loads_primary_curriculum_metadata(self):
        document = load_document("primary")

        assert document is not None
        assert document.key == "rcoa_primary_frca"
        assert document.owner_key == "rcoa"
        assert document.assessment_key == "primary_frca"
        assert document.version.label == "2.2"
        assert document.version.released_at == "2026-01-19"
        assert document.root.code == "root"

    def test_loads_primary_curriculum_by_canonical_key(self):
        document = load_document("primary_frca")

        assert document is not None
        assert document.assessment_key == "primary_frca"


class TestBuildMaps:
    def test_node_map_contains_all_nodes(self, curriculum_tree):
        node_map, _ = _build_maps(curriculum_tree)
        assert set(node_map) == {"root", "A1", "A1a", "A1b", "B1", "B1a"}

    def test_parent_map_correct_relationships(self, curriculum_tree):
        _, parent_map = _build_maps(curriculum_tree)
        assert parent_map["A1"] == "root"
        assert parent_map["A1a"] == "A1"
        assert parent_map["B1a"] == "B1"

    def test_root_has_no_parent(self, curriculum_tree):
        _, parent_map = _build_maps(curriculum_tree)
        assert "root" not in parent_map


class TestBuildText:
    def test_deep_node_joins_ancestor_labels(self, curriculum_tree):
        node_map, parent_map = _build_maps(curriculum_tree)
        assert _build_text("A1a", node_map, parent_map) == "Pharmacology. Opioids"

    def test_shallow_node_single_label(self, curriculum_tree):
        node_map, parent_map = _build_maps(curriculum_tree)
        assert _build_text("A1", node_map, parent_map) == "Pharmacology"

    def test_unknown_code_returns_empty(self, curriculum_tree):
        node_map, parent_map = _build_maps(curriculum_tree)
        assert _build_text("ZZZZ", node_map, parent_map) == ""
