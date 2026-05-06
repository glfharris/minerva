# Question Pool Website V1 Design

This document describes the current v1 idea for a small Django and HTMX website around a canonical pool of reviewed Single Best Answer questions.

## Product Principles

Minerva exists because existing question banks are often expensive, closed, and hard to improve from the outside. The long-term goal is to build a freely accessible, open question bank that can be trusted because its content is reviewed, versioned, cited, and open to community improvement.

The product should be guided by these principles:

- Free learner access should be the default goal. The question pool should not depend on paywalled access to the core learner experience.
- The bank should avoid lock-in. Question content, provenance, citations, curriculum alignment, attempts, and review decisions should be stored in formats that can be exported, audited, and migrated.
- Content can come from multiple routes: AI-assisted generation, conversion from suitable sources, manually authored JSON, and direct website authoring.
- AI-generated questions are candidate content, not trusted content. Human review, citation support, and curriculum alignment are required before publication.
- Community curation should improve the pool over time. V1 starts with editors, reviewers, and learner reports; later versions can add richer contribution, attribution, structured edits, and public governance workflows.
- Published learner-facing content should be stable and accountable. Attempts, reports, reviews, citations, and provenance should refer to the exact question version involved.
- The system should make quality visible without exposing unsafe or inappropriate internals. Clean citation and provenance metadata should support trust, while detailed generation internals can remain reviewer/admin information.

The first version should prove one complete workflow with two content entry paths:

1. Create candidate SBA questions either by importing Minerva CLI JSON or by manually authoring a complete SBA in the website.
2. Review each candidate question version.
3. Publish approved questions into one canonical learner-facing pool.
4. Let learners practise published questions.
5. Record attempts and reports against the exact question version shown.

Anything that does not directly support that loop should be deferred. Deferred ideas live in `design/future.md`.

## Goals

- Keep a canonical pool of reviewed SBA questions.
- Use a stable Minerva CLI JSON export as the primary bulk content path.
- Support simple manual authoring for complete text-only SBAs.
- Keep candidate content out of learner practice until a human has approved it.
- Preserve immutable question versions so review decisions, attempts, and reports always refer to the exact content seen.
- Provide enough source, citation, curriculum, and provenance metadata for review and later audit.
- Keep the implementation small enough to deliver before adding generation, banks, reuse, media, or rich contribution workflows.

## Non-Goals

V1 should not include:

- in-web AI generation
- source document upload, indexing, embedding, or retrieval inside the website
- image-based questions
- non-SBA formats
- long-lived in-web drafts
- structured learner proposed edits
- independently managed question banks or collections
- cross-bank reuse, request-to-reuse, or update propagation
- duplicate or similarity review workflows beyond optional cheap exact warnings
- rich attribution, contributor dashboards, or learner-facing contribution history
- configurable bank policies
- public or unlisted bank discovery
- spaced repetition or difficulty modelling
- mandatory two-person review

## Technology Direction

The expected stack is Django with HTMX.

Django fits the workflow-heavy parts: users, permissions, review queues, uploads, model validation, admin tooling, and audit-friendly records.

HTMX fits the first interface because most interactions are form and list driven: import validation, review queue filters, approval forms, publication actions, practice answers, and report submission.

## Project Structure And Environment

The website should live in this repository using a Cookiecutter Django-style structure, adapted to avoid confusion with the existing `minerva` CLI/library package.

Suggested repository structure:

```text
minerva/
  pyproject.toml
  README.md
  design/
  docs/

  minerva/
    cli/
    models.py
    generation.py
    conversion.py
    website_export.py

  config/
    settings/
      __init__.py
      base.py
      local.py
      test.py
      production.py
    urls.py
    asgi.py
    wsgi.py

  web/
    __init__.py
    users/
    curriculum/
    question_bank/

  manage.py
  compose.yaml
```

The existing `minerva` package remains the CLI and reusable library package. The Django project uses a root-level `config` package for settings and URLs, and a `web` package for local Django apps.

Suggested Django apps:

- `web.users`: custom user model, site-level account concerns, and role/group helpers
- `web.curriculum`: reusable curriculum tree models, such as `Curriculum`, `CurriculumVersion`, and `CurriculumNode`
- `web.question_bank`: question bank workflow models and services, including `Question`, `QuestionVersion`, `QuestionCurriculumAlignment`, imports, review, publication, attempts, and reports

`QuestionCurriculumAlignment` should live in `web.question_bank`, even though it points at `web.curriculum.CurriculumNode`, because the alignment is a question-bank relationship rather than a property of the curriculum tree itself.

### CLI And Website Boundary

The CLI and website should share a stable Pydantic import/export schema, but not database models.

Suggested boundary:

```text
Minerva CLI generation or conversion
  -> minerva.website_export.WebsiteQuestionSetV1
  -> website-targeted JSON export
  -> Django upload/import validation
  -> Django ORM records
```

The shared schema module should be pure and lightweight. It should not import Typer, LanceDB, embeddings, prompts, model clients, console helpers, or Django.

The website may import:

- `minerva.website_export`

The website should not import:

- `minerva.cli`
- `minerva.generation`
- `minerva.embed`
- `minerva.agent`
- prompt or retrieval internals

The Django app still owns its own database-backed models. The Pydantic website export schema is only the upload contract and validation layer.

### Dependency And Runtime Approach

Use `uv` for Python dependency management and command execution. Use Docker Compose for services.

Initial local development should run Django and the CLI on the host with `uv`, while Postgres runs in Docker Compose:

```text
uv run minerva ...
uv run python manage.py runserver
docker compose up postgres
```

This keeps early development fast while still using Postgres from the start. Django settings should be environment-driven so the app can later move into Docker without changing application code.

A Django container can be added later with the same command shape:

```text
docker compose up django postgres
```

The Python dependencies should eventually be split so the website can depend on the shared export schema without installing the full CLI/generation stack. A likely shape is:

```text
base dependencies: pydantic and shared lightweight library code
cli extra: Typer, Rich, pydantic-ai, LanceDB, sentence-transformers, PDF/conversion tooling
web extra: Django, django-htmx, Postgres driver, deployment/runtime helpers
```

The web image, when added, should install the web dependency set and use `uv` inside the container.

## Core Domain Model

### Question

`Question` is the stable educational object. It represents the concept being tested, not one exact wording.

Examples:

- `Adrenaline hyperglycaemia mechanism`
- `Suxamethonium hyperkalaemia after burns`

In v1, a `Question` belongs to the canonical pool and can have at most one current learner-facing version.

Suggested fields:

- title or concept label
- curriculum alignments, through `QuestionCurriculumAlignment`
- publication status: `unpublished`, `published`, or `retired`
- current published version, optional
- internal notes, optional
- published by, optional
- published at, optional
- retired by, optional
- retired at, optional
- retirement reason, optional

A question is eligible for learner practice only when:

- its publication status is `published`
- its `current_published_version` is approved
- required `Question` curriculum alignment is present and confirmed
- the current published version's review confirms that the version fits the question's curriculum alignment

Eligibility should be derived from those facts rather than stored as a separate status.

### QuestionVersion

`QuestionVersion` stores the exact learner-facing SBA content. It is immutable after creation.

Suggested content fields:

- question
- title
- stem
- lead-in
- five options
- stable option identity for each option
- correct option identity
- per-option explanations
- overall explanation
- option ordering mode: `fixed` or `randomizable`
- content approval status: `unreviewed`, `approved`, or `rejected`

Suggested review fields:

- reviewed by
- reviewed at
- completed proofing checklist
- citation support judgement
- curriculum alignment judgement
- structured rejection reason, optional
- review notes, optional

Citation, source, and provenance records may attach to a `QuestionVersion`, but they are editable metadata. Editing that metadata does not create a new version.

Durable curriculum alignment belongs to the stable `Question`, because it describes the educational concept rather than one exact wording. Review of each `QuestionVersion` should still confirm that the exact learner-facing content fits the `Question`'s curriculum alignment.

Changing learner-facing SBA content must create a new `QuestionVersion`. Historical attempts and reports continue to point at the older version.

### Options

V1 supports text-only SBA questions with:

- exactly five options
- exactly one correct option
- stable option identities within the version
- per-option explanations
- one overall explanation

Learner attempts must store the selected stable option identity, not only the displayed letter. This is required because display order may be randomized for versions marked `randomizable`.

### Sources And Citations

`Source` represents reference metadata, not a hosted source file.

Suggested `Source` fields:

- title
- source type: `book`, `article`, `web_page`, `manual`, `curriculum`, `pdf`, or `unknown`
- author or publisher, optional
- year, optional
- URL, optional
- DOI, optional
- file name or external reference, optional

`Citation` attaches a source reference to a `QuestionVersion`.

Suggested `Citation` fields:

- question version
- source
- page, section, or URL anchor, optional
- citation type: `retrieved`, `manual`, or `imported`
- support note, optional
- concise excerpt, optional where permitted
- added by

The website should not host or share full copyrighted source material in v1. Learners can see clean citation metadata where appropriate, but internal generation details should remain reviewer/admin information.

### Imported Provenance

The website should import enough CLI metadata to understand where a question version came from without modelling the full generation pipeline.

Imported provenance may include:

- export schema version
- Minerva CLI version
- source mode: `generated`, `converted`, `manual_json`, `external_bank`, `mixed`, or `unknown`
- external question id
- source question id, optional
- model, optional
- prompt version, optional
- topic, optional
- exam and curriculum context, optional
- generated, converted, or exported timestamps, optional
- token usage or estimated cost, optional

Generation metadata is not citation support. Citation support should come from `Source` and `Citation` records.

### Curriculum

V1 should preserve the existing Minerva curriculum node concept.

A curriculum is a versioned framework owned by some source, optionally associated with a domain and/or assessment. It may be external, such as RCoA, UKMLA, or MSRA, or internal, such as a Minerva cross-pool taxonomy.

Suggested model:

- `Curriculum`
- `CurriculumVersion`
- `CurriculumNode`
- `QuestionCurriculumAlignment`

Use `key` for Minerva's stable internal identifiers. Use `source_identifier` only for identifiers that come from the source framework itself.

Suggested `Curriculum` fields:

- key, such as `rcoa_primary_frca`, `gmc_ukmla`, or `minerva_medical_knowledge`
- title
- owner name, optional
- owner key, optional
- owner type: `organisation`, `exam_board`, `institution`, `community`, `minerva`, or `unknown`
- domain name, optional
- domain key, optional
- assessment name, optional
- assessment key, optional
- internal flag

Suggested `CurriculumVersion` fields:

- curriculum
- version label
- effective from, optional
- effective to, optional
- source URL, optional
- source file name, optional
- imported at

Curriculum versions should use honest labels from the source data where known. If the official version is not known, use an explicit internal label rather than guessing.

Suggested `CurriculumNode` fields:

- curriculum version
- key
- source identifier, optional
- label
- parent node, optional
- sort order, optional

`QuestionCurriculumAlignment` attaches curriculum nodes to the stable `Question`.

Suggested fields:

- question
- curriculum node
- status: `proposed`, `confirmed`, or `rejected`
- added by, optional
- confirmed by, optional
- added at
- confirmed at, optional
- notes, optional

For curriculum-backed practice, a published question should have at least one confirmed `QuestionCurriculumAlignment`, and the current published version's review should confirm that the exact version fits that alignment. Placeholder curriculum nodes are acceptable during development, but production content should avoid relying on `uncategorised` as a long-term substitute for meaningful alignment.

If a proposed replacement version changes the educational scope enough that the existing curriculum alignment no longer fits, it should usually be treated as a new `Question` rather than a new version of the same `Question`.

## Roles And Permissions

V1 needs simple site roles only.

### Editor

Editors can:

- upload Minerva CLI exports
- validate and import question sets
- manually author complete text-only SBA questions
- review question versions
- approve or reject question versions
- publish approved questions
- retire published questions
- close learner reports

### Reviewer

Reviewers can:

- view review queues
- manually author complete text-only SBA questions, if granted
- review question versions
- approve or reject question versions, if granted
- publish approved questions, if granted
- close learner reports, if granted

### Learner

Learners can:

- practise published questions
- submit reports against questions they can access
- review their own attempt history where implemented

Initial access can be assigned through Django groups or equivalent site-level roles. Bank-level roles are deferred.

## Content Creation

V1 supports two content creation paths:

- bulk import from a Minerva CLI `QuestionSet` JSON export
- simple manual authoring of a complete text-only SBA

Both paths create immutable `QuestionVersion` records with content approval status `unreviewed`, then enter the same review workflow.

### CLI Import

1. Editor generates or converts questions using the Minerva CLI.
2. Editor uploads the website-targeted JSON export.
3. The app validates the export schema version and required question fields.
4. The app creates an `ImportBatch`.
5. Existing curriculum node identifiers are mapped where possible, using the curriculum key, version label, node key, and source identifier where present.
6. The app creates `Question`, `QuestionVersion`, `QuestionCurriculumAlignment`, `Source`, `Citation`, and imported provenance records where supported.
7. Each imported `QuestionVersion` starts as `unreviewed`.
8. The app creates a `content_review` task for each imported version.

Initial imports should not require editor mapping decisions for every question. Duplicate detection can be limited to optional exact warnings if cheap.

### Manual Authoring

Manual authoring should be deliberately simple in v1. It is a single complete form for creating a text-only SBA, not a draft workflow.

The form should capture:

- question concept title
- stem
- lead-in
- exactly five options
- correct option
- per-option explanations
- overall explanation
- option ordering mode
- question curriculum alignment
- citation metadata, where available
- internal notes, optional

Saving a manually authored question should:

1. Create a `Question`.
2. Create an initial immutable `QuestionVersion` with approval status `unreviewed`.
3. Create source, citation, `Question` curriculum alignment, and provenance metadata where provided.
4. Create a `content_review` task.

Manual authoring should not create long-lived drafts in v1. If the author leaves before submitting the complete form, the system does not need to preserve partial work.

## Review Workflow

The workflow separates durable decisions from queue state:

- `QuestionVersion` owns content approval.
- `Question` owns publication into the canonical pool.
- `ReviewTask` owns operational queue state.

Review should use a shared queue by default. Assignment can be nullable and lightweight.

V1 task types:

- `content_review`
- `import`

V1 review filters:

- task type
- task status
- curriculum node, through the target question's alignment
- creator
- reviewer or assignee

Reviewers should check:

- answer is correct
- distractors are plausible and homogeneous
- explanations are accurate
- citation metadata supports the answer
- the exact version fits the question's curriculum alignment
- no unsafe or outdated guidance is present

Approval and publication should be separate actions, but an `approve and publish` shortcut is acceptable for users with permission to do both.

## Publication

Publishing makes an approved `QuestionVersion` available through the canonical learner-facing pool.

Rules:

- A question cannot be published without an approved current published version.
- A question cannot be published for curriculum-backed practice without confirmed `Question` curriculum alignment and version-level review confirmation that the current version fits that alignment.
- Retiring a question removes it from learner serving but does not delete historical attempts, reports, versions, citations, provenance, or review records.
- If a current published version is later rejected, the question becomes ineligible for learner practice until it has a new approved current version or is retired.

## Learner Practice

Learners practise from the canonical pool in v1.

Useful filters:

- curriculum node
- unanswered
- incorrect
- updated since answered
- random or newest
- question count

`UserQuestionAttempt` should be append-only.

Each attempt should store:

- user
- question
- exact question version shown
- practice session or filter context, optional
- displayed option order
- selected option identity
- correct or incorrect result
- answered at
- time taken, optional

Progress can roll up by stable `Question`, while still detecting when a newer approved version has been published since the learner last answered.

## Reports

Learners should be able to report issues using structured issue types plus free text.

Suggested issue types:

- `answer_incorrect`
- `ambiguous_question`
- `poor_explanation`
- `typo_or_formatting`
- `outdated_guidance`
- `wrong_curriculum_mapping`
- `wrong_scope_or_concept`
- `citation_problem`
- `other`

Reports should attach to:

- reporter
- exact `QuestionVersion` seen
- `Question`
- practice session or filter context, optional
- issue type
- free-text detail
- status: `open` or `closed`

Closing a report records triage notes and an explicit outcome. If the outcome requires content changes, v1 can record `accepted_for_follow_up`; the replacement content can arrive through a later import or another deliberately scoped editing workflow.

## State Transitions

The goal of the v1 lifecycle rules is to prevent impossible combinations of state while keeping the first implementation small.

Deferred workflows are tracked in `design/future.md`.

### Global Invariants

- `QuestionVersion` is immutable after creation.
- A `QuestionVersion` approval decision applies only to the exact content of that version.
- A `Question` has at most one current published version in v1.
- `Question.current_published_version` must be approved before the question can be served to learners.
- Learner serving eligibility is derived, not stored as a separate lifecycle state.
- A resolved `ReviewTask` must first write its durable outcome to its target object.
- Learner attempts must reference the exact `QuestionVersion` shown, the practice context, the displayed option order, and the selected stable option identity.
- Reports must reference the exact `QuestionVersion` seen and the practice context where the report was made.
- Retiring a `Question` must not delete historical attempts, reports, versions, citations, provenance, or review records.
- Citation, source, and provenance records are editable version metadata. Editing them does not create a new `QuestionVersion`.
- Curriculum alignment records belong to `Question`. Editing them does not create a new `QuestionVersion`, but a published question becomes ineligible for curriculum-backed practice if required confirmed alignment is removed or no longer applies to the current published version.
- If a published version is later rejected, the question becomes ineligible for learner serving until it has a new approved current version or is retired.

### QuestionVersion Approval

`QuestionVersion` stores exact SBA content and its content approval status.

States:

- `unreviewed`
- `approved`
- `rejected`

| From | To | Actor | Required side effect |
|---|---|---|---|
| `unreviewed` | `approved` | reviewer, editor | record reviewer, reviewed time, proofing checklist, citation support judgement, curriculum alignment judgement, and review notes |
| `unreviewed` | `rejected` | reviewer, editor | record reviewer, reviewed time, structured rejection reason, and rejection notes |
| `rejected` | `approved` | reviewer, editor | allowed only if the rejection was recorded in error; record reversal reason |
| `approved` | `rejected` | reviewer, editor | allowed only for serious post-approval errors; if this is the question's current published version, make the question ineligible for learner serving until it has a new approved current version or is retired |

Do not use `superseded` as an approval status. A previous approved version may be old without being wrong. Version lineage and publication choice should represent replacement.

Suggested rejection reasons:

- `incorrect_answer`
- `unsafe_or_outdated`
- `insufficient_citation_support`
- `poor_question_quality`
- `duplicate`
- `wrong_scope_or_curriculum`
- `created_in_error`
- `other`

### Question Publication

`Question` stores publication state for the canonical learner-facing pool.

States:

- `unpublished`
- `published`
- `retired`

| From | To | Actor | Required side effect |
|---|---|---|---|
| `unpublished` | `published` | editor, permitted reviewer | confirm `current_published_version` is approved; confirm required `Question` curriculum alignment; confirm the current version's review accepts that alignment; record publisher and published time |
| `published` | `retired` | editor, permitted reviewer | record retired time and reason; keep historical records intact |
| `retired` | `published` | editor, permitted reviewer | confirm `current_published_version` is approved; confirm required `Question` curriculum alignment; confirm the current version's review accepts that alignment; record publisher and published time |

Serving eligibility is true only when:

- `Question.publication_status == published`
- `Question.current_published_version.approval_status == approved`
- required `Question` curriculum alignment remains satisfied
- the current published version's review confirms that the version fits the alignment

V1 should not publish multiple current versions of the same `Question`. If two learner-facing variants are needed, that is future fork/reuse work.

### ReviewTask

`ReviewTask` is queue state. It is not the durable source of truth for the final decision.

States:

- `submitted`
- `in_review`
- `resolved`
- `cancelled`

| From | To | Actor | Required side effect |
|---|---|---|---|
| `submitted` | `in_review` | reviewer, editor | optionally assign reviewer and record review start time |
| `submitted` | `cancelled` | creator, reviewer, editor | record cancellation reason |
| `in_review` | `resolved` | reviewer, editor | write durable outcome to the target object before resolving |
| `submitted` | `resolved` | reviewer, editor | allowed for simple decisions; write durable outcome to the target object before resolving |
| `in_review` | `cancelled` | reviewer, editor | record cancellation reason |

V1 task types:

- `content_review`
- `import`

Content review outcomes:

- `approved`
- `rejected`

Import outcomes:

- `import_completed`
- `import_failed`

Durable outcome examples:

- content review writes approval status and review metadata to `QuestionVersion`
- import creates `Question`, `QuestionVersion`, `QuestionCurriculumAlignment`, `Source`, `Citation`, and provenance records where supported

### ImportBatch

`ImportBatch` tracks one uploaded Minerva CLI export.

States:

- `uploaded`
- `validated`
- `imported`
- `failed`
- `cancelled`

| From | To | Actor | Required side effect |
|---|---|---|---|
| `uploaded` | `validated` | system | validate JSON against the supported Minerva export schema |
| `uploaded` | `failed` | system | record validation errors |
| `validated` | `imported` | system | create question/version records and related question curriculum, source, citation, and provenance metadata |
| `validated` | `failed` | system | record import errors |
| `uploaded` | `cancelled` | editor | record cancellation reason |
| `validated` | `cancelled` | editor | record cancellation reason |

`ImportBatch` is operational. It may be pruned after import work is complete if durable provenance has been copied to the created records.

Whole-file idempotency is not a v1 invariant. Re-uploading the same file can be detected opportunistically while batch records exist.

### Learner Attempt

`UserQuestionAttempt` is append-only and does not need a mutable lifecycle in v1.

Each attempt should store:

- user
- question
- exact question version shown
- practice session or filter context, optional
- displayed option order
- selected option identity
- correct or incorrect result
- answered at
- time taken, optional

Attempts must not be deleted or rewritten when a question is edited, retired, rejected after publication, or replaced by a newer published version.

### Report Lifecycle

`Report` records learner or reviewer feedback about the exact version seen in a practice context.

States:

- `open`
- `closed`

| From | To | Actor | Required side effect |
|---|---|---|---|
| `open` | `closed` | reviewer, editor | record closure outcome, notes, closer, and closed time |

Closure outcomes:

- `accepted_for_follow_up`
- `rejected_no_issue`
- `duplicate_or_already_addressed`
- `no_change_needed`
- `other`

Closing a report is triage. If content needs to change, the corrected content should be handled by a later import or a deliberately scoped replacement-version workflow.

## Implementation Open Questions

- What exact first website export schema version should be supported?
- What exact dependency groups or extras should be used for CLI-only, web-only, and full development installs?
- What exact local environment variable names should be standardised for Django, Postgres, secrets, and optional future services?
- What exact RCoA curriculum version labels should be attached to the existing curriculum data?
- Which roles can publish in v1: editors only, or reviewers with an explicit permission?
- Should content corrections in v1 happen only through fresh imports, or should there be a small in-website "create replacement version" form?
