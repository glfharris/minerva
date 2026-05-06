# TODO

## Before Starting The Website

These items prepare the current CLI/library code for a future question pool
website without starting the website implementation yet.

1. [x] Make website export a first-class CLI artifact
   - Add a command or flag that writes `WebsiteQuestionSetV1` JSON.
   - Keep legacy `QuestionSet` JSON output working.
   - Prove the website import contract from the CLI before Django exists.

2. [ ] Harden `WebsiteQuestionSetV1` validation
   - Cover required fields, stable option identity, source mode, per-question
     origin, fingerprints, and curriculum metadata.
   - Make bad imports fail predictably.

3. [x] Document fingerprint normalization
   - Document the hash algorithm and normalization rules.
   - Add tests that pin the documented rules.
   - Keep the website able to recompute hashes later.

4. [x] Return structured retrieval chunks
   - Let retrieval return text plus source metadata as structured values.
   - Format those chunks for agent prompts through an adapter.
   - Avoid parsing prompt strings to recover source/citation facts.

5. [ ] Populate source/citation export where safe
   - Use source manifest metadata and structured retrieval chunks.
   - Fill `WebsiteSourceV1` and `WebsiteCitationV1` where evidence is available.
   - Keep excerpts optional and conservative.

6. [ ] Add an artifact-writing seam
   - Save legacy JSON, Markdown, and website JSON through one output path.
   - Keep path handling and sidecar behaviour consistent.

7. [ ] Split dependencies into extras
   - Keep `minerva.website_export` importable without CLI/generation dependencies.
   - Separate lightweight base dependencies from CLI dependencies.
   - Leave room for a future web dependency set.

8. [ ] Create example website export fixtures
   - Generate realistic `examples/*website*.json` payloads.
   - Use them later as website import fixtures.

9. [ ] Add a schema/version migration note
   - Document website export schema version `1`.
   - State the stability promise and breaking-change policy.
   - Include a representative example payload.
