# DB Schema (Azure SQL)

This schema supports a regulatory KYB onboarding + document evidence + human review + deterministic risk scoring workflow.

## Tables

### `companies`
Stores the KYB entity (one row per company/customer).

| Column | Type | Notes |
|---|---|---|
| company_id | uniqueidentifier | **PK** |
| external_ref | nvarchar | External reference / client id |
| company_name | nvarchar | Display name |
| created_utc | datetime2 | Created timestamp (UTC) |
| updated_utc | datetime2 | Updated timestamp (UTC) |

**Recommended constraints / indexes**
- `PK(companies.company_id)`
- `INDEX IX_companies_external_ref (external_ref)`

---

### `documents`
Stores uploaded documents and derived metadata (classification, extracted text location).

| Column | Type | Notes |
|---|---|---|
| document_id | uniqueidentifier | **PK** |
| company_id | uniqueidentifier | **FK → companies.company_id** |
| file_name | nvarchar | Original file name |
| blob_path | nvarchar | Path in `raw-documents` container |
| file_sha256 | char | SHA-256 of original bytes |
| doc_type_pred | nvarchar | Predicted doc type (e.g., TRADE_LICENSE) |
| doc_type_confidence | decimal | Confidence score |
| language | nvarchar | Detected language (e.g., en/ar) |
| issue_date | date | Parsed issue date (if applicable) |
| expiry_date | date | Parsed expiry date (if applicable) |
| extracted_text_blob_path | nvarchar | Path in `extracted-text` container |
| created_utc | datetime2 | Created timestamp (UTC) |
| extracted_utc | datetime2 | Extraction timestamp (UTC) |

**Recommended constraints / indexes**
- `PK(documents.document_id)`
- `FK(documents.company_id → companies.company_id)`
- `INDEX IX_documents_company_created (company_id, created_utc DESC)`
- `INDEX IX_documents_sha (file_sha256)`

---

### `extracted_fields`
Stores extracted key-value fields with evidence snippet + confidence.

| Column | Type | Notes |
|---|---|---|
| field_id | uniqueidentifier | **PK** |
| company_id | uniqueidentifier | **FK → companies.company_id** |
| document_id | uniqueidentifier | **FK → documents.document_id** |
| field_path | nvarchar | Canonical JSON path (e.g., `licenseDetails.licenseNumber`) |
| field_value | nvarchar | Extracted value |
| confidence | decimal | Extraction confidence |
| evidence_snippet | nvarchar | Short text evidence |
| snippet_sha256 | char | SHA-256 of snippet |
| extraction_method | nvarchar | e.g., regex/pdf, model, etc. |
| created_utc | datetime2 | Created timestamp (UTC) |

**Recommended constraints / indexes**
- `PK(extracted_fields.field_id)`
- `FK(extracted_fields.company_id → companies.company_id)`
- `FK(extracted_fields.document_id → documents.document_id)`
- `INDEX IX_fields_company_path (company_id, field_path, created_utc DESC)`
- `INDEX IX_fields_document (document_id)`

---

### `manual_edits`
Human-in-the-loop overrides (reviewer edits that should take precedence over extracted fields).

| Column | Type | Notes |
|---|---|---|
| edit_id | uniqueidentifier | **PK** |
| company_id | uniqueidentifier | **FK → companies.company_id** |
| field_path | nvarchar | Canonical JSON path |
| old_value | nvarchar | Previous value (optional) |
| new_value | nvarchar | Updated value |
| reason | nvarchar | Reason for change |
| reviewer | nvarchar | Reviewer identity |
| created_utc | datetime2 | Created timestamp (UTC) |

**Recommended constraints / indexes**
- `PK(manual_edits.edit_id)`
- `FK(manual_edits.company_id → companies.company_id)`
- `INDEX IX_manual_edits_company_path (company_id, field_path, created_utc DESC)`

---

### `exceptions`
Regulatory/compliance exceptions raised during ingestion/extraction/review.

| Column | Type | Notes |
|---|---|---|
| exception_id | uniqueidentifier | **PK** |
| company_id | uniqueidentifier | **FK → companies.company_id** |
| document_id | uniqueidentifier | Nullable, **FK → documents.document_id** |
| exception_type | nvarchar | e.g., MISSING_MANDATORY_DOCS, NO_FIELDS_EXTRACTED |
| severity | nvarchar | LOW / MEDIUM / HIGH |
| message | nvarchar | Human-readable detail |
| status | nvarchar | OPEN / RESOLVED |
| created_utc | datetime2 | Created timestamp (UTC) |
| resolved_utc | datetime2 | Resolved timestamp (UTC, nullable) |

**Recommended constraints / indexes**
- `PK(exceptions.exception_id)`
- `FK(exceptions.company_id → companies.company_id)`
- `FK(exceptions.document_id → documents.document_id)` (nullable)
- `INDEX IX_exceptions_company_status (company_id, status, created_utc DESC)`
- `INDEX IX_exceptions_doc (document_id)`

---

### `risk_assessments`
Stores deterministic risk scoring output per company (can be multiple versions over time).

| Column | Type | Notes |
|---|---|---|
| assessment_id | uniqueidentifier | **PK** |
| company_id | uniqueidentifier | **FK → companies.company_id** |
| overall_risk | nvarchar | LOW / MEDIUM / HIGH |
| score | int | 0–100 |
| rationale | nvarchar | Semi-structured rationale / drivers |
| model_version | nvarchar | Version tag (e.g., demo-v1) |
| created_utc | datetime2 | Created timestamp (UTC) |

**Recommended constraints / indexes**
- `PK(risk_assessments.assessment_id)`
- `FK(risk_assessments.company_id → companies.company_id)`
- `INDEX IX_risk_company_created (company_id, created_utc DESC)`

---

### `audit_events`
Immutable audit trail for key actions (ingest, classify, extract, edits, review, risk score).

| Column | Type | Notes |
|---|---|---|
| event_id | uniqueidentifier | **PK** |
| correlation_id | uniqueidentifier | Request/flow correlation |
| company_id | uniqueidentifier | **FK → companies.company_id** |
| event_type | nvarchar | e.g., COMPANY_CREATED, DOCUMENT_UPLOADED |
| actor | nvarchar | system / reviewer name |
| details | nvarchar | Additional event payload |
| created_utc | datetime2 | Created timestamp (UTC) |

**Recommended constraints / indexes**
- `PK(audit_events.event_id)`
- `FK(audit_events.company_id → companies.company_id)`
- `INDEX IX_audit_company_created (company_id, created_utc DESC)`
- `INDEX IX_audit_correlation (correlation_id)`

---

## Blob Storage Containers (Reference)

| Container | Purpose |
|---|---|
| raw-documents | Original uploaded documents (PDF/TXT/etc.) |
| extracted-text | Extracted full-text per document (`<company>/<document>.txt`) |
| evidence-snippets | Evidence snippets per extracted field |
| risk-reports | Final report JSON per assessment |
| $blobchangefeed | Azure internal change feed |
