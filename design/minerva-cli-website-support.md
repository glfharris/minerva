# Minerva CLI Website Support

This document tracks changes needed in the Minerva CLI so the future question bank website can use CLI-generated or CLI-converted content as its primary early content path.

The website should not need to understand the full generation pipeline in early versions. The CLI should export enough structured metadata for the website to import, review, publish, audit, and later investigate question content.

## Goals

- Make `QuestionSet` exports stable enough to serve as the website import contract.
- Preserve exact generated or converted question content at import time.
- Provide stable option identities so learner attempts can remain auditable after option randomisation.
- Export provenance metadata without requiring the website to model CLI internals.
- Support AI-generated, converted, manually authored JSON, and mixed-origin question sets.
- Include citation/source metadata where the CLI can provide it.
- Keep the export useful even when the website later gains in-web AI generation.

## Export Schema Version

Add explicit export metadata to every website-targeted CLI export.

Suggested top-level fields:

- `export_schema_version`
- `minerva_cli_version`
- `exported_at`
- `exported_by`, optional
- `source_mode`, such as `generated`, `converted`, `manual_json`, `external_bank`, `mixed`, or `unknown`
- `questions`

The website should validate `export_schema_version` before import. Breaking export changes should increment the schema version and be documented with migration notes.

## Stable Question And Option Identity

Each exported question should include stable IDs for import and audit.

Suggested fields:

- `external_question_id`, stable within the export or source dataset
- `source_question_id`, optional when converted from an external question set
- `options[].option_id`, stable within the exported question

The website will create its own database IDs. CLI IDs are import identifiers and provenance aids, not website primary keys.

Option IDs are required because learner attempts should store selected option identity, not only the displayed letter. If the website later randomises options, the selected option must still be auditable.

## Question Provenance

Each question should be able to carry provenance independently from the batch-level metadata.

Suggested per-question fields:

- `origin_type`, optional override of batch `source_mode`
- `created_at`, optional
- `generated_by`, optional
- `converted_by`, optional
- `source_refs`, optional
- `generation_metadata`, optional
- `conversion_metadata`, optional

If a file contains mixed origins, the top-level `source_mode` should be `mixed` and each question should provide its own `origin_type`.

## Generation Metadata

For AI-generated questions, the CLI should export a compact generation summary.

Suggested fields:

- `method`, such as `rag`
- `model`
- `prompt_version`
- `topic`
- `exam`
- `curriculum_node_code`
- `generated_at`
- `token_usage`, optional
- `estimated_cost`, optional
- `retrieval_summary`, optional

Do not require the website to store full prompt chains, message histories, chain-of-thought, or retrieved source chunks. If the CLI exports detailed payloads for debugging, they should be clearly marked as optional and prunable.

Generation metadata is not citation support. It explains how the candidate was created. Medical support should be represented through sources and citations.

## Conversion Metadata

For converted question sets, the CLI should distinguish conversion from generation.

Suggested fields:

- `converter`
- `conversion_model`, optional if an LLM was used
- `converted_at`
- `input_type`, such as `pdf`, `markdown`, `text`, or `json`
- `source_title`, optional
- `source_url`, optional
- `source_file_name`, optional
- `source_page`, `section`, or `anchor`, optional where known

Converted questions may have no AI-generation metadata. They should still have source and contribution provenance.

## Sources And Citations

The CLI should export source/citation metadata where it can do so safely.

Suggested source fields:

- `source_id`
- `title`
- `source_type`, such as `book`, `article`, `web_page`, `manual`, `curriculum`, `pdf`, or `unknown`
- `author_or_publisher`
- `year`
- `url`
- `doi`
- `file_name`, optional

Suggested citation fields:

- `source_id`
- `page`
- `section`
- `url_anchor`
- `citation_type`, such as `retrieved`, `manual`, or `imported`
- `support_note`
- `concise_excerpt`, optional where permitted

The export should avoid embedding full copyrighted source material. Concise excerpts should be optional and clearly separated from support notes.

## Curriculum Metadata

The CLI currently exports curriculum node codes and scores. Website-targeted exports should also include enough context to map against versioned curricula.

Suggested fields:

- `exam`
- `curriculum_code`
- `curriculum_version_label`, if known
- `curriculum_node_codes`
- `curriculum_node_scores`
- `curriculum_path`, optional display context

The website may still remap or confirm bank-local alignment during import and review.

## Content Fingerprints

The CLI may export content fingerprints to help import duplicate detection, but the website should be able to compute them independently.

Suggested fields:

- `content_hash`
- `stem_hash`
- `lead_hash`
- `option_set_hash`
- `answer_hash`

Hashes should be based on documented normalisation rules. If normalisation changes, include a hash algorithm/version.

## Validation Requirements

Website-targeted exports should be strict enough that import errors are predictable.

Required question fields:

- title
- stem
- lead
- exactly five options
- stable option IDs
- exactly one correct option
- per-option explanations
- overall explanation
- option ordering mode, defaulting to `fixed`

The CLI should provide a validation command or flag for website exports so bank owners can check files before uploading them.

## Open Questions

- Should website-targeted export be a new command, such as `minerva export-web`, or a flag on existing commands?
- Should the CLI export retain backwards-compatible `QuestionSet` shape and add metadata, or introduce a new explicit `WebsiteQuestionSet` schema?
- What exact export schema version should be the first supported website import version?
- Should source and citation metadata be required for generated questions, or allowed to be absent until reviewers add citations in the website?
- Should content hashes be generated by the CLI, the website, or both?
