# Offline Review Workflow (v1)

Use this workflow to produce a stable, reviewable package for candidate policy promotion decisions.

## Inputs

- `comparison.json`
- `promotion.json`
- optional `segmented_comparison.json`
- optional `segmented_promotion.json`
- provenance (`policy_version`, `parameter_set_version`, `corpus_id`)

## Command

```bash
python3 scripts/offline_governance_report.py \
  --comparison /path/comparison.json \
  --promotion /path/promotion.json \
  --segmented-comparison /path/segmented_comparison.json \
  --segmented-promotion /path/segmented_promotion.json \
  --policy-version v1.2 \
  --parameter-set-version pset-1 \
  --corpus-id corpus-2026-03-08 \
  --package-out-dir /path/review-package
```

## Output package

The package directory contains canonical files:

- `comparison.json`
- `promotion.json`
- `segmented_comparison.json` (if provided)
- `segmented_promotion.json` (if provided)
- `report.json`
- `report.md`
- `manifest.json`

## Manifest

`manifest.json` includes:

- `review_package_schema_version`
- `review_workflow_version`
- `report_schema_version`
- `generated_at_utc`
- `provenance`
- `package_hash`
- per-file hashes and sizes

`package_hash` is computed from deterministic per-file hashes so reviewers can verify artifact integrity.

## Promotion authorization

Use `scripts/review_authorization.py` to record and validate promotion authorization:

```bash
python3 scripts/review_authorization.py decide \
  --manifest /path/review-package/manifest.json \
  --out /path/review-package/review_status.json \
  --status APPROVED \
  --reviewer-id reviewer@example.com \
  --rationale "Guardrails passed; progression improved in warm and engaged segments."
```

Check authorization (exit code `0` only when promotion is authorized):

```bash
python3 scripts/review_authorization.py check \
  --manifest /path/review-package/manifest.json \
  --review-status /path/review-package/review_status.json
```

Rules:

- Approval is bound to exact `package_hash`.
- `APPROVED`, `REJECTED`, and `SUPERSEDED` require rationale.
- Promotion is authorized only when status is `APPROVED` and hash matches.
