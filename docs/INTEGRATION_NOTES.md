# Member 4: Integration Notes (Batch Processing, Review and Job History)

Branch: `feature/review-jobs`. This module was built and tested standalone, with mocks for
every other member's module. Each mock sits behind an interface with a single swap point.

## 1. Endpoints

Implements the contract (section 10): create, list and read jobs, job results, correct a result,
finalize a job.

| Endpoint | Notes |
|---|---|
| `POST /api/v1/extraction-jobs` | **202** `{job_id, status: "queued"}` and processing starts. `start: false` gives **201** (create only) |
| `GET /api/v1/extraction-jobs` | Paginated job list, also used as job history |
| `GET /api/v1/extraction-jobs/{job_id}` | Job with progress and its results |
| `GET /api/v1/extraction-jobs/{job_id}/results` | Results with extracted values |
| `PATCH /api/v1/extraction-results/{result_id}` | Saves corrections: `{"corrections": [{"field_id", "value"}]}` |
| `POST /api/v1/extraction-jobs/{job_id}/finalize` | Closes a reviewed job exactly once, then requests delivery |

**Additions (not in the contract):**

| Endpoint | Why |
|---|---|
| `POST /api/v1/extraction-jobs/{job_id}/process` | Starts a job created with `start: false` |
| `GET /api/v1/extraction-results?review_status=&job_id=` | The review queue, lowest reliability first |
| `GET /api/v1/extraction-results/{result_id}` | One result with field-level detail |
| `POST /api/v1/extraction-results/{result_id}/approve` | A reviewer confirms one result |
| `GET /api/v1/finalized-results?job_id=` | Handoff for Member 5: results ready to export |
| `GET /api/v1/audit-logs` | Admin-only audit trail (the contract lists no audit endpoint) |

## 2. Database (`document_extraction`)

Collections used: `extraction_jobs`, `extraction_results`, `audit_logs`.

Fields added beyond the team schema example:
- `extraction_jobs`: `name`, `priority`, `data_structure_id`, `start_requested_at`, `processed_at`, `finalized_by`
- `extraction_results`: `reliability_score`, `ocr_confidence`, `ai_confidence`, `review_status`,
  `review_reasons`, `flagged_fields`, `corrections`, `final_fields`, `finalized_by`, `finalized_at`,
  `reviewed_by`, `reviewed_at`, `field_definitions` (snapshot), `language_routing`, `created_by`
- `audit_logs`: `job_id` (extra)

Indexes are created at startup by `ensure_indexes()` (idempotent).

## 3. Dependencies and infrastructure

- New Python packages: `celery[redis]` (plus `pymongo`, `fastapi`, `pydantic-settings`)
- New services in Docker Compose: **`redis`** (broker) and **`worker`** (Celery, same image as the API)
- Worker command: `celery -A app.core.celery_app:celery_app worker -Q p1_high,p2_medium,p3_low --pool=solo`
- New environment variables: `REDIS_URL`, `MOCK_PROCESSING_DELAY_SECONDS`, `LOG_LEVEL`, `RELIABILITY_THRESHOLD`, `WEIGHT_OCR`, `WEIGHT_AI`, `WEIGHT_VALIDATION`

## 4. What this module needs from other members (mocks to replace)

| Member | Swap point | Needed |
|---|---|---|
| 1: Documents | `get_document_provider()` | `document_id`, `filename`, `page_count`, `text_length`, `detected_language` (`en/si/ta/unknown`), `is_scanned`. **Page count and text length are not in the current schema. Please add them, or we fall back to file size** |
| 2: Data structures and templates | `get_data_structure_provider()`, `get_template_provider()` | Ordered field definitions (`field_id`, `name`, `type`, `required`, `order`); template `is_active` |
| 3: Mappings and extraction | `get_mapping_provider()`, `get_extraction_service()` | Mapping: `template_id`, `data_structure_id`, `version`, `is_active`. Engine: `extract(document_id, mapping_id)` returns `field_values` as `{field_id: {value, status, source_text}}`, optional `ai_confidence`, `validation_errors` |
| 5: Auth and output | `get_current_user()`, `require_roles()`, `get_output_service()` | Authenticated user with a role; `deliver(job_id)` called after finalize |

OCR is an optional extension in the team documents, so the OCR score is optional input to the reliability score.

## 5. Decisions made where the documents were silent (please confirm)

1. **`review_status` values:** `not_required`, `pending_review`, `approved`.
2. **Reliability score** = weighted OCR / AI confidence / validation (0.3 / 0.5 / 0.2); missing inputs are dropped and the rest rescaled. Below 0.80 goes to review. A missing or invalid **required** field always forces review.
3. **Job status:** `queued` until a worker takes it; `review_required` when processing ends with at least one success; `completed` or `partially_failed` only at finalize; `failed` if nothing succeeded. `cancelled` is unused.
4. **Roles:** Template Designer can create, view and correct their own jobs, but cannot approve or finalize. Approving and finalizing: admin and operator. Viewers see only what they own, which is nothing until sharing is defined.
5. **Ownership:** users see only jobs they created (admins see all). Someone else's job returns 404, never 403.
6. **Errors:** the contract format plus optional `details` (validation) and `request_id`; response header `X-Request-ID`.
7. **Audit:** field IDs only, never values. Rejected requests and reads are not audited.
8. **Delivery:** finalize calls `deliver(job_id)`. A delivery failure never undoes finalization.
9. **IDs:** documents keep whatever ID Member 1 uses (opaque string). Malformed IDs return 404.
10. **Extras:** `start` flag and optional `name` and `priority` on job creation.

## 6. Known limitations

- Celery runs with the `solo` pool (one job at a time).
- A killed worker's job is redelivered only after the Redis visibility timeout (1 hour by default); there is no stuck-job watchdog.
- Priority is strict between queues but never interrupts a running job, and low priority can starve.
- No transactions: the audit entry is written after the change, so a crash between them loses the entry.
- The mock authentication reads the `X-Mock-User-Id` and `X-Mock-Role` headers and works only when `ENVIRONMENT=development`.

## 7. Tests

`python -m pytest` (needs MongoDB; Redis is not needed because Celery runs eagerly in tests).