# Minerva
#### LLM-based Single Best Answer Question Generation

<video src="https://github.com/user-attachments/assets/513c38fd-46fd-4a18-b3aa-ada6381671a7" /></video>

## Rationale

High-quality question banks for postgraduate medical examinations are expensive, often charging significant sums for access — with little reduction in price for candidates who need to resit. Given the capabilities of modern LLMs, there is no good reason for this to remain the case.

Minerva generates Single Best Answer (SBA) questions from your own reference material using retrieval-augmented generation, with the aim of producing questions that meet the standard of those written by human examiners.

## Usage

Minerva uses `uv` as its package manager. Install it for your operating system before proceeding.

Two environment variables are required: `OPENAI_API_KEY` and `CHROMA_DB_DIR`. The simplest way to set these is with a `.env` file in the project directory, which the CLI will read automatically.

First, embed your reference documents (a folder of PDFs):

```
./mincli.py embed path/to/docs/folder
```

Then generate questions on any topic:

```
# ./mincli.py create "Lung Compliance"
──────────────────────────────── Question ────────────────────────────────
A 68-year-old woman with a history of chronic obstructive pulmonary
disease (COPD) presents with increasing shortness of breath. On
examination, she has a barrel-shaped chest and uses accessory muscles for
breathing.

Which of the following changes in lung compliance is most likely present
in this patient?

        > Increased lung compliance due to loss of elastic tissue.
        > Decreased lung compliance due to pulmonary fibrosis.
        > Normal lung compliance with increased airway resistance.
        > Decreased lung compliance due to fluid in the alveoli.
        > Increased lung compliance due to increased surface tension.

Correct: Increased lung compliance due to loss of elastic tissue.

In patients with COPD, particularly with emphysema, there is destruction
of lung elastic tissue leading to increased lung compliance. This results
in diminished elastic recoil and difficulty with passive exhalation, often
causing a barrel-shaped chest appearance.
```

The `--count` (`-c`) flag generates multiple questions in a single call. Approximate API costs using OpenAI are around $0.03 per question with `gpt-4o`, or $0.003 with `gpt-4o-mini`.

## Adapting to Other Fields

The current defaults target the primary FRCA anaesthetic examinations. To use Minerva in another domain, update the role prompt in `minerva/llm.py`, replace the few-shot examples in `examples/`, and supply embeddings from relevant reference material.

## What's Next

Question quality is currently being validated against a set of human-written questions. Longer term, the goal is to make a freely accessible web platform that serves generated questions to anyone preparing for postgraduate exams.
