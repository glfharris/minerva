# Future Website Ideas

This document keeps ideas that may matter later but are not part of the current v1 question pool website.

The v1 design is intentionally smaller: create questions through CLI import or simple manual authoring, review candidate versions, publish approved questions into one canonical pool, let learners practise, and let learners report issues.

## In-Website Generation

The first website should not run AI generation. Editors should generate or convert question sets using the Minerva CLI and import the resulting JSON.

Later versions may add:

- in-web generation
- generation permissions
- generation quotas
- token and cost tracking
- source document upload
- source document indexing and retrieval
- generation runs visible to reviewers

When this exists, generation metadata should still remain separate from citation support. Generation explains how a candidate was created; citations explain why the answer is supported.

## Advanced Authoring And Revision Drafts

V1 has simple manual authoring for complete text-only SBAs. It does not need long-lived drafts or advanced editing workflows.

Possible future features:

- save draft versions before review
- structured editor change proposals
- compare versions side by side
- fork a question from an existing version
- start from an existing `QuestionVersion` and save a replacement version

Any edit to learner-facing SBA content should still create a new immutable `QuestionVersion`.

## Question Forking

Forking is useful when a version no longer tests the same concept, answer logic, exam level, or curriculum intent.

Possible future rule:

- unreviewed versions may be moved to a different new `Question` before approval
- approved or rejected versions should not be moved between questions
- later forks should create a new version under a new `Question`

Forks should preserve lineage back to the source question and source version.

## Rich Contribution And Attribution

V1 can store minimal imported provenance. It does not need a full contribution model.

Future models:

- `QuestionContribution`
- `ContributorIdentity`

`ContributorIdentity` could represent:

- a site user
- an external person
- an organisation
- an external source or imported question set

`QuestionContribution` could record:

- question version
- contributor identity
- role, such as `original_author`, `original_source`, `editor`, `reviewer`, `fork_author`, `importer`, or `citation_verifier`
- contribution summary
- whether the contribution is learner-visible or internal only
- materiality, such as `minor_edit`, `material_revision`, `original_import`, `review`, or `fork`
- display order
- attributed time

Future learner-facing attribution might say: `Adapted from RCoA sample questions. Updated by Person A. Forked by Person B.`

## Independently Managed Banks And Collections

V1 has one canonical learner-facing pool. It does not need independently managed banks or collections.

Future banks or collections may support:

- institutional curation
- specialty sets
- private groups
- user-managed revision lists
- freeform collections without formal curricula

Possible model:

- `QuestionBank`
- `QuestionBankEntry`
- `BankMembership`

`BankMembership` could record:

- bank
- user
- role, such as `owner`, `reviewer`, or `learner`
- membership status, such as `active`, `invited`, `suspended`, or `left`
- invited by
- joined at

Future banks may have visibility settings:

- `private`: invited members only
- `unlisted`: accessible by link
- `public`: discoverable according to policy

## Contribution Policies

V1 has a fixed policy:

- editors import
- reviewers and editors review
- permitted editors or reviewers publish
- learners report issues
- structured proposed edits are not supported

Future banks may configure:

- who can report issues
- who can leave free-text suggestions
- who can submit structured edits
- who can submit new manual questions
- who can import generated or converted questions

## Discoverability And Reuse Policies

Cross-bank reuse is outside v1.

Future discoverability policies might include:

- `private`: not visible outside this bank
- `metadata_visible`: other reviewers can see limited metadata in duplicate or similarity search
- `content_visible`: other reviewers can inspect full published content where access allows

Future reuse policies might include:

- `private`: only this bank can reuse its questions
- `members_only`: bank members can reuse questions into their other banks
- `site_reusable`: any bank owner or reviewer can reuse published questions
- `request_required`: other banks can request reuse

Discoverability and reuse should remain separate. A bank might allow metadata-only duplicate search without allowing direct reuse.

## Update Propagation Across Banks

If cross-bank reuse exists later, a report or edit may produce a new approved version used by only some banks.

Other banks using an older version should receive an update notification or review task. They should not be silently updated.

Receiving banks could choose to:

- adopt the new version
- ignore it
- fork or edit it
- retire their entry

## Duplicate And Similarity Review

V1 may optionally warn on exact duplicates if cheap, but duplicate review should not block the import-review-publish loop.

Future model:

- `SimilarityMatch`

`SimilarityMatch` could record:

- candidate question version
- matched question version
- scope, such as `same_bank`, `accessible_banks`, or `site_reusable`
- score
- reason, such as stem similarity, lead-in similarity, answer similarity, or embedding similarity
- created at
- reviewer decision, such as `reuse`, `fork`, `create_new_anyway`, `intentional_variant`, or `reject_duplicate`

Duplicate detection should support review. It should not become a hard uniqueness constraint because intentional variants may be legitimate.

## Media And Other Question Formats

V1 supports text-only SBAs.

Future formats:

- image-based SBAs
- multi-select
- true/false
- EMQ
- short answer
- OSCE or viva prompts

Suggested image model:

- `QuestionMedia`

`QuestionMedia` could record:

- question version
- media type, initially image
- file reference
- caption, optional
- alt text
- source or contribution reference where relevant
- display order

Media should belong to `QuestionVersion` because changing the image can change the question.

## Freeform Collections And Tags

V1 practice is curriculum-backed.

Future freeform collections may not have a formal curriculum. They could use collection-scoped tags:

- tags are optional by default
- collection owners may require at least one tag
- category trees should be deferred unless tags prove insufficient

Freeform collections should not require curriculum alignment.

## Advanced Learning Features

Deferred learner features:

- difficulty metadata
- spaced repetition
- cross-bank learner practice
- richer progress analytics
- question quality analytics
- learner-facing attribution

## Audit Events

V1 stores durable state on the main domain objects.

A future append-only audit event log could record major transitions and metadata changes across:

- imports
- approvals
- rejections
- publication
- retirement
- report closure
- citation support changes
- curriculum alignment changes

This is useful but should not block the first implementation.
