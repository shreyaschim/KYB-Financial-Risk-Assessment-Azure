from __future__ import annotations

import datetime as dt
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from app.db import Database, sha256_hex
from app.kv import get_secret
from app.storage import upload_bytes, upload_bytes_to, download_bytes


APP_VERSION = "demo-v1"
CONTAINER_EXTRACTED_TEXT = "extracted-text"
CONTAINER_EVIDENCE = "evidence-snippets"
CONTAINER_RISK_REPORTS = "risk-reports"

ATTESTATION_TEXT = (
    "I confirm that I have reviewed the extracted information, supporting documents, and risk indicators. "
    "I understand that submission constitutes an attestation for regulatory purposes."
)

MANDATORY_DOC_TYPES = {
    "TRADE_LICENSE",
    "FINANCIAL_STATEMENT",
}

DOC_TYPE_KEYWORDS = [
    ("TRADE_LICENSE", ["trade license", "licence", "license", "tl_"]),
    ("MOA_AOA", ["moa", "aoa", "memorandum", "articles of association"]),
    ("BOARD_RESOLUTION", ["board resolution", "resolution"]),
    ("ID", ["passport", "emirates id", "national id", "id_"]),
    ("BANK_LETTER", ["bank letter", "bank confirmation"]),
    ("VAT_TRN", ["vat", "trn"]),
    ("FINANCIAL_STATEMENT", ["balance sheet", "p&l", "profit", "loss", "financial", "statement"]),
]


app = FastAPI(title="Regulatory KYB API", version=APP_VERSION)
_db: Optional[Database] = None


def _now_utc_iso() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()


def _mask(s: str, keep: int = 4) -> str:
    if not s:
        return s
    if len(s) <= keep:
        return "*" * len(s)
    return "*" * (len(s) - keep) + s[-keep:]


def get_db() -> Database:
    global _db
    if _db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return _db


@app.on_event("startup")
def startup_init_db() -> None:
    global _db
    secret_name = os.getenv("SQL_SECRET_NAME")
    if not secret_name:
        raise RuntimeError("SQL_SECRET_NAME env var missing")

    conn_str = get_secret(secret_name)
    _db = Database(conn_str)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "utc": _now_utc_iso(), "version": APP_VERSION}


# ---------------------------
# Helper logic: classify/extract
# ---------------------------
def classify_document(file_name: str, text: str) -> Tuple[str, float]:
    hay = (file_name + "\n" + text).lower()
    for doc_type, kws in DOC_TYPE_KEYWORDS:
        for k in kws:
            if k in hay:
                return doc_type, 0.90
    return "UNKNOWN", 0.40


def detect_language(text: str) -> str:
    arabic_chars = re.search(r"[\u0600-\u06FF]", text)
    return "ar" if arabic_chars else "en"


def _parse_date_any(s: str) -> Optional[str]:
    s = s.strip()

    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}"

    m = re.search(r"\b(\d{2})[/-](\d{2})[/-](20\d{2})\b", s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}"

    return None


def extract_issue_expiry(text: str) -> Tuple[Optional[str], Optional[str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    issue = None
    expiry = None

    for ln in lines[:80]:
        low = ln.lower()
        if issue is None and ("issue" in low or "issued" in low):
            d = _parse_date_any(ln)
            if d:
                issue = d
        if expiry is None and ("expiry" in low or "expire" in low or "valid until" in low):
            d = _parse_date_any(ln)
            if d:
                expiry = d

    if issue and expiry:
        return issue, expiry

    hits: List[str] = []
    for ln in lines[:120]:
        d = _parse_date_any(ln)
        if d:
            hits.append(d)
        if len(hits) >= 2:
            break

    if issue is None and len(hits) >= 1:
        issue = hits[0]
    if expiry is None and len(hits) >= 2:
        expiry = hits[1]
    return issue, expiry


def extract_kv_fields(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for ln in text.splitlines():
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if not k or not v:
            continue
        out[k] = v
    return out


def snippet_hash(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def to_unified_json(
    company: Dict[str, Any],
    docs: List[Dict[str, Any]],
    fields: List[Dict[str, Any]],
    manual_edits: List[Dict[str, Any]],
    exceptions: List[Dict[str, Any]],
    latest_risk: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    current: Dict[str, Any] = {}
    for f in reversed(fields):
        current[f["field_path"]] = {
            "value": f["field_value"],
            "confidence": f.get("confidence"),
            "document_id": f.get("document_id"),
            "evidence_snippet": f.get("evidence_snippet"),
            "snippet_sha256": f.get("snippet_sha256"),
            "extraction_method": f.get("extraction_method"),
        }
    for e in reversed(manual_edits):
        current[e["field_path"]] = {
            "value": e["new_value"],
            "confidence": 1.0,
            "document_id": None,
            "evidence_snippet": None,
            "snippet_sha256": None,
            "extraction_method": "manual",
            "manual_edit_id": e["edit_id"],
        }

    def get_val(path: str) -> Optional[str]:
        item = current.get(path)
        return item["value"] if item else None

    missing_fields: List[str] = []
    for required_path in [
        "companyProfile.legalName",
        "companyProfile.registrationNumber",
        "licenseDetails.licenseNumber",
        "financialIndicators.latestFinancialPeriod",
    ]:
        if not get_val(required_path):
            missing_fields.append(required_path)

    risk_block = {
        "financialRiskScore": latest_risk["score"] if latest_risk else 0,
        "riskBand": latest_risk["overall_risk"] if latest_risk else "",
        "riskDrivers": (
            latest_risk["rationale"].split("; ")
            if latest_risk and latest_risk.get("rationale")
            else []
        ),
        "confidenceLevel": "LOW"
        if missing_fields
        else "MEDIUM"
        if (latest_risk and latest_risk["score"] < 75)
        else "HIGH",
    }

    return {
        "companyProfile": {
            "companyId": company["company_id"],
            "externalRef": company.get("external_ref"),
            "companyName": company.get("company_name"),
            "legalName": get_val("companyProfile.legalName"),
            "registrationNumber": get_val("companyProfile.registrationNumber"),
            "jurisdiction": get_val("companyProfile.jurisdiction"),
            "legalForm": get_val("companyProfile.legalForm"),
        },
        "licenseDetails": {
            "licenseNumber": get_val("licenseDetails.licenseNumber"),
            "issuingAuthority": get_val("licenseDetails.issuingAuthority"),
            "issueDate": get_val("licenseDetails.issueDate"),
            "expiryDate": get_val("licenseDetails.expiryDate"),
        },
        "addresses": {
            "registeredAddress": get_val("addresses.registeredAddress"),
        },
        "shareholders": [],
        "ubos": [],
        "documents": [
            {
                "documentId": d["document_id"],
                "fileName": d["file_name"],
                "blobPath": d["blob_path"],
                "docTypePred": d.get("doc_type_pred"),
                "docTypeConfidence": float(d["doc_type_confidence"])
                if d.get("doc_type_confidence") is not None
                else None,
                "language": d.get("language"),
                "issueDate": str(d["issue_date"]) if d.get("issue_date") else None,
                "expiryDate": str(d["expiry_date"]) if d.get("expiry_date") else None,
                "extractedTextBlobPath": d.get("extracted_text_blob_path"),
                "createdUtc": str(d.get("created_utc")),
            }
            for d in docs
        ],
        "signatories": [],
        "financialIndicators": {
            "latestFinancialPeriod": get_val("financialIndicators.latestFinancialPeriod"),
            "revenue": get_val("financialIndicators.revenue"),
            "netProfitLoss": get_val("financialIndicators.netProfitLoss"),
            "totalAssets": get_val("financialIndicators.totalAssets"),
            "totalLiabilities": get_val("financialIndicators.totalLiabilities"),
            "auditStatus": get_val("financialIndicators.auditStatus"),
        },
        "riskAssessment": risk_block,
        "complianceIndicators": {
            "exceptionsOpen": len([e for e in exceptions if e.get("status") == "OPEN"]),
        },
        "missingFields": missing_fields,
        "_meta": {
            "version": APP_VERSION,
            "generatedUtc": _now_utc_iso(),
            "manualEditsCount": len(manual_edits),
        },
    }


def compute_financial_risk(
    unified: Dict[str, Any], docs: List[Dict[str, Any]], exceptions: List[Dict[str, Any]]
) -> Tuple[int, str, List[str], str]:
    score = 100
    drivers: List[str] = []

    fin = unified.get("financialIndicators", {})
    audit_status = (fin.get("auditStatus") or "unknown").strip().lower()

    def parse_money(x: Any) -> Optional[float]:
        if x is None:
            return None
        s = str(x).replace(",", "").strip()
        m = re.search(r"-?\d+(\.\d+)?", s)
        return float(m.group(0)) if m else None

    revenue = parse_money(fin.get("revenue"))
    net = parse_money(fin.get("netProfitLoss"))
    assets = parse_money(fin.get("totalAssets"))
    liab = parse_money(fin.get("totalLiabilities"))
    period = fin.get("latestFinancialPeriod")

    if not period:
        score -= 25
        drivers.append("Missing latest financial period (conservative default)")
    if revenue is None:
        score -= 10
        drivers.append("Missing revenue")
    if net is None:
        score -= 15
        drivers.append("Missing net profit/loss")
    if assets is None or liab is None:
        score -= 20
        drivers.append("Missing assets/liabilities")

    if net is not None and net < 0:
        score -= 25
        drivers.append("Net losses / negative profitability")

    if assets is not None and liab is not None and liab > assets:
        score -= 30
        drivers.append("Liabilities exceed assets")

    if audit_status in ("unaudited", "unknown"):
        score -= 10
        drivers.append(f"Audit status is {audit_status}")

    doc_types = {d.get("doc_type_pred") for d in docs if d.get("doc_type_pred")}
    missing = sorted(list(MANDATORY_DOC_TYPES - doc_types))
    if missing:
        score -= 25
        drivers.append(f"Missing mandatory documents: {', '.join(missing)}")

    if any(
        (e.get("severity") or "").upper() == "HIGH" and e.get("status") == "OPEN"
        for e in exceptions
    ):
        score -= 15
        drivers.append("High severity exception(s) open")

    score = max(0, min(100, score))
    band = "HIGH" if score < 50 else "MEDIUM" if score < 75 else "LOW"

    confidence = (
        "LOW"
        if len(unified.get("missingFields", [])) >= 2
        else "MEDIUM"
        if missing
        else "HIGH"
    )
    return score, band, drivers, confidence


# ---------------------------
# APIs
# ---------------------------

@app.post("/companies")
def create_company(
    external_ref: str = Form(...),
    company_name: str = Form(...),
) -> Dict[str, Any]:
    db = get_db()
    correlation_id = str(uuid.uuid4())

    company_id = db.create_company(external_ref=external_ref, company_name=company_name)
    db.insert_audit_event(
        correlation_id,
        company_id,
        "COMPANY_CREATED",
        "system",
        f"external_ref={_mask(external_ref)}",
    )
    return {"company_id": company_id, "correlation_id": correlation_id}


@app.post("/ingest")
async def ingest(
    company_id: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    db = get_db()
    correlation_id = str(uuid.uuid4())

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # 1) Upload RAW document to STORAGE_CONTAINER (raw-documents)
    raw_blob_path = f"{company_id}/{uuid.uuid4()}_{file.filename}"
    upload_bytes(raw_blob_path, content, file.content_type or "application/octet-stream")
    db.insert_audit_event(
        correlation_id, company_id, "DOCUMENT_UPLOADED", "system", f"blob_path={raw_blob_path}"
    )

    # 2) Create document row
    file_hash = sha256_hex(content)
    document_id = db.create_document(company_id, file.filename, raw_blob_path, file_hash)

    # 3) Extract text (supports PDFs via pypdf)
    text = ""
    ct = (file.content_type or "").lower()
    name = file.filename.lower()

    if ct.startswith("text/") or name.endswith((".txt", ".csv", ".json")):
        text = content.decode("utf-8", errors="ignore")

    elif name.endswith(".pdf") or ct == "application/pdf":
        try:
            import io
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            text = "\n".join([(p.extract_text() or "") for p in reader.pages]).strip()
            if not text:
                raise ValueError("empty_pdf_text")
        except Exception:
            text = "BINARY_DOCUMENT: pdf text extraction failed in demo."
            db.insert_exception(
                company_id, document_id, "TEXT_EXTRACTION_FAILED", "MEDIUM", "PDF text extraction failed"
            )

    else:
        text = "BINARY_DOCUMENT: text extraction skipped in demo."
        db.insert_exception(
            company_id, document_id, "TEXT_EXTRACTION_SKIPPED", "LOW", "Binary document; no OCR in demo"
        )

    # 4) Classify + metadata
    doc_type, conf = classify_document(file.filename, text)
    lang = detect_language(text)
    issue, expiry = extract_issue_expiry(text)
    db.update_document_metadata(document_id, doc_type, conf, lang, issue, expiry)
    db.insert_audit_event(
        correlation_id, company_id, "DOCUMENT_CLASSIFIED", "system", f"type={doc_type},conf={conf}"
    )

    # expiry exception
    if expiry:
        try:
            exp_date = dt.date.fromisoformat(expiry)
            if exp_date < dt.date.today():
                db.insert_exception(
                    company_id, document_id, "DOCUMENT_EXPIRED", "HIGH", f"Document expired on {expiry}"
                )
        except Exception:
            pass

    # low confidence exception
    if conf < 0.60:
        db.insert_exception(
            company_id, document_id, "LOW_CLASSIFICATION_CONFIDENCE", "MEDIUM", f"Confidence={conf}"
        )

    # 5) Store extracted full text in extracted-text container
    extracted_text_blob_path = f"{company_id}/{document_id}.txt"
    upload_bytes_to(
        CONTAINER_EXTRACTED_TEXT,
        extracted_text_blob_path,
        text.encode("utf-8"),
        "text/plain",
    )
    db.update_document_extracted_text_blob_path(document_id, extracted_text_blob_path)
    db.mark_document_extracted(document_id)

    # 6) Extract fields (demo: Key: Value lines + aliases)
    kv = extract_kv_fields(text)
    mapped: List[Dict[str, Any]] = []

    def add_field(
        path: str,
        value: Optional[str],
        confidence: float,
        snippet: str,
        method: str = "regex",
    ) -> None:
        if value is None:
            return
        snip = snippet.strip()[:500]
        sh = snippet_hash(snip)
        evidence_blob_path = f"{company_id}/{document_id}/{path.replace('.', '_')}_{sh}.txt"
        upload_bytes_to(CONTAINER_EVIDENCE, evidence_blob_path, snip.encode("utf-8"), "text/plain")

        mapped.append(
            {
                "field_path": path,
                "field_value": value,
                "confidence": confidence,
                "evidence_snippet": snip,
                "snippet_sha256": sh,
                "extraction_method": method,
            }
        )

    add_field(
        "companyProfile.legalName",
        kv.get("legal name") or kv.get("company legal name"),
        0.80,
        f"legal name: {kv.get('legal name') or kv.get('company legal name')}",
    )
    add_field(
        "companyProfile.registrationNumber",
        kv.get("registration number") or kv.get("cr number"),
        0.80,
        f"registration number: {kv.get('registration number') or kv.get('cr number')}",
    )
    add_field("companyProfile.jurisdiction", kv.get("jurisdiction"), 0.70, f"jurisdiction: {kv.get('jurisdiction')}")
    add_field("companyProfile.legalForm", kv.get("legal form"), 0.70, f"legal form: {kv.get('legal form')}")

    add_field(
        "licenseDetails.licenseNumber",
        kv.get("license number") or kv.get("licence number"),
        0.80,
        f"license number: {kv.get('license number') or kv.get('licence number')}",
    )
    add_field(
        "licenseDetails.issuingAuthority",
        kv.get("issuing authority") or kv.get("license issuing authority"),
        0.70,
        f"issuing authority: {kv.get('issuing authority') or kv.get('license issuing authority')}",
    )
    if issue:
        add_field("licenseDetails.issueDate", issue, 0.75, f"issue date: {issue}")
    if expiry:
        add_field("licenseDetails.expiryDate", expiry, 0.75, f"expiry date: {expiry}")

    add_field(
        "addresses.registeredAddress",
        kv.get("registered address") or kv.get("address"),
        0.65,
        f"registered address: {kv.get('registered address') or kv.get('address')}",
    )

    add_field(
        "financialIndicators.latestFinancialPeriod",
        kv.get("latest financial period") or kv.get("period"),
        0.70,
        f"period: {kv.get('latest financial period') or kv.get('period')}",
    )
    add_field("financialIndicators.revenue", kv.get("revenue"), 0.65, f"revenue: {kv.get('revenue')}")
    add_field(
        "financialIndicators.netProfitLoss",
        kv.get("net profit") or kv.get("net loss") or kv.get("net profit/loss"),
        0.65,
        f"net: {kv.get('net profit') or kv.get('net loss') or kv.get('net profit/loss')}",
    )
    add_field(
        "financialIndicators.totalAssets",
        kv.get("total assets") or kv.get("assets"),
        0.65,
        f"assets: {kv.get('total assets') or kv.get('assets')}",
    )
    add_field(
        "financialIndicators.totalLiabilities",
        kv.get("total liabilities") or kv.get("liabilities"),
        0.65,
        f"liabilities: {kv.get('total liabilities') or kv.get('liabilities')}",
    )
    add_field(
        "financialIndicators.auditStatus",
        kv.get("audit status") or kv.get("audited"),
        0.60,
        f"audit status: {kv.get('audit status') or kv.get('audited')}",
    )

    if mapped:
        db.insert_extracted_fields(company_id, document_id, mapped)
        db.insert_audit_event(
            correlation_id, company_id, "FIELDS_EXTRACTED", "system", f"count={len(mapped)}"
        )
    else:
        db.insert_exception(
            company_id, document_id, "NO_FIELDS_EXTRACTED", "MEDIUM", "No key-value fields detected in document"
        )

    # 7) Missing mandatory docs check at ingestion time
    docs = db.list_documents_for_company(company_id)
    doc_types = {d.get("doc_type_pred") for d in docs if d.get("doc_type_pred")}
    missing = sorted(list(MANDATORY_DOC_TYPES - doc_types))
    if missing:
        db.insert_exception(
            company_id, None, "MISSING_MANDATORY_DOCS", "HIGH", f"Missing: {', '.join(missing)}"
        )

    return {
        "status": "ok",
        "company_id": company_id,
        "document_id": document_id,
        "correlation_id": correlation_id,
    }


@app.post("/ingest/bulk")
async def ingest_bulk(
    company_id: str = Form(...),
    files: List[UploadFile] = File(...)
) -> Dict[str, Any]:

    results = []

    for file in files:
        try:
            result = await ingest(company_id=company_id, file=file)
            results.append({
                "file_name": file.filename,
                "status": "success",
                "document_id": result["document_id"]
            })
        except Exception as e:
            results.append({
                "file_name": file.filename,
                "status": "failed",
                "error": str(e)
            })

    return {
        "company_id": company_id,
        "total_files": len(files),
        "results": results
    }


@app.get("/review/{company_id}")
def review(company_id: str) -> Dict[str, Any]:
    db = get_db()
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    docs = db.list_documents_for_company(company_id)
    fields = db.list_extracted_fields(company_id)
    manual_edits = db.list_manual_edits(company_id)
    exceptions = db.list_exceptions(company_id)
    latest_risk = db.get_latest_risk_assessment(company_id)

    unified = to_unified_json(company, docs, fields, manual_edits, exceptions, latest_risk)
    return {
        "unified": unified,
        "exceptions": exceptions,
        "manualEdits": manual_edits,
        "latestRiskAssessment": latest_risk,
    }


@app.post("/review/edit")
def review_edit(
    company_id: str = Form(...),
    field_path: str = Form(...),
    new_value: str = Form(...),
    reason: str = Form(...),
    reviewer: str = Form(...),
    old_value: Optional[str] = Form(None),
) -> Dict[str, Any]:
    db = get_db()
    correlation_id = str(uuid.uuid4())

    edit_id = db.insert_manual_edit(company_id, field_path, old_value, new_value, reason, reviewer)
    db.insert_audit_event(
        correlation_id, company_id, "MANUAL_EDIT_APPLIED", reviewer, f"path={field_path},reason={reason}"
    )
    return {"status": "ok", "edit_id": edit_id, "correlation_id": correlation_id}


@app.post("/review/confirm")
def review_confirm(
    company_id: str = Form(...),
    reviewer: str = Form(...),
) -> Dict[str, Any]:
    db = get_db()
    correlation_id = str(uuid.uuid4())
    db.insert_audit_event(correlation_id, company_id, "HUMAN_REVIEW_COMPLETED", reviewer, ATTESTATION_TEXT)
    return {
        "status": "review_finalized",
        "attestation": ATTESTATION_TEXT,
        "utc": _now_utc_iso(),
        "correlation_id": correlation_id,
    }


@app.post("/risk-assessment/{company_id}")
def risk_assessment(company_id: str) -> Dict[str, Any]:
    db = get_db()
    correlation_id = str(uuid.uuid4())

    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    docs = db.list_documents_for_company(company_id)
    fields = db.list_extracted_fields(company_id)
    manual_edits = db.list_manual_edits(company_id)
    exceptions = db.list_exceptions(company_id)
    latest_risk = db.get_latest_risk_assessment(company_id)

    unified = to_unified_json(company, docs, fields, manual_edits, exceptions, latest_risk)

    score, band, drivers, confidence = compute_financial_risk(unified, docs, exceptions)
    rationale = "; ".join(drivers) if drivers else "No major risk factors detected"

    assessment_id = db.insert_risk_assessment(
        company_id=company_id,
        overall_risk=band,
        score=score,
        rationale=rationale,
        model_version=APP_VERSION,
    )

    db.insert_audit_event(correlation_id, company_id, "RISK_COMPUTED", "system", f"score={score},band={band}")

    unified["riskAssessment"]["financialRiskScore"] = score
    unified["riskAssessment"]["riskBand"] = band
    unified["riskAssessment"]["riskDrivers"] = drivers
    unified["riskAssessment"]["confidenceLevel"] = confidence

    report = {
        "companyId": company_id,
        "assessmentId": assessment_id,
        "generatedUtc": _now_utc_iso(),
        "report": unified,
    }

    report_blob_path = f"{company_id}/{assessment_id}.json"
    upload_bytes_to(
        CONTAINER_RISK_REPORTS,
        report_blob_path,
        json.dumps(report, indent=2).encode("utf-8"),
        "application/json",
    )

    return {
        "company_id": company_id,
        "assessment_id": assessment_id,
        "score": score,
        "risk_band": band,
        "risk_drivers": drivers,
        "confidence_level": confidence,
        "risk_report_blob_path": report_blob_path,
        "correlation_id": correlation_id,
    }


@app.get("/documents/{document_id}/view")
def view_document(document_id: str):
    """Inline (read-only) document viewer endpoint used by the Review UI."""
    db = get_db()
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    data, content_type = download_bytes(doc["blob_path"])
    headers = {
        "Content-Disposition": f'inline; filename="{doc["file_name"]}"',
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=data, media_type=content_type or "application/pdf", headers=headers)

@app.get("/ui/review/{company_id}", response_class=HTMLResponse)
def ui_review(company_id: str):
    """
    Minimal Review & Confirm UI (Human-in-the-loop) to satisfy assignment Point #6.
    Notes:
    - "No screenshot/download" cannot be guaranteed in a web browser; this UI is read-only and uses inline rendering.
    - Uses existing APIs: /review, /risk-assessment, /review/edit, /review/confirm, and /documents/{document_id}/view
    """
    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>KYB Review - {company_id}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
    .row {{ display:flex; gap:12px; flex-wrap: wrap; }}
    .col {{ flex:1; min-width: 280px; }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 8px; text-align:left; vertical-align: top; }}
    th {{ background: #fafafa; }}
    .badge {{ display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
    .auto {{ background: #eef6ff; color:#1b66c9; }}
    .manual {{ background: #fff2e6; color:#b45309; }}
    .danger {{ background:#fee2e2; color:#b91c1c; }}
    .btn {{ padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; background: #fff; cursor:pointer; }}
    .btn-primary {{ background: #111827; color: #fff; border-color:#111827; }}
    input[type="text"] {{ width:100%; padding: 8px; border: 1px solid #ddd; border-radius: 8px; }}
    small {{ color:#666; }}
    code {{ background:#f6f6f6; padding:2px 6px; border-radius:6px; }}
    .muted {{ color:#6b7280; }}
  </style>
</head>
<body>
  <h2>KYB Review & Confirm</h2>

  <div class="card">
    <div><b>Company ID:</b> <code>{company_id}</code></div>
    <div style="margin-top:8px;">
      <button class="btn" onclick="loadAll()">Reload</button>
      <button class="btn btn-primary" onclick="computeRisk()">Compute Risk Now</button>
    </div>
    <div id="status" style="margin-top:10px;"></div>
  </div>

  <div class="row">
    <div class="card col">
      <h3>Risk Summary</h3>
      <div><b>Score:</b> <span id="riskScore">-</span></div>
      <div><b>Band:</b> <span id="riskBand">-</span></div>
      <div style="margin-top:8px;"><b>Drivers</b></div>
      <ul id="riskDrivers"></ul>
      <small class="muted">Computed via <code>POST /risk-assessment/{company_id}</code></small>
    </div>

    <div class="card col">
      <h3>Exceptions</h3>
      <ul id="exceptions"></ul>
      <small class="muted">From <code>GET /review/{company_id}</code></small>
    </div>
  </div>

  <div class="card">
    <h3>Supporting Documents</h3>
    <table>
      <thead><tr><th>File</th><th>Type</th><th>Confidence</th><th>View</th></tr></thead>
      <tbody id="docs"></tbody>
    </table>
  </div>

  <div class="card">
    <h3>Extracted Data (System vs Human Edits)</h3>
    <p><small class="muted">
      Fields below show system-extracted values. If a field has been manually edited, it will show a <span class="badge manual">Human edit</span>.
    </small></p>
    <table>
      <thead><tr><th>Field</th><th>Current Value</th><th>Update</th><th>Provenance</th></tr></thead>
      <tbody id="fields"></tbody>
    </table>
  </div>

  <div class="card">
    <h3>Review & Confirm (Human-in-the-Loop)</h3>
    <p><b>Confirmation statement:</b></p>
    <p style="border-left:4px solid #111827; padding-left:12px;">
      “I confirm that I have reviewed the extracted information, supporting documents, and
      risk indicators. I understand that submission constitutes an attestation for regulatory
      purposes.”
    </p>
    <div style="margin-top:10px;">
      <input id="reviewer" type="text" placeholder="Reviewer name (required)"/>
    </div>
    <div style="margin-top:10px;">
      <button class="btn btn-primary" onclick="confirmReview()">Confirm & Attest</button>
    </div>
    <div id="confirmResult" style="margin-top:10px;"></div>
  </div>

  <!-- Document viewer modal -->
  <div id="docModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.6);">
    <div style="position:absolute; top:5%; left:5%; right:5%; bottom:5%; background:#fff; border-radius:12px; overflow:hidden;">
      <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; border-bottom:1px solid #eee;">
        <b id="docTitle">Document</b>
        <button class="btn" onclick="closeDoc()">✕</button>
      </div>
      <iframe id="docFrame" style="width:100%; height:calc(100% - 52px); border:0;"></iframe>
    </div>
  </div>

<script>
const BASE = window.location.origin;
const CID = "{company_id}";

const FIELD_LABELS = {{
  "companyProfile.legalName": "Legal Name",
  "companyProfile.registrationNumber": "Commercial Registration (CR)",
  "companyProfile.jurisdiction": "Jurisdiction",
  "companyProfile.legalForm": "Legal Form",
  "licenseDetails.licenseNumber": "Trade License Number",
  "licenseDetails.issuingAuthority": "Issuing Authority",
  "licenseDetails.issueDate": "License Issue Date",
  "licenseDetails.expiryDate": "License Expiry Date",
  "addresses.registeredAddress": "Registered Address",
  "financialIndicators.latestFinancialPeriod": "Financial Period",
  "financialIndicators.revenue": "Revenue (AED)",
  "financialIndicators.netProfitLoss": "Net Profit/Loss (AED)",
  "financialIndicators.totalAssets": "Total Assets (AED)",
  "financialIndicators.totalLiabilities": "Total Liabilities (AED)",
  "financialIndicators.auditStatus": "Audit Status"
}};

function setStatus(msg) {{
  document.getElementById("status").innerHTML = msg;
}}

function openDoc(docId, fileName) {{
  document.getElementById("docTitle").innerText = fileName || "Document";
  document.getElementById("docFrame").src = `${{BASE}}/documents/${{docId}}/view`;
  document.getElementById("docModal").style.display = "block";
}}

function closeDoc() {{
  document.getElementById("docFrame").src = "about:blank";
  document.getElementById("docModal").style.display = "none";
}}

document.addEventListener("contextmenu", e => e.preventDefault());

async function loadAll() {{
  setStatus("Loading review data...");
  const r = await fetch(`${{BASE}}/review/${{CID}}`);
  if (!r.ok) {{
    setStatus(`<span class="badge danger">Error</span> Failed to load review: ${{r.status}}`);
    return;
  }}
  const data = await r.json();

  renderRiskFromUnified(data.unified);
  renderExceptions(data.exceptions || []);
  renderDocs((data.unified && data.unified.documents) ? data.unified.documents : []);
  renderFields(data);
  setStatus(`<span class="badge auto">OK</span> Loaded at ${{new Date().toLocaleString()}}`);
}}

function renderRiskFromUnified(unified) {{
  const ra = (unified && unified.riskAssessment) ? unified.riskAssessment : null;
  document.getElementById("riskScore").innerText = ra ? (ra.financialRiskScore ?? "-") : "-";
  document.getElementById("riskBand").innerText = ra ? (ra.riskBand ?? "-") : "-";
  const ul = document.getElementById("riskDrivers");
  ul.innerHTML = "";
  (ra && ra.riskDrivers ? ra.riskDrivers : []).forEach(d => {{
    const li = document.createElement("li");
    li.innerText = d;
    ul.appendChild(li);
  }});
}}

function renderExceptions(excs) {{
  const ul = document.getElementById("exceptions");
  ul.innerHTML = "";
  if (!excs.length) {{
    ul.innerHTML = "<li>No exceptions</li>";
    return;
  }}
  excs.forEach(e => {{
    const li = document.createElement("li");
    li.innerText = `${{e.severity}} | ${{e.exception_type}} | ${{e.message}}`;
    ul.appendChild(li);
  }});
}}

function renderDocs(docs) {{
  const tbody = document.getElementById("docs");
  tbody.innerHTML = "";
  docs.forEach(d => {{
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${{d.fileName}}</td>
      <td>${{d.docTypePred}}</td>
      <td>${{d.docTypeConfidence}}</td>
      <td><button class="btn" onclick="openDoc('${{d.documentId}}', '${{d.fileName}}')">View</button></td>
    `;
    tbody.appendChild(tr);
  }});
}}

function flattenUnified(unified) {{
  return [
    ["companyProfile.legalName", unified?.companyProfile?.legalName],
    ["companyProfile.registrationNumber", unified?.companyProfile?.registrationNumber],
    ["companyProfile.jurisdiction", unified?.companyProfile?.jurisdiction],
    ["companyProfile.legalForm", unified?.companyProfile?.legalForm],

    ["licenseDetails.licenseNumber", unified?.licenseDetails?.licenseNumber],
    ["licenseDetails.issuingAuthority", unified?.licenseDetails?.issuingAuthority],
    ["licenseDetails.issueDate", unified?.licenseDetails?.issueDate],
    ["licenseDetails.expiryDate", unified?.licenseDetails?.expiryDate],

    ["addresses.registeredAddress", unified?.addresses?.registeredAddress],

    ["financialIndicators.latestFinancialPeriod", unified?.financialIndicators?.latestFinancialPeriod],
    ["financialIndicators.revenue", unified?.financialIndicators?.revenue],
    ["financialIndicators.netProfitLoss", unified?.financialIndicators?.netProfitLoss],
    ["financialIndicators.totalAssets", unified?.financialIndicators?.totalAssets],
    ["financialIndicators.totalLiabilities", unified?.financialIndicators?.totalLiabilities],
    ["financialIndicators.auditStatus", unified?.financialIndicators?.auditStatus],
  ];
}}

function renderFields(reviewPayload) {{
  const unified = reviewPayload.unified;
  const manualEdits = reviewPayload.manualEdits || [];

  const manualMap = {{}};
  manualEdits.forEach(me => {{
    manualMap[me.field_path] = me;
  }});

  const tbody = document.getElementById("fields");
  tbody.innerHTML = "";

  const rows = flattenUnified(unified);
  rows.forEach(([path, val]) => {{
    const label = FIELD_LABELS[path] || path;
    const me = manualMap[path];

    const badge = me ? `<span class="badge manual">Human edit</span>` : `<span class="badge auto">System</span>`;
    const provenance = me ? `Updated by ${{me.reviewer}} (reason: ${{me.reason}})` : `System extracted`;
    const curVal = (val === null || val === undefined) ? "" : String(val);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${{label}}</td>
      <td>${{curVal}} ${{badge}}</td>
      <td>
        <input type="text" id="edit_${{path.replaceAll('.','_')}}" value="${{curVal}}"/>
        <div style="margin-top:6px;">
          <button class="btn" onclick="saveEdit('${{path}}')">Save</button>
        </div>
      </td>
      <td><small class="muted">${{provenance}}</small></td>
    `;
    tbody.appendChild(tr);
  }});
}}

async function saveEdit(path) {{
  const v = document.getElementById("edit_" + path.replaceAll(".","_")).value;
  const reviewer = prompt("Reviewer name:");
  if (!reviewer) return alert("Reviewer required");
  const reason = prompt("Reason for change:");
  if (!reason) return alert("Reason required");

  const form = new FormData();
  form.append("company_id", CID);
  form.append("field_path", path);
  form.append("new_value", v);
  form.append("reason", reason);
  form.append("reviewer", reviewer);

  const r = await fetch(`${{BASE}}/review/edit`, {{ method: "POST", body: form }});
  if (!r.ok) {{
    alert("Edit failed: " + r.status);
    return;
  }}
  await loadAll();
  alert("Saved");
}}

async function computeRisk() {{
  setStatus("Computing risk...");
  const r = await fetch(`${{BASE}}/risk-assessment/${{CID}}`, {{ method: "POST" }});
  if (!r.ok) {{
    setStatus(`<span class="badge danger">Error</span> Risk computation failed: ${{r.status}}`);
    return;
  }}
  const data = await r.json();
  await loadAll();
  setStatus(`<span class="badge auto">OK</span> Risk computed (assessment_id=${{data.assessment_id}})`);
}}

async function confirmReview() {{
  const reviewer = document.getElementById("reviewer").value.trim();
  if (!reviewer) {{
    alert("Reviewer name required");
    return;
  }}
  const form = new FormData();
  form.append("company_id", CID);
  form.append("reviewer", reviewer);

  const r = await fetch(`${{BASE}}/review/confirm`, {{ method: "POST", body: form }});
  if (!r.ok) {{
    document.getElementById("confirmResult").innerHTML = `<span class="badge danger">Error</span> Confirm failed: ${{r.status}}`;
    return;
  }}
  const data = await r.json();
  document.getElementById("confirmResult").innerHTML =
    `<span class="badge auto">Confirmed</span> ${{data.status}} at ${{data.utc}} (correlation_id=${{data.correlation_id}})`;
}}

loadAll();
</script>
</body>
</html>
"""
    return HTMLResponse(content=html)
