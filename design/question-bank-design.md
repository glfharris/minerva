# Question Bank Website Design

This document captures the product and domain decisions for a future Django and HTMX website built around Minerva-generated Single Best Answer questions.

The website should host, review, publish, practise, and improve question bank content. It should also support AI generation inside the website, but with a human review step before learner-facing publication.

## Goals

- Support multiple independently managed question banks.
- Reuse the existing Minerva `QuestionSet` JSON format as an import path.
- Allow bank owners to generate questions with AI inside the web app.
- Keep generated questions out of the published bank until a human has reviewed them.
- Let learners report issues and help improve published questions.
- Let questions be reused across banks without duplicating content unnecessarily.
- Preserve immutable question versions so reports, attempts, citations, and review decisions refer to the exact content seen.

## Initial Technology Direction

The expected web stack is Django with HTMX.

Django is a good fit because the core product is workflow-heavy: users, permissions, review queues, versioned content, admin tooling, uploads, and audit trails. HTMX is a good fit because most interactions are form and list driven: filtering review queues, approving drafts, adding citations, submitting reports, and practising questions.

## Core Domain Model

### Question

`Question` is the stable reusable educational object. It represents the underlying concept being tested, not one exact wording.

Examples:

- `Adrenaline hyperglycaemia mechanism`
- `Suxamethonium hyperkalaemia after burns`

A question can appear in multiple question banks.

### QuestionVersion

`QuestionVersion` is immutable and stores the exact learner-facing SBA content:

- title
- stem
- lead-in
- five immutable options, each with a stable identity within the version
- correct option
- per-option explanations
- overall explanation
- option ordering mode
- citations
- source/provenance links
- content approval state

Published edits create a new `QuestionVersion`. Existing versions are preserved for reports, learner attempts, audit history, and comparison.

Options are part of the immutable version. Editing option text, changing the correct option, or changing an option explanation should create a new `QuestionVersion`.

Learner attempts and reports should refer to the stable option identity, not only to the displayed letter. The displayed letter may change if a version is marked as randomizable, but the selected option identity must remain auditable.

Content approval belongs to the `QuestionVersion`. Either the exact version is accurate, well supported, and suitable for publication, or it is not. That judgement should not vary by question bank. Bank-specific review decides whether an approved version belongs in that bank, not whether the content is intrinsically correct.

Content approval should record:

- approval status, such as unreviewed, approved, rejected, or superseded
- reviewer
- reviewed at
- completed proofing checklist
- citation support judgement, such as citations_support_answer or insufficient_support
- review notes

Reviewers explicitly choose whether an edit is:

- a new version of the same question
- a fork into a new question

A change should remain a new version if it preserves the same learning objective, correct answer, reasoning pathway, and curriculum alignment. It should become a new question if it changes the tested concept, correct answer, exam level, curriculum alignment, or answer logic materially.

### Question Format

V1 should support Single Best Answer questions only:

- exactly five options
- exactly one correct option
- per-option explanations
- overall explanation
- fixed or randomizable option ordering

Image-based SBAs should be allowed as an SBA subtype, not as a separate question format.

Suggested model:

- `QuestionMedia`

`QuestionMedia` should record:

- question version
- media type, initially image
- file reference
- caption, optional
- alt text
- source or contribution reference where relevant
- display order

Media belongs to `QuestionVersion` because changing the image can change the question. Learner attempts should therefore continue to reference the exact immutable version shown.

Non-SBA formats, such as multi-select, true/false, EMQ, short answer, and OSCE or viva prompts, are deferred.

### Contribution and Attribution

Contribution and attribution should be a first-class model rather than only simple `created_by` fields.

The site needs to credit both internal users and external sources. For example, a question may start as an imported open-access Royal College question, then be updated by one user, then forked or substantially revised by another.

Attribution is separate from citation support. Citation support answers "what source supports this answer?" Attribution answers "who or what should receive credit for this question or version?"

Suggested model:

- `QuestionContribution`
- `ContributorIdentity`

`ContributorIdentity` can represent:

- a site user
- an external person
- an organisation, such as the Royal College of Anaesthetists
- an external source or imported question set

`QuestionContribution` should record:

- question version
- contributor identity
- role, such as original_author, original_source, editor, reviewer, fork_author, importer, or citation_verifier
- contribution summary
- whether the contribution is learner-visible or admin/reviewer-only
- materiality, such as minor_edit, material_revision, original_import, review, or fork
- ordering for display
- attributed at

Contribution tracking should be internal by default. In v1, it is primarily for audit history, provenance tracking, moderation, and future contributor statistics. Learner-facing attribution can be added later on a per-contribution or per-bank basis.

A future learner-facing display might be:

`Adapted from RCoA sample questions. Updated by Person A. Forked by Person B.`

Reviewer and admin views can show fuller attribution, including reviewers, importers, citation verifiers, and internal audit details.

Question-level attribution should normally be derived by collapsing the contribution events from the relevant `QuestionVersion` lineage. For example, a dashboard could later show how many questions a user submitted, edited, reviewed, or had published by aggregating contribution events.

When a question is reused in another bank, attribution should travel with the shared `QuestionVersion`.

When a question is forked, the new question should preserve lineage back to the source question and source version, while starting its own attribution chain from the fork point.

### QuestionBank

`QuestionBank` is an independently managed collection of questions.

Examples:

- `Primary FRCA Pharmacology`
- `Final FRCA Revision`
- `Burns Anaesthesia Revision`
- `Interesting ICU SBAs`

A bank has owners and members, visibility settings, contribution policies, reuse policies, and either a curriculum-backed or freeform organisation mode.

### QuestionBankEntry

`QuestionBankEntry` is the relationship between a reusable `Question` and a specific `QuestionBank`.

It stores bank-specific publication and workflow state, such as:

- bank
- question
- current published version
- locally selected version awaiting publication
- status
- local review notes
- local curriculum alignment or tags
- added by
- approved by
- published at
- retired at

This name is preferred over `QuestionBankItem` and `QuestionBankMember`.

`QuestionBankItem` is simple but too vague once review, publication, and retirement state are added.

`QuestionBankMember` should be avoided because "member" is better reserved for users belonging to a bank.

Each `QuestionBankEntry` should have at most one currently published version. Forks can exist as separate questions and therefore separate entries.

## Curricula

The existing Minerva curriculum node concept should be preserved.

Royal College of Anaesthetists curricula should be represented as canonical, versioned reference data because exam curricula can change over time.

Suggested model:

- `Curriculum`
- `CurriculumVersion`
- `CurriculumNode`

Example versions:

- `RCoA Primary FRCA`
- `RCoA Final FRCA`

The exact version labels should be taken from the source data rather than guessed.

Curriculum versions can have lifecycle states, such as draft, active, retired, or dev/test. This allows new exams or development fixtures to use a minimal placeholder curriculum before the full canonical structure exists.

For example, a draft curriculum for a new exam might initially contain broad nodes such as general, pharmacology, physiology, and uncategorised.

Placeholder nodes are acceptable for development and early scaffolding. Production exam banks should avoid using uncategorised nodes as a long-term substitute for meaningful curriculum alignment.

### Curriculum-Backed Banks

A curriculum-backed question bank has a primary curriculum version.

Learners mainly see the bank-relevant curriculum path. For example, a Final FRCA bank should present Final FRCA alignment rather than cluttering the learner view with Primary FRCA or unrelated specialty alignments.

Publication rule: a curriculum-backed bank should require at least one bank-local confirmed curriculum alignment before a question can be published in that bank.

### Freeform Banks

Some banks may not have a formal curriculum. These should be allowed.

For v1, freeform banks should use bank-scoped tags as lightweight organisation:

- tags are optional by default
- bank owners can require at least one tag later if needed
- category trees should be deferred unless tags prove insufficient

Publication rule: a freeform bank should not require curriculum alignment. It may optionally require at least one bank-scoped tag if the bank owner enables that setting.

### Global and Local Alignment

Question versions can have global curriculum alignments across multiple curricula.

Each question bank entry can also have a bank-local confirmed alignment.

Example:

One question about suxamethonium hyperkalaemia after burns may be globally aligned to both Primary FRCA pharmacology and Final FRCA burns/perioperative management. In a Final FRCA bank, the learner should mainly see the Final FRCA placement. In a Primary FRCA pharmacology bank, the learner should mainly see the pharmacology placement.

## Roles and Permissions

Roles should distinguish site-level administration from bank-level permissions.

### Site-Level Role

- `SiteAdmin`: manages platform-level concerns, such as users, abuse/moderation, canonical curricula, global source/reference data, system configuration, and support tasks.

`SiteAdmin` is not the normal editorial owner of every question bank. Bank-level editorial control should remain with each bank's owners and reviewers unless platform intervention is required.

### Bank-Level Roles

Initial bank-level roles:

- `Owner`: manages the bank, runs AI generation, configures settings, reviews, approves, and publishes.
- `Reviewer`: reviews submissions, edits, approves, rejects, forks, and publishes if granted by the bank.
- `Contributor`: writes or imports manual questions and submits them for review.
- `Learner`: practises published questions and submits reports or suggestions according to bank policy.

Bank-level roles should be assigned through `BankMembership`.

`BankMembership` is the relationship between a user and a question bank. It is separate from `QuestionBankEntry`, which is the relationship between a question and a question bank.

`BankMembership` should record:

- bank
- user
- role, such as owner, reviewer, contributor, or learner
- membership status, such as active, invited, suspended, or left
- invited by, optional
- joined at

AI generation should be bank-owner-only in v1. It can be expanded later.

Owners may review their own AI-generated questions, but generated questions must still pass through an explicit human-in-the-loop review/proofing workflow before publication.

## Bank Settings

### Visibility

Banks should have explicit visibility settings, defaulting to private:

- `private`: invited members only
- `unlisted`: accessible by link
- `public`: discoverable and viewable by users according to policy

### Contribution Policy

Contribution policy should be bank-configurable:

- who can report issues
- who can leave free-text suggestions
- who can submit structured proposed edits
- who can submit new manual/imported questions

Default v1 policy:

- reports: any logged-in user with access
- free-text suggestions: any logged-in user with access
- structured proposed edits: contributors by default, configurable
- new manual/imported question submissions: contributors
- AI generation: owner only

### Reuse Policy

Question reuse should also be bank-configurable.

Most published content is expected to be relatively open within the site, so the default posture should favour discoverability and reuse. More restrictive settings exist for private or tightly curated banks.

Discoverability and reuse should be treated as related but separate permissions. A bank may allow its published questions to appear in duplicate/similarity search without allowing other banks to add those questions directly.

Suggested discoverability policies:

- `private`: not visible outside this bank
- `metadata_visible`: other bank reviewers can see limited metadata in duplicate/similarity search
- `content_visible`: other bank reviewers can inspect the full published question where access policy allows

Suggested reuse policies:

- `private`: only this bank can reuse its questions
- `members_only`: bank members can reuse questions into their other banks
- `site_reusable`: any bank owner or reviewer can reuse published questions
- `request_required`: other banks can request reuse

The default should be `content_visible` and `site_reusable` for published questions.

Bank visibility controls learner access. Discoverability and reuse policies control reviewer workflows across banks.

Private banks should default to private discoverability and private reuse. A private bank owner can explicitly opt into limited cross-bank discoverability or reuse, such as metadata-only duplicate search or request-required reuse, without making the bank learner-visible.

## Review Workflow

The workflow should separate durable domain decisions from temporary queue state.

Three objects should own different parts of the process:

### QuestionVersion Content Approval

`QuestionVersion` owns content approval.

This answers: is this exact SBA version medically correct, well written, and supported by evidence?

This is a global judgement about the immutable version. It should not vary by question bank.

Example fields:

- content approval status, such as unreviewed, approved, rejected, or superseded
- reviewed by
- reviewed at
- proofing checklist
- citation support judgement, such as citations_support_answer or insufficient_support
- review notes

### QuestionBankEntry Local Publication

`QuestionBankEntry` owns local publication.

This answers: should this approved question version appear in this specific bank?

This is bank-specific. A question can be content-approved but still not belong in a given bank.

Example fields:

- bank
- question
- current published version
- locally selected version awaiting publication
- local publication status, such as unpublished, published, or retired
- local curriculum alignment or tags
- published by
- published at

Approval and publication should be separate actions, with an `approve and publish` shortcut.

### ReviewTask Queue State

`ReviewTask` owns reviewer queue state.

This answers: what work currently needs human attention?

It is operational work tracking, not the long-term source of truth. When a review task is resolved, the durable decision should be written back to `QuestionVersion`, `QuestionBankEntry`, a report, or a question draft.

Review should use a shared queue by default in v1. `ReviewTask` may have an optional assignee, but assignment should be lightweight and nullable. Complex workload balancing, SLAs, and mandatory assignment rules are deferred.

`ReviewTask` should be able to point at the relevant object, such as:

- a `QuestionVersion`
- a `QuestionBankEntry`
- a report
- a `QuestionDraft`
- an import batch
- a reuse candidate

Review task sources:

- `ai_generated`
- `manual`
- `imported`
- `proposed_edit`
- `report_fix`
- `reuse_candidate`

Review task states:

- `submitted`
- `in_review`
- `changes_requested`
- `resolved`
- `cancelled`

Review queues should be filterable by:

- source
- status
- curriculum node or tag
- report count
- creator
- reviewer or assignee
- generated model, later if useful

For AI-generated questions, review should include a checklist confirming:

- answer is correct
- distractors are plausible and homogeneous
- explanations are accurate
- citations support the answer
- curriculum alignment is appropriate
- no unsafe or outdated medical guidance is present

## Sources and Citations

The website should store citation metadata and review provenance for generated and manually submitted questions.

Citation metadata should travel with the `QuestionVersion` when a question is reused in another bank.

The site should not host or share full source materials in v1. Citations are references to source material, not copies of the source material. Learner-facing citations should not imply that the learner has access to the cited PDF, book, article, or external resource through the site.

Suggested objects:

- `Source`
- `Citation`
- `GenerationRun`

`Source` represents bibliographic or reference metadata, not necessarily a hosted file:

- title
- source type, such as PDF, book, article, web page, manual, or curriculum
- author or publisher
- year
- URL, DOI, file reference, page, or section where available

`Citation` attaches a source reference to a `QuestionVersion`. In v1, citations should store reviewable support metadata and concise supporting notes where appropriate, but not full copyrighted source material:

- source
- concise excerpt, quote, or supporting note where permitted
- page, section, or URL anchor
- added by
- citation type, such as retrieved, manual, or imported
- support note, describing how this source supports or contextualises the answer

`GenerationRun` stores AI generation metadata:

- model
- prompt version
- topic
- bank and curriculum context if provided
- created by
- created at
- token usage or cost if available

AI generation should have owner-level and bank-level limits or quotas in v1. Token usage and estimated cost should be recorded where available and visible to bank owners and site admins.

Learners should see clean citations and source metadata so they know where to read more. They should not see the full prompt chain, critique history, retrieval scores, or internal AI-generation provenance.

Reviewers should see enough evidence and provenance to assess the question, including citation details, concise supporting notes, and permitted excerpts. Full source document hosting and sharing is out of scope for v1.

## Reports and Proposed Edits

Learners should be able to report issues using structured issue types plus free text.

Suggested issue types:

- `answer_incorrect`
- `ambiguous_question`
- `poor_explanation`
- `typo_or_formatting`
- `outdated_guidance`
- `wrong_curriculum_mapping`
- `citation_problem`
- `other`

Reports should attach to:

- the exact `QuestionVersion` seen
- the `QuestionBankEntry` context where the report was made
- the reporter

Reports should have statuses:

- `open`
- `triaged`
- `accepted`
- `rejected`
- `resolved`

Free-text feedback belongs to reports and suggestions. A structured proposed edit is different: it should represent a draft replacement for a specific immutable `QuestionVersion`.

`QuestionDraft` is the place for editable question drafts. This lets users stage generated, imported, manual, or edited questions over several sessions before submitting them for review, while preserving `QuestionVersion` as the immutable record of submitted, approved, rejected, or published content.

Drafts should be flexible. A user should be able to draft a question without a target bank, curriculum node, or tag. A draft can also be associated with a target bank, curriculum node, or tag from the start if the user is working in a specific bank context.

Bank-specific requirements should apply when the draft is submitted for review or published, not while the user is still drafting.

Submission readiness rules:

- unscoped drafts do not require a bank, curriculum node, or tag
- submitting to a curriculum-backed bank requires a proposed bank-local curriculum alignment
- publishing in a curriculum-backed bank requires a confirmed bank-local curriculum alignment
- submitting or publishing in a freeform bank does not require curriculum alignment
- freeform bank tags are required only if the bank owner has enabled that setting

Suggested model:

- `QuestionDraft`

`QuestionDraft` should record:

- based-on question version
- proposed stem, lead-in, options, explanations, citations, and option ordering mode
- submitted by
- reason or change summary
- linked report, optional
- review task
- state, such as draft, submitted, changes_requested, accepted, rejected, or forked

If accepted, the proposal should create a new immutable `QuestionVersion` and associated `QuestionContribution` records. If the proposed change alters the tested concept materially, reviewers should fork it into a new `Question` instead.

## Reuse and Updates Across Banks

Reuse should preserve the same shared `Question` and selected `QuestionVersion` by default.

When a bank reuses a question from another bank:

- content approval travels with the question version
- citations and citation support metadata travel with the question version
- the receiving bank still controls whether that approved version fits and should be published locally
- the receiving bank confirms local curriculum alignment or tags

When a report leads to a new approved version, other banks using the affected old version should receive an update notification or review task. They should not be silently updated.

The receiving bank can choose to:

- adopt the new version
- ignore it
- fork or edit it
- retire the entry

## Duplicate Detection

Reviewers should be shown likely duplicate or similar questions.

This should work within a bank and across banks where reuse is permitted by policy.

Duplicate detection is review support, not a hard uniqueness constraint. Similar questions may be legitimate if they test a different angle, use a different scenario, or are intentional variants.

Suggested model:

- `SimilarityMatch`

`SimilarityMatch` should record:

- candidate question version
- matched question version
- scope, such as same_bank, accessible_banks, or site_reusable
- score
- reason, such as stem similarity, lead-in similarity, answer similarity, or embedding similarity
- created at
- reviewer decision, such as reuse, fork, create_new_anyway, intentional_variant, or reject_duplicate

The review UI should show:

- similar question title or stem preview
- bank
- curriculum node or tags
- current published version
- similarity score
- actions such as view, reuse, mark intentional fork, or reject as duplicate

Duplicate detection should warn but not block publication, because intentional forks are valid.

## Import

Importing existing Minerva `QuestionSet` JSON should be part of v1.

Suggested flow:

1. Owner uploads a `QuestionSet` JSON file.
2. The app validates the file using the existing Minerva schema.
3. The app creates an import batch and checks each imported question for likely duplicates.
4. Existing curriculum node codes are mapped where possible.
5. The owner reviews an import summary with duplicate candidates.
6. For each imported question, the owner chooses whether to reuse an existing question/version, fork from an existing question, or create a new question.
7. The app creates or links the appropriate `Question`, `QuestionVersion`, and `QuestionContribution` records.
8. Imported questions enter the same review workflow as other sources.

This gives the web app a low-risk path to seed content before full web generation is complete.

## Learner Practice

Learners should practise within one bank at a time in v1.

Practice filters should include:

- curriculum node or tag
- unanswered
- incorrect
- updated since answered
- random or newest
- question count

Learner attempts should be tracked from v1.

`UserQuestionAttempt` should store:

- user
- question bank entry
- exact question version seen
- displayed option order
- selected option identity
- correct or incorrect result
- answered at
- time taken, optional

Attempts must refer to the immutable version shown to the learner.

Progress should roll up primarily by stable `Question`, while marking questions as updated if a newer version has been published since the learner last answered.

## Option Ordering

Some SBAs require fixed option ordering, such as dose ranges or severity scales.

`QuestionVersion` should declare an option ordering mode:

- `fixed`
- `randomizable`

The default should be `fixed`.

If reviewers mark a question as randomizable, attempts should still store the displayed option order.

## Deferred Features

The following are intentionally deferred:

- difficulty metadata
- spaced repetition
- cross-bank learner practice sessions
- full public request-to-reuse workflow
- two-person mandatory review
- full citation formatting system
- custom per-bank curriculum trees
- non-SBA question formats beyond image-based SBAs

## Implementation Open Questions

- What exact RCoA curriculum version labels should be attached to the existing curriculum data?
- What exact status, state, role, and qualifier vocabularies should be used before implementation? This includes contribution roles such as primary_author, original_source, reviewer, editor, importer, citation_verifier, and fork_author.
- What is the implementation plan for first Django delivery? This should cover the initial model set, permissions matrix, audit/event strategy, import mapping, generation integration, and background job approach.
- Should bank owners be able to delegate AI generation to reviewers in v1.1?
- How much source document management should live in the web app versus continuing to use the existing Minerva embedding pipeline?
- Should the first Django implementation live inside this repository or as a separate web project that depends on the Minerva package?
