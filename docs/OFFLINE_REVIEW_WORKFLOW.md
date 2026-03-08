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
- `generated_at_utc`
- `provenance`
- `package_hash`
- per-file hashes and sizes

`package_hash` is computed from deterministic per-file hashes so reviewers can verify artifact integrity.
