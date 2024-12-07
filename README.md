# Minerva
#### LLM-based Single Best Answer Question Generation

<video src="https://github.com/user-attachments/assets/513c38fd-46fd-4a18-b3aa-ada6381671a7" /></video>

## Rationale

## Usage

Minerva relies on `uv` as its package manager, so please install that in the normal fashion for your operating system first.

The environment variables `OPENAI_API_KEY` and `CHROMA_DB_DIR` must be set, the simplest way to do this is to create a `.env` file in the directory, which the cli will read.

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

## Application to other fields

Currently I have hardcoded a few variables specifically to target the primary FRCA anaesthetic examinations. However, by altering the role prompt in `minerva/llm.py`, changing the examples used, and suppling embeddings relevant to your field.
