# Minerva
#### LLM-based Single Best Answer Question Generation

<video src="https://github.com/user-attachments/assets/513c38fd-46fd-4a18-b3aa-ada6381671a7" /></video>

## Rationale

I dislike exams, and I dislike having to fork out large sums of money for
question banks to support my revision for said exams.

The business model for these question banks is ridiculous, punishing people who
need to retake exams, while delivering a poor quality experience.

Given the tools available these days there is no need for them.

## Usage

Minerva relies on `uv` as its package manager, so please install that in the
normal fashion for your operating system first.

The environment variables `OPENAI_API_KEY` and `CHROMA_DB_DIR` must be set, the
simplest way to do this is to create a `.env` file in the directory, which the 
cli will read.

Then initialise your embeddings, at present this needs to be a folder of pdfs:

```
> ./mincli.py embed path/to/docs/folder
```

Then you're free to create questions as you see fit:

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

From a cursory look the OpenAI API cost per question is about $0.03 using
`gpt-4o` or $0.003 if using `gpt-4o-mini`.

## What's Next?

The code in this repository is pretty rough and ready so far, so needs a fair
bit of cleaning up. I'm in the process of validating the generated questions to
a similar standard as human-written questions. Longer term I'm planning on
creating a website that's free as in libre and as in beer, that can serve
questions to people who can make use of them.

## Application to other fields

Currently I have hardcoded a few variables specifically to target the primary 
FRCA anaesthetic examinations. However, by altering the role prompt in 
`minerva/llm.py`, changing the examples used, and suppling embeddings relevant
to your field, it's pretty trivial to apply these techniques to other fields.
