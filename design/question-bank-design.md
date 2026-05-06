# Question Pool Website V1 Design

This document describes the current v1 idea for a small Django and HTMX website around a canonical pool of reviewed Single Best Answer questions.

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

## Core Domain Model

### Question

`Question` is the stable educational object. It represents the concept being tested, not one exact wording.

Examples:

- `Adrenaline hyperglycaemia mechanism`
- `Suxamethonium hyperkalaemia after burns`

In v1, a `Question` belongs to the canonical pool and can have at most one current learner-facing version.

Suggested fields:

- title or concept label
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
- required curriculum alignment is present and confirmed

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
- structured rejection reason, optional
- review notes, optional

Citation, source, provenance, and curriculum alignment records may attach to a `QuestionVersion`, but they are editable metadata. Editing that metadata does not create a new version.

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

Suggested model:

- `Curriculum`
- `CurriculumVersion`
- `CurriculumNode`
- `QuestionVersionCurriculumAlignment`

Curriculum versions should use labels from the source data rather than guessed names.

For curriculum-backed practice, a published question should have at least one confirmed curriculum alignment. Placeholder curriculum nodes are acceptable during development, but production content should avoid relying on `uncategorised` as a long-term substitute for meaningful alignment.

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
5. Existing curriculum node codes are mapped where possible.
6. The app creates `Question`, `QuestionVersion`, `Source`, `Citation`, and imported provenance records.
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
- curriculum alignment
- citation metadata, where available
- internal notes, optional

Saving a manually authored question should:

1. Create a `Question`.
2. Create an initial immutable `QuestionVersion` with approval status `unreviewed`.
3. Create source, citation, curriculum alignment, and provenance metadata where provided.
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
- curriculum node
- creator
- reviewer or assignee

Reviewers should check:

- answer is correct
- distractors are plausible and homogeneous
- explanations are accurate
- citation metadata supports the answer
- curriculum alignment is appropriate
- no unsafe or outdated guidance is present

Approval and publication should be separate actions, but an `approve and publish` shortcut is acceptable for users with permission to do both.

## Publication

Publishing makes an approved `QuestionVersion` available through the canonical learner-facing pool.

Rules:

- A question cannot be published without an approved current published version.
- A question cannot be published for curriculum-backed practice without confirmed curriculum alignment.
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
- Citation, source, provenance, and curriculum alignment records are editable metadata. Editing them does not create a new `QuestionVersion`.
- If a published version is later rejected, the question becomes ineligible for learner serving until it has a new approved current version or is retired.

### QuestionVersion Approval

`QuestionVersion` stores exact SBA content and its content approval status.

States:

- `unreviewed`
- `approved`
- `rejected`

| From | To | Actor | Required side effect |
|---|---|---|---|
| `unreviewed` | `approved` | reviewer, editor | record reviewer, reviewed time, proofing checklist, citation support judgement, and review notes |
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
| `unpublished` | `published` | editor, permitted reviewer | confirm `current_published_version` is approved; confirm required curriculum alignment; record publisher and published time |
| `published` | `retired` | editor, permitted reviewer | record retired time and reason; keep historical records intact |
| `retired` | `published` | editor, permitted reviewer | confirm `current_published_version` is approved; confirm required curriculum alignment; record publisher and published time |

Serving eligibility is true only when:

- `Question.publication_status == published`
- `Question.current_published_version.approval_status == approved`
- required curriculum alignment remains satisfied

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
- import creates `Question`, `QuestionVersion`, `Source`, `Citation`, curriculum alignment, and provenance records where supported

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
| `validated` | `imported` | system | create question/version records and related source, citation, curriculum, and provenance metadata |
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
- Should the first Django implementation live in this repository or in a separate web project that depends on the Minerva package?
- What exact RCoA curriculum version labels should be attached to the existing curriculum data?
- Which roles can publish in v1: editors only, or reviewers with an explicit permission?
- Should content corrections in v1 happen only through fresh imports, or should there be a small in-website "create replacement version" form?
