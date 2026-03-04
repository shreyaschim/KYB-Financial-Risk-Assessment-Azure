# Synthetic UAE KYB Document Generator

Script: `generate_synthetic_docs_uae_cases.py`

## Purpose
Generates synthetic UAE-style KYB document packs (PDF) for testing/demo flows.

Each case includes:
- `trade_license.pdf`
- `moa_aoa.pdf`
- `board_resolution.pdf`
- `ids.pdf`
- `bank_letter.pdf`
- `vat_trn.pdf`
- `financial_statements.pdf`
- `manifest.json`

The script creates **10 predefined scenarios** (expired license, unaudited financials, net loss, TRN conflict, etc.) to simulate realistic compliance/risk patterns.

## Prerequisites
- Python 3.10+ (3.11 recommended)
- Python package: `reportlab`

Install dependency:
```bash
pip install reportlab
```

## How To Run
From repository root:
```bash
python SourceCode/scripts/generate_synthetic_docs_uae_cases.py
```

## Output Location
Output is written to:
```text
synthetic_cases/
```

Important: path is relative to your current working directory.  
If you run from repo root, output will be `./synthetic_cases/`.

## Notes
- Data is fully synthetic and non-PII.
- Script currently has fixed defaults (`n=10`, `seed=20260304`) and no CLI arguments.
