from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple
import pyodbc

def _normalize_semicolon_kv(s: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in s.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def build_odbc_conn_str(raw: str) -> str:
    """
    DO NOT CHANGE (your original logic):
    Accepts either:
    - Full ODBC string containing DRIVER=...
    - Or semicolon KV string like:
      server=...;port=1433;database=...;user=...;password=...;encrypt=true
    Returns a valid pyodbc connection string using ODBC Driver 18.
    """
    if "driver=" in raw.lower():
        s = raw
        if "encrypt=" not in raw.lower():
            s += ";Encrypt=yes"
        if "trustservercertificate=" not in raw.lower():
            s += ";TrustServerCertificate=no"
        return s

    kv = _normalize_semicolon_kv(raw)
    server = kv.get("server") or kv.get("host")
    if not server:
        raise ValueError("SQL conn string missing 'server='")

    port = kv.get("port", "1433")
    database = kv.get("database")
    user = kv.get("user") or kv.get("uid") or kv.get("username")
    password = kv.get("password") or kv.get("pwd")

    if not database or not user or not password:
        raise ValueError("SQL conn string missing database/user/password")

    encrypt_raw = (kv.get("encrypt") or "true").lower()
    encrypt = "yes" if encrypt_raw in ("1", "true", "yes") else "no"

    server_with_port = f"{server},{port}"

    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server_with_port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt={encrypt};"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )


class Database:
    def __init__(self, conn_str: str):
        self.conn_str = build_odbc_conn_str(conn_str)

    def _connect(self) -> pyodbc.Connection:
        return pyodbc.connect(self.conn_str, autocommit=False)

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -------------------------
    # COMPANIES
    # -------------------------
    def create_company(self, external_ref: str, company_name: str) -> str:
        company_id = str(uuid.uuid4())
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.companies (company_id, external_ref, company_name, created_utc, updated_utc)
                VALUES (?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                """,
                company_id, external_ref, company_name
            )
        return company_id

    def get_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        cid = str(company_id)
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT company_id, external_ref, company_name, created_utc, updated_utc
                FROM dbo.companies
                WHERE company_id = ?
                """,
                cid,
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    # -------------------------
    # DOCUMENTS
    # -------------------------
    def create_document(
        self,
        company_id: str,
        file_name: str,
        blob_path: str,
        file_sha256_hex: str,
    ) -> str:
        document_id = str(uuid.uuid4())
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.documents (
                  document_id, company_id, file_name, blob_path, file_sha256,
                  doc_type_pred, doc_type_confidence, language,
                  issue_date, expiry_date,
                  extracted_text_blob_path,
                  created_utc, extracted_utc
                ) VALUES (
                  ?, ?, ?, ?, ?,
                  NULL, NULL, NULL,
                  NULL, NULL,
                  NULL,
                  SYSUTCDATETIME(), NULL
                )
                """,
                document_id, str(company_id), file_name, blob_path, file_sha256_hex
            )
        return document_id

    def update_document_metadata(
        self,
        document_id: str,
        doc_type_pred: str,
        doc_type_confidence: float,
        language: Optional[str],
        issue_date: Optional[str],   # YYYY-MM-DD
        expiry_date: Optional[str],  # YYYY-MM-DD
    ) -> None:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE dbo.documents
                SET doc_type_pred = ?,
                    doc_type_confidence = ?,
                    language = ?,
                    issue_date = ?,
                    expiry_date = ?
                WHERE document_id = ?
                """,
                doc_type_pred, doc_type_confidence, language, issue_date, expiry_date, str(document_id)
            )

    def update_document_extracted_text_blob_path(self, document_id: str, extracted_text_blob_path: str) -> None:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE dbo.documents
                SET extracted_text_blob_path = ?
                WHERE document_id = ?
                """,
                extracted_text_blob_path,
                str(document_id),
            )

    def mark_document_extracted(self, document_id: str) -> None:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE dbo.documents
                SET extracted_utc = SYSUTCDATETIME()
                WHERE document_id = ?
                """,
                str(document_id),
            )

    def list_documents_for_company(self, company_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                  document_id, company_id, file_name, blob_path, file_sha256,
                  doc_type_pred, doc_type_confidence, language,
                  issue_date, expiry_date, extracted_text_blob_path,
                  created_utc, extracted_utc
                FROM dbo.documents
                WHERE company_id = ?
                ORDER BY created_utc DESC
                """,
                str(company_id),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]


    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                  document_id, company_id, file_name, blob_path, file_sha256,
                  doc_type_pred, doc_type_confidence, language,
                  issue_date, expiry_date, extracted_text_blob_path,
                  created_utc, extracted_utc
                FROM dbo.documents
                WHERE document_id = ?
                """,
                str(document_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    # -------------------------
    # EXTRACTED FIELDS
    # -------------------------
    def insert_extracted_fields(
        self,
        company_id: str,
        document_id: str,
        fields: List[Dict[str, Any]],
    ) -> None:
        cid = str(company_id)
        did = str(document_id)
        with self._connection() as conn:
            cur = conn.cursor()
            for f in fields:
                field_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO dbo.extracted_fields (
                      field_id, company_id, document_id,
                      field_path, field_value, confidence,
                      evidence_snippet, snippet_sha256,
                      extraction_method, created_utc
                    ) VALUES (
                      ?, ?, ?,
                      ?, ?, ?,
                      ?, ?,
                      ?, SYSUTCDATETIME()
                    )
                    """,
                    field_id,
                    cid,
                    did,
                    f.get("field_path"),
                    f.get("field_value"),
                    f.get("confidence"),
                    f.get("evidence_snippet"),
                    f.get("snippet_sha256"),
                    f.get("extraction_method"),
                )

    def list_extracted_fields(self, company_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                  field_id, company_id, document_id,
                  field_path, field_value, confidence,
                  evidence_snippet, snippet_sha256,
                  extraction_method, created_utc
                FROM dbo.extracted_fields
                WHERE company_id = ?
                ORDER BY created_utc DESC
                """,
                str(company_id),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    # -------------------------
    # EXCEPTIONS
    # -------------------------
    def insert_exception(
        self,
        company_id: str,
        document_id: Optional[str],
        exception_type: str,
        severity: str,
        message: str,
        status: str = "OPEN",
    ) -> None:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.exceptions (
                  exception_id, company_id, document_id,
                  exception_type, severity, message, status,
                  created_utc
                ) VALUES (
                  ?, ?, ?,
                  ?, ?, ?, ?,
                  SYSUTCDATETIME()
                )
                """,
                str(uuid.uuid4()),
                str(company_id),
                str(document_id) if document_id else None,
                exception_type,
                severity,
                message,
                status,
            )

    def list_exceptions(self, company_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                  exception_id, company_id, document_id,
                  exception_type, severity, message, status,
                  created_utc, resolved_utc
                FROM dbo.exceptions
                WHERE company_id = ?
                ORDER BY created_utc DESC
                """,
                str(company_id),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    # -------------------------
    # AUDIT EVENTS
    # -------------------------
    def insert_audit_event(
        self,
        correlation_id: str,
        company_id: str,
        event_type: str,
        actor: str,
        details: str,
    ) -> None:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.audit_events (
                  event_id, correlation_id, company_id,
                  event_type, actor, details, created_utc
                ) VALUES (
                  ?, ?, ?,
                  ?, ?, ?, SYSUTCDATETIME()
                )
                """,
                str(uuid.uuid4()),
                str(correlation_id),
                str(company_id),
                event_type,
                actor,
                details,
            )

    # -------------------------
    # MANUAL EDITS
    # -------------------------
    def insert_manual_edit(
        self,
        company_id: str,
        field_path: str,
        old_value: Optional[str],
        new_value: str,
        reason: str,
        reviewer: str,
    ) -> str:
        edit_id = str(uuid.uuid4())
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.manual_edits (
                  edit_id, company_id, field_path,
                  old_value, new_value,
                  reason, reviewer,
                  created_utc
                ) VALUES (
                  ?, ?, ?,
                  ?, ?,
                  ?, ?,
                  SYSUTCDATETIME()
                )
                """,
                edit_id, str(company_id), field_path, old_value, new_value, reason, reviewer
            )
        return edit_id

    def list_manual_edits(self, company_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                  edit_id, company_id, field_path,
                  old_value, new_value, reason, reviewer,
                  created_utc
                FROM dbo.manual_edits
                WHERE company_id = ?
                ORDER BY created_utc DESC
                """,
                str(company_id),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    # -------------------------
    # RISK ASSESSMENTS
    # -------------------------
    def insert_risk_assessment(
        self,
        company_id: str,
        overall_risk: str,
        score: int,
        rationale: str,
        model_version: str,
    ) -> str:
        assessment_id = str(uuid.uuid4())
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.risk_assessments (
                  assessment_id, company_id,
                  overall_risk, score, rationale, model_version,
                  created_utc
                ) VALUES (
                  ?, ?,
                  ?, ?, ?, ?,
                  SYSUTCDATETIME()
                )
                """,
                assessment_id, str(company_id),
                overall_risk, int(score), rationale, model_version
            )
        return assessment_id

    def get_latest_risk_assessment(self, company_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT TOP 1
                  assessment_id, company_id, overall_risk, score, rationale, model_version, created_utc
                FROM dbo.risk_assessments
                WHERE company_id = ?
                ORDER BY created_utc DESC
                """,
                str(company_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()