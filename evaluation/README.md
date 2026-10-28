# Evaluation

Measures how accurate the pipeline is by comparing its output with judgments a
person has labelled by hand.

## 1. Label judgments

Copy [`gold/_template.json`](gold/_template.json) to `gold/<case_id>.json`, put the PDF
at the `pdf` path, and fill in what the judgment actually says.

- **Leave a key out** → not labelled; the scorer skips it.
- **`null` or `[]`** → the judgment does not contain it; the pipeline should return nothing.

That distinction is how the scorer tells a correct "not found" from an invented value.
Only objective fields are labelled: court, bench, decision date, case number,
jurisdiction, judges, parties, cited statutes, evidence labels and timeline dates.
Free-text fields (facts, arguments) need human or LLM-judge review and are not scored.

## 2. Run

```bash
# Score predictions you already have (StructuredJudgment JSON per case,
# e.g. from `python -m pipeline.run x.pdf --out evaluation/predictions/<case_id>.json`)
python -m evaluation.run_eval

# Run the real pipeline on every labelled PDF first, then score (needs the Docker image)
docker compose run --rm app python -m evaluation.run_eval --run

# Try it on the bundled synthetic example (no dependencies beyond pydantic)
python -m evaluation.run_eval --gold evaluation/examples/gold \
  --predictions evaluation/examples/predictions --name example
```

Reports are written to `evaluation/reports/<name>.json` and `.md`. The API serves them
at `/api/eval/reports` and the UI shows them on the **Evaluation** page.

## 3. What the numbers mean

| Metric | Meaning |
|---|---|
| **Field accuracy** | Share of labelled single-value fields handled correctly, including correctly returning nothing. |
| **Wrong when answering** | Of the values the pipeline gave, the share that were wrong or invented. The pipeline is designed to keep this low. |
| **Abstention rate** | The judgment had the value but the pipeline returned nothing — the price of "None over guessing". |
| **Precision / recall / F1** | For list fields (judges, statutes, evidence labels, …), after one-to-one matching. |
| **Confidence calibration** | Mean accuracy per review decision, and the correlation between confidence and accuracy. If the confidence score works, auto-saved documents should score higher than ones sent to a person. |

Matching rules (all in [`metrics.py`](metrics.py)) ignore formatting but not content:
"Hon'ble Mr. Justice A. R. Menon" matches "A. R. Menon, J.", "Crl.A. 412/2018" matches
"Criminal Appeal No. 412 of 2018", "Ext. P-5" matches "Ex.P5".

The files in [`examples/`](examples/) are **synthetic** — made up to show how scoring
works. Reports built from them are flagged as synthetic and say nothing about real accuracy.
