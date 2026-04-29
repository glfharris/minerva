# Minerva
#### LLM-based Single Best Answer Question Generation

<video src="https://github.com/user-attachments/assets/513c38fd-46fd-4a18-b3aa-ada6381671a7" /></video>

## Rationale

High-quality question banks for postgraduate medical examinations are expensive, often charging significant sums for access — with little reduction in price for candidates who need to resit. Given the capabilities of modern LLMs, there is no good reason for this to remain the case.

Minerva generates Single Best Answer (SBA) questions from your own reference material using retrieval-augmented generation, with the aim of producing questions that meet the standard of those written by human examiners.

## Setup

Minerva uses `uv` as its package manager. Install it for your operating system before proceeding, then install dependencies:

```bash
uv sync
```

Copy `.env.example` to `.env` and fill in your API keys:

```
OPENAI_API_KEY=        # required if using OpenAI models
ANTHROPIC_API_KEY=     # required if using Anthropic/Claude models
MINERVA_MODEL=openai:gpt-4o
LANCEDB_DIR=./lancedb
```

Embeddings use `NeuML/pubmedbert-base-embeddings` locally — no API key required for embedding.

## Usage

**1. Embed your reference documents** (a folder of PDFs):

```bash
./mincli.py embed path/to/docs/
```

**2. Generate questions:**

```bash
# Single question
./mincli.py create "Lung Compliance"

# Multiple questions, saved to disk
./mincli.py create "Cardiac Output" --count 3 --output ./output

# With curriculum context (auto-matches the best curriculum node)
./mincli.py create "Rocuronium" --exam primary

# Using Anthropic Claude
./mincli.py create "Pharmacokinetics" --model anthropic:claude-opus-4-6
```

**3. Interactive quiz:**

```bash
# Quiz from a saved file
./mincli.py quiz output/cardiac_output_2026-04-29.json

# Generate then quiz in one step
./mincli.py quiz --topic "Lung Compliance" --exam primary --count 5
```

**4. Test retrieval** (useful for debugging):

```bash
# Check curriculum node matching for a topic
./mincli.py match "Rocuronium"
./mincli.py match "Rocuronium" --exam final

# Check what reference material would be retrieved
./mincli.py match "Rocuronium" --source docs
```

## Curriculum-aware generation

Minerva includes the full RCoA Primary and Final FRCA curriculum trees. When `--exam` is provided, it automatically matches the topic to the most relevant curriculum node using embedding similarity and includes the full curriculum breadcrumb in the prompt — helping the LLM target the right scope and depth for the exam standard.

## Models

Model strings use `provider:name` format:

| Provider | Example |
|---|---|
| OpenAI | `openai:gpt-4o` |
| Anthropic | `anthropic:claude-opus-4-6` |

Set the default via `MINERVA_MODEL` in `.env`, or override per-run with `--model`.

## Adapting to Other Fields

To use Minerva in another domain:
- Update the role prompt in `minerva/agent.py`
- Replace the few-shot examples in `examples/`
- Supply embeddings from relevant reference material
- Replace the curriculum JSON in `data/` with your own structure

## What's Next

Question quality is currently being validated against a set of human-written questions. Longer term, the goal is to make a freely accessible web platform that serves generated questions to anyone preparing for postgraduate exams.
