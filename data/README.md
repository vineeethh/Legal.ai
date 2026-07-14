# Legal Knowledge Base — source data

This is the raw/processed source layer for the statute knowledge base used by
the Statute Agent's verification step. It is NOT read at runtime — an
ingestion script parses `raw/` into `processed/`, and only `processed/` gets
loaded into Postgres (source of truth) and Qdrant (embeddings).

## Layout

```
data/
  raw/<act>/          # official PDFs, one subfolder per act
  processed/           # one JSONL per act-version, produced by ingestion
```

## Sourcing rule

Only pull bare-act PDFs from an authoritative source — India Code
(indiacode.nic.in) or the e-Gazette. This KB verifies legal citations, so a
bad source document doesn't just degrade an answer, it produces false
VERIFIED/MISMATCH results for every judgment citing that section.

## Acts covered

| Folder          | Act                                          | Family                |
|-----------------|-----------------------------------------------|------------------------|
| `ipc/`          | Indian Penal Code, 1860                        | criminal_substantive   |
| `bns/`          | Bharatiya Nyaya Sanhita, 2023                  | criminal_substantive   |
| `crpc/`         | Code of Criminal Procedure, 1973               | criminal_procedural    |
| `bnss/`         | Bharatiya Nagarik Suraksha Sanhita, 2023       | criminal_procedural    |
| `evidence_act/` | Indian Evidence Act, 1872                      | evidence               |
| `bsa/`          | Bharatiya Sakshya Adhiniyam, 2023              | evidence               |
| `constitution/` | Constitution of India                          | constitutional         |

Old and new acts in each family coexist indefinitely — see
[docs/architecture/data_flow.md](../docs/architecture/data_flow.md). Nothing
here gets deleted when its successor act is added; pre-2024 judgments will
keep citing the old acts for decades under Article 20(1).

Raw PDFs are gitignored (`data/raw/**/*.pdf`); `data/processed/*.jsonl` is
committed since it's the small, reviewable artifact that ingestion produces.
