# DFM KYB & Financial Risk Assessment on Azure (Executive Submission)

## 1. Objective
Build a secure, auditable KYB onboarding and deterministic financial risk assessment solution for regulated operations, deployed on Azure.

## 2. Delivered Solution
- FastAPI service hosted on Azure Container Apps
- Managed Identity access to Key Vault and Blob Storage
- Azure SQL persistence for KYB records, extracted fields, exceptions, edits, risk outputs, and audit trail
- Human-in-the-loop review, manual override, and attestation endpoint
- Deterministic, explainable risk scoring with explicit drivers

## 3. Architecture
![Architecture Diagram](architecture.png)

### Runtime Flow
1. Client uploads company and documents through REST APIs.
2. API stores raw files in Blob Storage and metadata in SQL.
3. API extracts text/fields, stores evidence snippets, and raises exceptions.
4. Reviewer inspects and edits extracted values.
5. Risk engine computes score/band and stores report JSON in Blob + SQL.
6. Audit events are captured for each critical action.

## 4. Azure Implementation (Current)
- Resource Group: `rg-dfm-kyb-risk-uae`
- Region: `UAE North`
- Container App: `ca-dfm-kyb-risk-uae01`
- ACR: `acrdfmkybriskuae01`
- Key Vault: `kv-dfm-kyb-risk-uae01`
- Azure SQL: `sql-dfm-kyb-risk-uae01` / `sqldb-kyb-risk`
- Storage: `stdfmkybriskuae01`
- App Insights: `appi-dfm-kyb-risk-uae01`

Required env vars:
- `KEY_VAULT_URL`
- `SQL_SECRET_NAME`
- `STORAGE_ACCOUNT`
- `STORAGE_CONTAINER`

## 5. Repository Structure
```text
KYB-Financial-Risk-Assessment-Azure/
├── README.md
├── README2.md
├── architecture.png
├── db_schema.md
├── dockerfile
├── DiagramsAndScreenshots/
└── SourceCode/
    ├── app/
    ├── tests/
    ├── synthetic_cases/
    └── scripts/
```

## 6. API Summary
Base URL: `https://<container-app-url>`

- `GET /health` - service status/version
- `POST /companies` - create company
- `POST /ingest` - ingest one document
- `POST /ingest/bulk` - ingest multiple documents
- `GET /review/{company_id}` - unified KYB snapshot
- `POST /review/edit` - manual field correction
- `POST /review/confirm` - reviewer attestation
- `POST /risk-assessment/{company_id}` - compute and persist risk assessment
- `GET /documents/{document_id}/view` - inline document viewing
- `GET /ui/review/{company_id}` - reviewer UI

## 7. Sample API Calls

### Create company
```bash
curl -X POST "$BASE/companies" \
  -F "external_ref=EXT-001" \
  -F "company_name=Acme Trading LLC"
```

### Ingest document
```bash
curl -X POST "$BASE/ingest" \
  -F "company_id=<company_id>" \
  -F "file=@SourceCode/synthetic_cases/case_01/trade_license.pdf"
```

### Compute risk
```bash
curl -X POST "$BASE/risk-assessment/<company_id>"
```

## 8. Screenshots (Drop-In Template)

### Azure
![Azure Resource Group](DiagramsAndScreenshots/azure-resource-group.png)
![Azure Container App](DiagramsAndScreenshots/azure-container-app.png)
![Azure Key Vault Secrets](DiagramsAndScreenshots/azure-keyvault-secrets.png)
![Azure Storage Containers](DiagramsAndScreenshots/azure-storage-containers.png)
![Azure SQL Database](DiagramsAndScreenshots/azure-sql-database.png)

### API and UI
![API Health](DiagramsAndScreenshots/api-health.png)
![API Create Company](DiagramsAndScreenshots/api-create-company.png)
![API Ingest](DiagramsAndScreenshots/api-ingest.png)
![API Review](DiagramsAndScreenshots/api-review.png)
![API Risk Assessment](DiagramsAndScreenshots/api-risk-assessment.png)
![Review UI](DiagramsAndScreenshots/ui-review-page.png)

## 9. Security and Compliance Notes
- Secrets are fetched from Key Vault (no hardcoded credentials).
- Blob and Key Vault access use Managed Identity.
- SQL connection uses TLS via ODBC Driver 18.
- Audit logging implemented for key lifecycle actions.

## 10. Future Scope
1. Enforce Azure AD auth and RBAC for all API operations.
2. Integrate Azure AI Document Intelligence for higher extraction quality.
3. Externalize scoring into policy/rule configuration with versioning.
4. Introduce async queue-based ingestion and retry controls.
5. Add production observability dashboards, alerts, and SLOs.
6. Add private networking and hardened perimeter controls.
