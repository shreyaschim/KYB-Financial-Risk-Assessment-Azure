# Summary — KYB & Financial Risk Assessment System (Azure)

## 1. Overall Approach

This solution implements a **regulatory-style Know Your Business (KYB) document ingestion, extraction, risk assessment, and human review system** deployed on Microsoft Azure.

The system follows a **document-centric pipeline architecture**:

1. **Company Creation**
   - A company profile is created via API (`POST /companies`).
   - A unique `company_id` and `correlation_id` are generated to track all subsequent events.

2. **Document Ingestion**
   - Documents are uploaded either individually or in bulk.
   - Files are stored in **Azure Blob Storage (`raw-documents`)**.
   - Metadata is recorded in **Azure SQL Database**.

3. **Document Classification**
   - Documents are classified using lightweight heuristics based on filename and extracted text.
   - Supported types include:
     - Trade License
     - MOA / AOA
     - Board Resolution
     - IDs
     - Bank Letters
     - VAT / TRN
     - Financial Statements

4. **Text Extraction**
   - PDF documents are parsed to extract text content.
   - Extracted text is stored in **Blob Storage (`extracted-text`)**.

5. **Field Extraction**
   - Structured data fields (e.g., license number, financial figures) are extracted.
   - Extracted fields and evidence snippets are stored in:
     - `extracted_fields` table
     - `evidence-snippets` blob container.

6. **Exception Detection**
   - The system automatically generates compliance exceptions such as:
     - Missing mandatory documents
     - Low classification confidence
     - Missing key fields.

7. **Risk Assessment**
   - Financial risk indicators are calculated based on extracted financial data and compliance signals.
   - Results are stored in `risk_assessments` and exported to `risk-reports`.

8. **Human-in-the-Loop Review**
   - A **Review & Confirm UI** displays extracted data and computed risk indicators.
   - Reviewers can:
     - Inspect supporting documents
     - Edit extracted fields
     - Confirm regulatory attestation.

9. **Auditability**
   - All actions generate structured audit events recorded in `audit_events`.

---

# 2. Trade-offs and Assumptions

### Trade-offs

**Lightweight document classification**

Instead of training a machine learning model, the system uses rule-based classification.  
This simplifies deployment and avoids external dependencies but reduces classification accuracy.

**Basic text extraction**

PDF parsing is implemented using a lightweight text extraction approach.  
OCR for scanned images is not included to keep infrastructure simple.

**Synchronous processing**

Document ingestion, extraction, and classification are executed synchronously within the API container rather than using background workers or queues.  
This simplifies architecture but limits scalability for very large workloads.

**Single service architecture**

All business logic is implemented within a single container application.  
A microservice-based architecture was avoided to reduce operational complexity for this assignment.

---

# 3. Company Financial Risk Scoring Logic

The financial risk score is calculated using a **rule-based scoring model** based on:

### Financial Indicators
- Revenue
- Net Profit / Loss
- Total Assets
- Total Liabilities
- Audit status
- Financial reporting period

### Compliance Indicators
- Missing mandatory documents
- Number of open compliance exceptions
- Confidence of document classification
- Missing extracted financial fields

### Risk Score Calculation

The system starts with a **base score of 100** and deducts points based on risk factors.

Example scoring logic:

| Risk Condition | Penalty |
|----------------|--------|
Missing financial statements | -40 |
Missing revenue data | -10 |
Missing profit/loss | -10 |
Unknown audit status | -10 |
Open high-severity exceptions | -15 |
Low document classification confidence | -5 |

Final score bands:

| Score | Risk Band |
|------|-----------|
70 – 100 | LOW |
40 – 69 | MEDIUM |
0 – 39 | HIGH |

Risk drivers explaining the score are stored in the response and risk report.

---

# 4. Known Limitations

This implementation is a **demonstration system** and includes several limitations:

**OCR not implemented**

Scanned image documents cannot currently be processed.  
A production system would integrate **Azure Document Intelligence or OCR services**.

**Simplified document classification**

Classification is rule-based rather than ML-based, which may produce lower accuracy.

**Limited fraud detection**

Financial risk scoring uses basic heuristics rather than advanced anomaly detection models.

**UI security limitations**

The document viewer is implemented as a browser modal.  
Complete prevention of screenshots or downloads cannot be guaranteed in web browsers.

**Scalability considerations**

The ingestion pipeline runs synchronously inside the API container.  
Large-scale production deployments would typically use:
- message queues
- background workers
- event-driven processing.

---

# 5. High-Level Azure Cost Estimate

Estimated monthly cost for a **small production-like workload**:

| Azure Service | Estimated Cost |
|---------------|---------------|
Azure Container Apps | $10 – $25 |
Azure SQL Database (serverless) | $5 – $20 |
Azure Storage Account | $2 – $5 |
Azure Key Vault | <$1 |

### Total Estimated Cost
**~$20 – $50 per month**

Costs depend on:
- number of companies processed
- document volume
- log retention
- compute scaling.

For this assignment workload the system can run within **Azure free tier / minimal cost limits**.

---

# Conclusion

The implemented solution demonstrates a **complete KYB document processing workflow** including:

- Document ingestion and classification
- Structured data extraction with evidence tracking
- Compliance exception detection
- Financial risk scoring
- Human-in-the-loop verification
- Full auditability

The architecture is designed to be **secure, traceable, and extensible**, aligning with regulatory expectations for financial risk assessment systems.