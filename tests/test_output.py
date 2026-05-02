from minerva.models import QuestionSet
from minerva.output import default_filename, save_json, save_markdown


class TestDefaultFilename:
    def test_uses_curriculum_node_code_when_set(self, sample_question_set):
        qs = sample_question_set.model_copy(update={"curriculum_node_code": "A1a"})
        assert default_filename(qs) == "A1a_2026-04-30.json"

    def test_uses_topic_slug_when_no_node_code(self, sample_question_set):
        assert default_filename(sample_question_set) == "induction_agents_2026-04-30.json"

    def test_special_characters_replaced_with_underscore(self, sample_question_set):
        qs = sample_question_set.model_copy(update={"topic": "Drug & Receptor Binding"})
        filename = default_filename(qs)
        assert "&" not in filename
        assert " " not in filename

    def test_slug_truncated_to_40_chars(self, sample_question_set):
        qs = sample_question_set.model_copy(update={"topic": "a" * 60})
        slug = default_filename(qs).split("_2026")[0]
        assert len(slug) <= 40

    def test_all_symbol_topic_falls_back_to_questions(self, sample_question_set):
        qs = sample_question_set.model_copy(update={"topic": "!!!"})
        assert default_filename(qs).startswith("questions_")

    def test_custom_suffix(self, sample_question_set):
        assert default_filename(sample_question_set, suffix=".md").endswith(".md")


class TestSaveJson:
    def test_creates_file(self, tmp_path, sample_question_set):
        path = save_json(sample_question_set, tmp_path / "out.json")
        assert path.exists()

    def test_content_round_trips(self, tmp_path, sample_question_set):
        path = save_json(sample_question_set, tmp_path / "out.json")
        loaded = QuestionSet.model_validate_json(path.read_text())
        assert loaded.topic == sample_question_set.topic
        assert len(loaded.questions) == 1

    def test_directory_path_auto_generates_filename(self, tmp_path, sample_question_set):
        path = save_json(sample_question_set, tmp_path)
        assert path.parent == tmp_path
        assert path.suffix == ".json"

    def test_creates_parent_directories(self, tmp_path, sample_question_set):
        nested = tmp_path / "a" / "b" / "out.json"
        path = save_json(sample_question_set, nested)
        assert path.exists()


class TestSaveMarkdown:
    def test_creates_file(self, tmp_path, sample_question_set):
        path = save_markdown(sample_question_set, tmp_path / "out.md")
        assert path.exists()

    def test_contains_topic(self, tmp_path, sample_question_set):
        path = save_markdown(sample_question_set, tmp_path / "out.md")
        assert sample_question_set.topic in path.read_text()

    def test_contains_question_stem(self, tmp_path, sample_question_set):
        path = save_markdown(sample_question_set, tmp_path / "out.md")
        assert sample_question_set.questions[0].stem in path.read_text()

    def test_directory_path_auto_generates_filename(self, tmp_path, sample_question_set):
        path = save_markdown(sample_question_set, tmp_path)
        assert path.parent == tmp_path
        assert path.suffix == ".md"

    def test_json_file_path_writes_markdown_sidecar(self, tmp_path, sample_question_set):
        json_path = tmp_path / "questions.json"
        md_path = save_markdown(sample_question_set, json_path)

        assert md_path == tmp_path / "questions.md"
        assert md_path.exists()
        assert not json_path.exists()
