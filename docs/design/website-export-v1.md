# Website Export V1

This note documents details of the `WebsiteQuestionSetV1` upload contract that
the future website should be able to validate independently.

## Content Fingerprints

`WebsiteContentFingerprintsV1.hash_algorithm` is:

```text
sha256-minerva-normalised-v1
```

The normalisation rule for every string part is:

1. Apply Python `str.casefold()`.
2. Split on all whitespace using `str.split()`.
3. Join the resulting words with a single ASCII space.

Hashes are SHA-256 hex digests. Each normalised string part is encoded as UTF-8
and followed by one NUL byte before the next part is added to the digest.

In pseudocode:

```python
from hashlib import sha256


def normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def fingerprint(*parts: str) -> str:
    digest = sha256()
    for part in parts:
        digest.update(normalise(part).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
```

The V1 fields are computed as follows:

- `content_hash`: title, stem, lead, overall explanation, then for each option
  in exported option order: option text, option explanation, and stringified
  correctness (`"True"` or `"False"` before normalisation).
- `stem_hash`: stem.
- `lead_hash`: lead.
- `option_set_hash`: option texts sorted by the normalised option text.
- `answer_hash`: correct option text.

`option_set_hash` deliberately ignores option order. `content_hash` deliberately
includes option order and per-option correctness.

Any breaking change to these rules requires a new `hash_algorithm` value and a
schema migration note.

