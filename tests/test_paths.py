from minerva.paths import slugify


class TestSlugify:
    def test_replaces_special_characters_with_underscores(self):
        assert slugify("Drug & Receptor Binding") == "drug_receptor_binding"

    def test_truncates_to_max_len_and_strips_trailing_separator(self):
        assert slugify("alpha beta gamma", max_len=10) == "alpha_beta"

    def test_uses_fallback_for_all_symbol_text(self):
        assert slugify("!!!", fallback="questions") == "questions"
