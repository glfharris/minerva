from minerva.source_manifest import SourceManifest, SourceMetadata, discover_source_manifest


class TestSourceMetadata:
    def test_fallback_metadata_uses_file_name(self, tmp_path):
        path = tmp_path / "Useful Book.pdf"

        metadata = SourceMetadata.from_path(path)

        assert metadata.source_id == "useful_book"
        assert metadata.title == "Useful Book"
        assert metadata.source_type == "pdf"
        assert metadata.file_name == "Useful Book.pdf"


class TestSourceManifest:
    def test_resolves_source_by_relative_path(self, tmp_path):
        doc = tmp_path / "book.pdf"
        doc.write_text("placeholder")
        manifest_path = tmp_path / "source-manifest.json"
        manifest_path.write_text(
            """
            {
              "schema_version": "1",
              "sources": [
                {
                  "source_id": "peck_pharmacology",
                  "path": "book.pdf",
                  "title": "Pharmacology for Anaesthesia",
                  "source_type": "book",
                  "author_or_publisher": "Tom Peck",
                  "year": "2021",
                  "doi": "10.example/test"
                }
              ]
            }
            """
        )

        manifest = SourceManifest.load(manifest_path)
        metadata = manifest.resolve(doc)

        assert metadata.source_id == "peck_pharmacology"
        assert metadata.title == "Pharmacology for Anaesthesia"
        assert metadata.source_type == "book"
        assert metadata.author_or_publisher == "Tom Peck"
        assert metadata.year == "2021"
        assert metadata.doi == "10.example/test"
        assert metadata.file_name == "book.pdf"

    def test_resolves_source_by_file_name(self, tmp_path):
        doc = tmp_path / "renamed.pdf"
        doc.write_text("placeholder")
        manifest_path = tmp_path / "source-manifest.json"
        manifest_path.write_text(
            """
            {
              "sources": [
                {
                  "source_id": "manual",
                  "file_name": "renamed.pdf",
                  "title": "Manual",
                  "source_type": "manual"
                }
              ]
            }
            """
        )

        manifest = SourceManifest.load(manifest_path)

        assert manifest.resolve(doc).source_id == "manual"

    def test_falls_back_when_source_missing(self, tmp_path):
        doc = tmp_path / "Unknown.pdf"
        doc.write_text("placeholder")
        manifest_path = tmp_path / "source-manifest.json"
        manifest_path.write_text('{"sources": []}')

        manifest = SourceManifest.load(manifest_path)
        metadata = manifest.resolve(doc)

        assert metadata.source_id == "unknown"
        assert metadata.title == "Unknown"


class TestDiscoverSourceManifest:
    def test_discovers_manifest_for_directory(self, tmp_path):
        manifest = tmp_path / "source-manifest.json"
        manifest.write_text('{"sources": []}')

        assert discover_source_manifest(tmp_path) == manifest

    def test_discovers_manifest_for_file_parent(self, tmp_path):
        doc = tmp_path / "book.pdf"
        doc.write_text("placeholder")
        manifest = tmp_path / "sources.json"
        manifest.write_text('{"sources": []}')

        assert discover_source_manifest(doc) == manifest
