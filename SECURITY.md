# SECURITY.md

## Security Scope

This project is a technical assignment implementation for a KYB and financial risk assessment workflow on Azure. It is designed for controlled evaluation using synthetic data, not as a production-ready banking platform.

## Data Handling Requirements

- Use only synthetic or publicly available sample data.
- Do not store or process real customer PII in this repository.
- Do not commit confidential documents, keys, or tokens.
- Mask sensitive values in logs, API traces, and UI previews.

## Identity And Access Controls

- Use Azure Managed Identity for service-to-service authentication.
- Apply least privilege RBAC to all Azure resources.
- Restrict Key Vault permissions to required principals only.
- Avoid shared owner-level access for day-to-day operations.

## Secrets Management

- Store secrets only in Azure Key Vault (`kv-dfm-kyb-risk-uae01`).
- Do not hardcode credentials in source code, scripts, or configs.
- Rotate credentials and access keys if exposure is suspected.
- Use Key Vault references or runtime retrieval (`GetSecret`) from the app.

## Network And Transport Security

- Enforce HTTPS/TLS for API traffic and SQL connectivity.
- Use private networking patterns where feasible (for example private endpoints) for production hardening.
- Minimize public ingress and egress exposure.

## Application And API Security

- Validate and sanitize all user inputs and uploaded files.
- Restrict accepted file types and enforce size limits for uploads.
- Implement authentication and authorization checks for sensitive endpoints.
- Protect against common API risks (OWASP API Top 10 baseline controls).

## Logging, Monitoring, And Auditability

- Send telemetry to Application Insights (`appi-dfm-kyb-risk-uae01`).
- Maintain structured audit logs for:
  - Document ingestion
  - Data extraction
  - Risk score calculation
  - Manual edits and reviewer actions
- Retain traceability from risk outcomes to source fields/documents.

## Dependency And Supply Chain Security

- Pin dependencies where possible.
- Review dependency updates regularly and patch known vulnerabilities.
- Scan container images before deployment.
- Use trusted registries and signed images where available.

## Secure Development Practices

- Run static checks and basic tests before release.
- Review code changes for security impact.
- Keep infrastructure and application configuration under version control.
- Separate environment-specific configuration from code.

## Incident Response (Assignment Level)

If a secret leak or vulnerability is detected:

1. Revoke/rotate exposed credentials immediately.
2. Remove sensitive data from history where possible.
3. Assess blast radius (resources, data, logs).
4. Apply remediation and document changes.
5. Re-deploy with updated secure configuration.

## Vulnerability Reporting

To report a security issue in this repository:

- Open a private channel with the repository owner/maintainer.
- Include affected files, reproduction steps, impact, and suggested mitigation.
- Avoid posting exploit details in public issues.

## Security Limitations

- This repository is timeboxed for assessment and may omit production controls.
- Additional controls recommended for production: WAF/API gateway, SIEM integration, private endpoints, DLP, backup/DR, and continuous compliance monitoring.
