# KYB And Financial Risk Assessment (Azure)

This repository contains the architecture deliverables for the technical assignment:
Company KYB onboarding and deterministic financial risk assessment on Azure, designed for regulated environments with explainability, auditability, and secure-by-default controls.

## Architecture Diagram

The assignment architecture diagram is included below and used as the primary design artifact:

![KYB Risk Assessment Architecture](architecture.png)

## Implementation Evidence (Screenshots)

Add your implementation screenshots in this section before submission.

Suggested folder:
- `docs/screenshots/`

### Azure Implementation

#### Resource Group And Deployed Services
![Azure Resource Group Overview - Placeholder](docs/screenshots/azure-resource-group-overview.png)

#### Azure Container Apps Configuration
![Azure Container Apps Settings - Placeholder](docs/screenshots/azure-container-app-settings.png)

#### Azure Key Vault Secrets And Access Policies
![Azure Key Vault Settings - Placeholder](docs/screenshots/azure-key-vault-settings.png)

#### Azure SQL Server And Database Configuration
![Azure SQL Settings - Placeholder](docs/screenshots/azure-sql-settings.png)

#### Azure Storage Account Configuration
![Azure Storage Settings - Placeholder](docs/screenshots/azure-storage-settings.png)

#### Azure Container Registry And Image
![Azure Container Registry - Placeholder](docs/screenshots/azure-acr-image.png)

#### Application Insights Overview
![Application Insights - Placeholder](\DiagramsAndScreenshots/acr_iam.png)

### Application UI Evidence

#### Review And Confirm Page
![Review Page - Placeholder](docs/screenshots/review-confirm-page.png)

### API Evidence

#### API Health Endpoint
![API Health Endpoint - Placeholder](docs/screenshots/api-health-endpoint.png)

#### API Companies Endpoint
![API Companies Endpoint - Placeholder](docs/screenshots/api-companies-endpoint.png)

#### API Documents Endpoint
![API Documents Endpoint - Placeholder](docs/screenshots/api-documents-endpoint.png)

#### API Assessments Run Endpoint
![API Assessments Run Endpoint - Placeholder](docs/screenshots/api-assessments-run-endpoint.png)

### Audit Trail Evidence

All critical workflow actions are recorded in structured audit tables for traceability and compliance review.

| Critical Action | Audit Evidence |
|---|---|
| Document ingestion logged | ![Audit Events Table](docs/screenshots/audit_events_table.png) |
| Manual human edits tracked | ![Manual Edits Audit](docs/screenshots/manual_edits_audit.png) |
| Risk scoring execution recorded | ![Risk Assessment Log](docs/screenshots/risk_assessment_log.png) |

## Implemented Azure Scope

- Resource Group: `rg-dfm-kyb-risk-uae`
- Region: `UAE North`
- Compute: Azure Container Apps (`ca-dfm-kyb-risk-uae01`, container `kyb-api`, FastAPI, port `8000`)
- Identity: System Assigned Managed Identity
- Secrets: Azure Key Vault (`kv-dfm-kyb-risk-uae01`, secret `sql-connection-string`)
- Database: Azure SQL Server (`sql-dfm-kyb-risk-uae01`) and SQL DB (`sqldb-kyb-risk`)
- Document Storage: Azure Storage Account (`stdfmkybriskuae01`) with containers `raw`, `processed`, `outputs`
- Image Pipeline: Azure Container Registry (`acrdfmkybriskuae01`, image `kyb-api:v1`)
- Monitoring: Application Insights (`appi-dfm-kyb-risk-uae01`)

## High-Level Flows

- `Compliance User -> Container App` (`HTTPS REST API`)
- `Container App -> Key Vault` (`Managed Identity Authentication`, `GetSecret(sql-connection-string)`)
- `Container App -> SQL Database` (`Secure SQL Connection (TLS)`)
- `Container App -> Blob Storage` (`Document Read / Write`)
- `ACR -> Container App` (`AcrPull`)
- `Container App -> Application Insights` (`Telemetry / Logs`)
- `Container App -> SQL Database` (`Audit Event Logging`)

## Repository Structure

```text
kyb-risk-assessment-azure/
   SourceCode/
      app/
         main.py
         db.py
         storage.py
         kv.py
      scripts/
         generate_synthetic_docs_uae_cases.py
         README.md
      synthetic_cases/
         case_01...case_10
      tests/
         test_health.py
         test_e2e_api.py
         conftest.py
   DiagramsAndScreenshots/
      architecture.png
      screenshots/
      

  README.md
  SECURITY.md
  dockerfile
  requirements.txt
  pytest.ini
  LICENSE
  .gitignore
```

## Quick Start (<=10 Minutes)

1. Create and activate a virtual environment:
   - macOS/Linux:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - Windows PowerShell:
     ```powershell
     py -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
2. Install Graphviz binary:
   - macOS: `brew install graphviz`
   - Windows: install Graphviz and add `bin` to `PATH`
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the API:
   ```bash
   python app/main.py
   ```
5. Run tests:
   ```bash
   pytest
   ```
6. Use submission artifacts from:
   - `docs/architecture/architecture.png`
   - `docs/architecture/kyb_azure_architecture.pptx`

## Explainable Risk Scoring (Design Intent)

The assignment scope is aligned to deterministic, explainable scoring:
- Numeric financial risk score and mapped risk band (`Low`/`Medium`/`High`)
- Explicit risk drivers (for example profitability, leverage, missing/old statements, audit status)
- Conservative defaults when data is missing or ambiguous
- Human-in-the-loop review and final attestation

## Assumptions And Tradeoffs

- Data is synthetic and non-PII for assessment execution.
- The design prioritizes auditability, traceability, and security controls over ML complexity.
- Managed Identity and Key Vault are used to avoid embedded credentials.
- Low-cost Azure service tiers are assumed for short-lived evaluation environments.

## Security

Security controls, handling requirements, and reporting guidance are documented in [SECURITY.md](SECURITY.md).
