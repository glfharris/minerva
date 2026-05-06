# Minerva Context

This file defines the project language for Minerva. Use these terms in code,
tests, issues, and design notes so the same concept keeps the same name.

## Product Direction

Minerva is a tool for creating, validating, exporting, and practising Single
Best Answer questions for postgraduate medical examinations.

The current codebase is a CLI and reusable Python library. The design direction
in `docs/design` points toward a future Django/HTMX question pool website, but
current refactors should improve the existing CLI/library first.

The website direction matters because current exports should preserve enough
structured question content, curriculum alignment, source metadata, citation
metadata, and provenance for later import and review.

## Core Terms

### Single Best Answer Question

A text-only question with one stem, one lead-in, exactly five options, exactly
one correct option, per-option explanations, and one overall explanation.

In current code this is `Question`.

### Question Option

One of the five possible answers in a Single Best Answer question.

In current code this is `QuestionOption`.

For future website imports, each option needs a stable option identity so
attempts can record the selected option even if display order changes.

### Question Set

A batch of questions produced or converted together by Minerva.

In current code this is `QuestionSet`. It carries batch-level facts such as
topic, exam, model, generated time, optional pinned curriculum node, and the
questions themselves.

`QuestionSet` is the CLI/library runtime shape. It is not a database model.

### Website Question Set Export

A website-targeted JSON export shape used as an upload/import contract for the
future question pool website.

In current code this is `WebsiteQuestionSetV1` in `minerva.website_export`.

The website export schema should remain pure and lightweight. It should not
import Typer, LanceDB, embeddings, prompt logic, model clients, console helpers,
or Django.

### Question

In the future website design, a `Question` is the stable educational object:
the concept being tested, not one exact wording.

In current CLI code, `Question` means the exact SBA content. Be careful when
moving between current code and website design docs.

### Question Version

The exact learner-facing SBA content shown to a learner or reviewed by an
editor.

This is a future website concept. Current CLI exports should preserve enough
exact content and identity metadata for a website import to create immutable
`QuestionVersion` records later.

Changing learner-facing SBA content should create a new `QuestionVersion` in
the future website model.

### Curriculum

A versioned framework of examinable knowledge or capability. Minerva currently
ships RCoA Primary FRCA and Final FRCA curriculum trees.

In current code, curriculum trees use `CurriculumDocument` and `CurriculumNode`.

### Curriculum Node

A node in a curriculum tree. Nodes have stable codes/keys, labels, and children.

Current code accepts legacy `code` input and exposes `node.code` as a
compatibility alias for `node.key`.

### Curriculum Alignment

The relationship between question content and curriculum nodes.

Current CLI code stores alignment on questions as `curriculum_node_codes` and
`curriculum_node_scores` for JSON compatibility. New code should prefer
`QuestionCurriculumAlignment` and `QuestionCurriculumAlignmentResult` when
working inside Python, then apply back to the legacy fields at the edge.

In the future website design, durable curriculum alignment belongs to the stable
`Question`, while each `QuestionVersion` review confirms that the exact content
fits the alignment.

### Source

Reference metadata for a book, article, web page, manual, curriculum, PDF, or
unknown source.

In current code this is represented by `SourceMetadata` and source manifest
entries. In website export code this is `WebsiteSourceV1`.

A source is metadata, not the hosted full source file.

### Citation

A reference from exact question content to supporting source metadata, including
page, section, URL anchor, support note, or concise excerpt where appropriate.

In website export code this is `WebsiteCitationV1`.

Citation support is separate from generation metadata. Generation metadata says
how a candidate was created; citation metadata says why the answer is supported.

### Provenance

Metadata describing where a question came from and how it was produced or
converted.

Examples include source mode, external question id, model, prompt version,
topic, exam, generated time, converted time, token usage, source references, and
conversion metadata.

The website should not need to model the full Minerva generation pipeline to
import provenance.

### Generation

AI-assisted creation of new SBA questions from topic, curriculum context, and
retrieved reference material.

In current code this is mostly `minerva.generation`, `minerva.agent`, and the
create workflow.

Generated questions are candidate content, not trusted content.

### Conversion

Parsing existing unstructured SBA text, Markdown, or PDF content into structured
`QuestionSet` JSON.

In current code this is `minerva.conversion` and the convert workflow.

Converted questions may have no generation metadata but should still preserve
source and conversion provenance where available.

### Retrieval

Searching embedded reference material to provide grounding context for
generation or inspection.

In current code this is mostly `EmbedClient`. Retrieval currently formats prompt
text directly; future refactors may return structured chunks first and format
them through adapters.

### Workflow

An application-level operation that coordinates domain modules to produce a
usable result.

Current workflow examples are `create_question_set` and `convert_question_set`
in `minerva.workflows`.

CLI commands should remain thin adapters over workflows: parse arguments, call a
workflow, display results, save outputs, and translate workflow errors into
process exits.

### Artifact

A saved representation of Minerva output.

Current artifacts include legacy `QuestionSet` JSON and Markdown. A
website-targeted JSON export is a separate artifact shape.

## Current Architectural Guidance

- Keep `minerva.website_export` pure and lightweight.
- Keep CLI command modules thin.
- Put orchestration in workflow modules, not Typer commands.
- Preserve current JSON compatibility unless explicitly changing an export
  schema version.
- Prefer named value objects when they keep related facts together.
- Do not introduce a new module only to move one small helper behind a new name.
- Use tests at module interfaces to protect behaviour during refactors.

