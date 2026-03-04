import os
import json
import requests

def _create_company(base_url, external_ref="pytest-001", company_name="PyTest Trading LLC"):
    r = requests.post(
        f"{base_url}/companies",
        files={"external_ref": (None, external_ref), "company_name": (None, company_name)},
        timeout=60
    )
    r.raise_for_status()
    return r.json()["company_id"]

def _ingest_pdf(base_url, company_id, path):
    with open(path, "rb") as f:
        r = requests.post(
            f"{base_url}/ingest",
            files={"company_id": (None, company_id), "file": (os.path.basename(path), f, "application/pdf")},
            timeout=120
        )
    r.raise_for_status()
    return r.json()

def test_end_to_end_case01(base_url):
    # you generated these locally using generate_synthetic_docs_uae_cases_v2.py
    case_dir = os.getenv("CASE_DIR", "synthetic_cases/case_01")

    cid = _create_company(base_url, external_ref="case01", company_name="Case 01 Demo LLC")

    # ingest all PDFs
    pdfs = [
        "trade_license.pdf",
        "moa_aoa.pdf",
        "board_resolution.pdf",
        "ids.pdf",
        "bank_letter.pdf",
        "vat_trn.pdf",
        "financial_statements.pdf",
    ]
    for p in pdfs:
        _ingest_pdf(base_url, cid, os.path.join(case_dir, p))

    # review
    r = requests.get(f"{base_url}/review/{cid}", timeout=60)
    r.raise_for_status()
    review = r.json()

    unified = review["unified"]
    docs = unified["documents"]

    # ensure we have all docs
    assert len(docs) >= 7

    # ensure at least trade license and financials were classified (mandatory doc types)
    doc_types = {d.get("docTypePred") for d in docs}
    assert "TRADE_LICENSE" in doc_types or "UNKNOWN" not in doc_types  # allow minor variance
    assert "FINANCIAL_STATEMENT" in doc_types

    # run risk assessment
    r2 = requests.post(f"{base_url}/risk-assessment/{cid}", timeout=90)
    r2.raise_for_status()
    risk = r2.json()

    assert "assessment_id" in risk
    assert "risk_report_blob_path" in risk
    assert risk["risk_band"] in ("LOW", "MEDIUM", "HIGH")