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
- five options
- correct option
- per-option explanations
- overall explanation
- option ordering mode
- citations
- source/provenance links
- content approval state

Published edits create a new `QuestionVersion`. Existing versions are preserved for reports, learner attempts, audit history, and comparison.

Content approval belongs to the `QuestionVersion`. Either the exact version is accurate, well supported, and suitable for publication, or it is not. That judgement should not vary by question bank. Bank-specific review decides whether an approved version belongs in that bank, not whether the content is intrinsically correct.

Content approval should record:

- approval status, such as unreviewed, approved, rejected, or superseded
- reviewer
- reviewed at
- completed proofing checklist
- evidence verification status
- review notes

Reviewers explicitly choose whether an edit is:

- a new version of the same question
- a fork into a new question

A change should remain a new version if it preserves the same learning objective, correct answer, reasoning pathway, and curriculum alignment. It should become a new question if it changes the tested concept, correct answer, exam level, curriculum alignment, or answer logic materially.

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
- approved version awaiting publication
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

### Curriculum-Backed Banks

A curriculum-backed question bank has a primary curriculum version.

Learners mainly see the bank-relevant curriculum path. For example, a Final FRCA bank should present Final FRCA alignment rather than cluttering the learner view with Primary FRCA or unrelated specialty alignments.

### Freeform Banks

Some banks may not have a formal curriculum. These should be allowed.

For v1, freeform banks should use bank-scoped tags as lightweight organisation:

- tags are optional by default
- bank owners can require at least one tag later if needed
- category trees should be deferred unless tags prove insufficient

### Global and Local Alignment

Question versions can have global curriculum alignments across multiple curricula.

Each question bank entry can also have a bank-local confirmed alignment.

Example:

One question about suxamethonium hyperkalaemia after burns may be globally aligned to both Primary FRCA pharmacology and Final FRCA burns/perioperative management. In a Final FRCA bank, the learner should mainly see the Final FRCA placement. In a Primary FRCA pharmacology bank, the learner should mainly see the pharmacology placement.

## Roles and Permissions

Initial roles:

- `Owner`: manages the bank, runs AI generation, configures settings, reviews, approves, and publishes.
- `Reviewer`: reviews submissions, edits, approves, rejects, forks, and publishes if granted by the bank.
- `Contributor`: writes or imports manual questions and submits them for review.
- `Learner`: practises published questions and submits reports or suggestions according to bank policy.

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

Suggested policies:

- `private`: only this bank can reuse its questions
- `members_only`: bank members can reuse questions into their other banks
- `site_reusable`: any bank owner or reviewer can reuse published questions
- `request_required`: other banks can request reuse

The default should be `site_reusable` for published questions.

## Review Workflow

All unpublished work should go through one unified review workflow with source labels.

Sources:

- `ai_generated`
- `manual`
- `imported`
- `proposed_edit`

Suggested states:

- `draft`
- `submitted`
- `in_review`
- `changes_requested`
- `approved`
- `published`
- `rejected`
- `retired`

Approval and publication should be separate actions, with an `approve and publish` shortcut.

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

## Evidence, Sources, and Citations

The website should store provenance for generated and manually submitted questions.

Suggested objects:

- `Source`
- `Evidence`
- `GenerationRun`

`Source` represents bibliographic or reference metadata:

- title
- source type, such as PDF, book, article, web page, manual, or curriculum
- author or publisher
- year
- URL, DOI, file reference, page, or section where available

`Evidence` attaches support to a `QuestionVersion`:

- source
- excerpt or retrieved chunk
- page, section, or URL anchor
- added by
- evidence type, such as retrieved, manual, or imported
- reviewer status, such as unverified, supports, or does not support

`GenerationRun` stores AI generation metadata:

- model
- prompt version
- topic
- bank and curriculum context if provided
- created by
- created at
- token usage or cost if available

Learners should see clean citations and source metadata so they know where to read more. They should not see the full prompt chain, critique history, retrieval scores, or internal AI-generation provenance.

Reviewers should see the full evidence and provenance needed to assess the question, including retrieved snippets and source excerpts.

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

Structured proposed edits should be supported as an optional enhancement to reports. A proposed edit should be based on a specific immutable question version and can be accepted by creating a new immutable version.

## Reuse and Updates Across Banks

Reuse should preserve the same shared `Question` and selected `QuestionVersion` by default.

When a bank reuses a question from another bank:

- content approval travels with the question version
- citations and verified evidence travel with the question version
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
3. The app creates draft `Question` and `QuestionVersion` records.
4. Existing curriculum node codes are mapped where possible.
5. The owner reviews an import summary.
6. Imported questions enter the same review workflow as other sources.

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
- selected option
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
- non-SBA question formats

## Open Questions

- What exact RCoA curriculum version labels should be attached to the existing curriculum data?
- Should reviewers have explicit review assignments in v1, or just a shared queue?
- Should bank owners be able to delegate AI generation to reviewers in v1.1?
- How much source document management should live in the web app versus continuing to use the existing Minerva embedding pipeline?
- Should the first Django implementation live inside this repository or as a separate web project that depends on the Minerva package?
