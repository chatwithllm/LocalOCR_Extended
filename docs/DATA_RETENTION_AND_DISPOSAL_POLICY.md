# Data Retention and Disposal Policy

**Application:** LocalOCR Extended
**Deployment Model:** Self-hosted, single-household / personal-use
**Effective Date:** 2026-04-17
**Review Cadence:** At least annually, and whenever a material change is made to the application or its integrations.

---

## 1. Purpose and Scope

This policy defines how LocalOCR Extended ("the Application") retains, reviews, and disposes of consumer data ingested through its supported integrations — including data obtained from Plaid APIs (linked account metadata, transactions, balances), user-uploaded grocery/household receipts, manually entered purchase records, and derived analytics.

It applies to all data stored by the self-hosted deployment, including the primary SQLite database, encrypted credential columns, uploaded receipt image files, on-disk backups, and application logs.

## 2. Data Categories and Retention Periods

| Data Category | Retention Period | Enforcement Mechanism |
|---|---|---|
| Plaid access tokens (encrypted with Fernet) | Until the user disconnects the item or deletes their account | Deleted immediately on user disconnect; no background retention |
| Plaid item metadata (institution, account names) | Same as above | Deleted with the parent `plaid_items` row |
| Plaid transactions (merchant, amount, date, category) | Maximum 12 months from transaction date | Rolling purge controlled by `RECEIPT_RETENTION_MONTHS` (default 12); applies to both staged and confirmed rows |
| Receipt image files (JPEG/PNG/PDF) | Maximum 12 months | Same rolling purge; image files unlinked from disk when their DB row is purged |
| Extracted receipt OCR / line items | Maximum 12 months | Same rolling purge |
| Derived purchase, inventory, and spending analytics | Maximum 12 months | Same rolling purge (tied to underlying purchase records) |
| User account records (email, hashed password, role) | Until user account is deleted by an administrator | Manual admin deletion via the Environment Ops UI |
| Application logs | Rotated at the container / host level, not retained beyond 30 days in normal operation | Docker log rotation + host log rotation |
| Database backups | Up to 90 days; older backups are manually pruned by the operator | Operator-managed under `BACKUP_DIR` |

The retention window for transactional and receipt data is configurable by the operator via the `RECEIPT_RETENTION_MONTHS` environment variable. The default and committed maximum for this deployment is **12 months**.

## 3. Consumer-Initiated Deletion

Users of the Application may, at any time:

- **Disconnect a linked bank account.** Doing so deletes the Plaid access token and item record from the database. No further data is pulled from Plaid for that institution.
- **Delete individual receipts, purchases, or shopping records** through the dashboard UI.
- **Request full account deletion.** Administrators can delete a user and all data owned by that user (linked items, receipts, purchases, analytics, sessions) through the admin-side Environment Ops tooling.

Deletion requests are processed on demand and do not require a fixed response window because the deployment is single-household. All deletions are hard deletes from the primary database; the only residual data is in dated backups, which are themselves pruned under Section 2.

## 4. Periodic Review

The operator reviews this policy and the enforced retention windows:

- At least once per year, and
- Whenever a new integration is added (e.g., a new OCR provider, a new financial data source), and
- Whenever `RECEIPT_RETENTION_MONTHS` or equivalent retention-related configuration is changed.

## 5. Secure Disposal

- **Database rows** are removed using SQL `DELETE` against the primary SQLite database. SQLite's write-ahead log is checkpointed as part of normal operation, so purged rows are not retained indefinitely in the WAL.
- **Receipt image files** are removed from the filesystem (`RECEIPTS_DIR`) when their corresponding database row is purged.
- **Backups** containing data older than the applicable retention window are deleted by the operator during routine backup rotation.
- **Encryption keys** (`FERNET_SECRET_KEY`) are kept out of backups and source control; credentials encrypted with a retired key are re-encrypted or deleted before key rotation.

## 6. Compliance Posture

The Application is deployed for personal / single-household use and is not offered as a commercial service. Retention and deletion practices are aligned with the principles of applicable U.S. data privacy laws (including, where relevant, the CCPA) and with Plaid's End User Privacy Policy requirements for data received through the Plaid API.

## 7. Point of Contact

Deletion requests, policy questions, and retention-related inquiries are handled by the operator of the deployment. Contact information is published in the Application's in-product privacy policy page.
