# API.md — REST API (Django REST Framework)

Status: Phase 1 design. Base path `/api/v1`. All responses JSON. Implement exactly; add endpoints
only via PROGRESS.md.

## 0. Conventions

**Auth.** `Authorization: Bearer <Firebase ID token>` on every request except `GET /health`.
The backend verifies the token with the Firebase Admin SDK and resolves a local `User`.

**Permission layers (every endpoint, in order).**
1. `IsAuthenticated` — valid Firebase token.
2. `IsApproved` — `user.status = APPROVED` and (role = ADMIN or org `verification_status = APPROVED`).
   Exempt: §1 Auth and §2 Onboarding.
3. Role gate — column **Roles** below: O owner, A agent, M merchant, X admin.
4. Object scoping — selectors filter by the actor's organization; a 404 is returned for objects
   outside scope (never 403, to avoid existence leaks), except for state/permission violations on
   in-scope objects which return 403/409.

**Errors.**
```json
{ "error": { "code": "invalid_transition", "message": "PDA can only be issued from DRAFT",
             "details": { "field": ["msg"] } } }
```
Codes: `validation_error` (400), `unauthenticated` (401), `forbidden` (403), `not_approved` (403,
details.status tells the UI where to route), `not_found` (404), `invalid_transition` (409),
`policy_denied` (403), `conflict` (409), `rate_limited` (429).

**Pagination.** `?page=1&page_size=25` (max 100). Response: `{ "count", "next", "previous", "results": [] }`.
**Sorting.** `?sort=field` or `-field` from the per-endpoint allow-list. **Filtering.** query params listed per endpoint. **Search.** `?q=` (icontains on named fields).

**Money.** Amounts are JSON strings (`"12345.67"`), never numbers. Every amount is accompanied by a
currency code field. Rates are strings with up to 10 decimals.

**Timestamps.** ISO-8601 UTC (`2026-11-13T10:00:00Z`). Dates `YYYY-MM-DD`.

**Transitions** are `POST /<resource>/{id}/<verb>` and return the updated resource.

**Common shapes.**
```
OrgSummary   { id, type, legal_name, trade_name, country_code, city }
UserSummary  { id, display_name, email, role }
Money        { amount: "1234.56", currency_code: "USD" }
FileRef      { id, original_filename, content_type, size_bytes, download_url }   // download_url is short-lived
StatusBadge  { status, status_changed_at }
```

---

## 1. Auth & session

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /health` | public | `{status:"ok"}` |
| `GET /auth/me` | any signed-in | `{ user: {id,email,display_name,photo_url,role,status,status_reason}, organization: OrgSummary|null, organization_status, next_step }` — `next_step` ∈ CHOOSE_ROLE, ONBOARDING, PENDING_REVIEW, REJECTED, SUSPENDED, APP |
| `POST /auth/choose-role` | status=NEW | body `{role}` → user ONBOARDING, creates org shell + profile |
| `POST /auth/logout` | any | no-op server side (client signs out of Firebase); kept for audit |

---

## 2. Onboarding (status ONBOARDING/REJECTED users)

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /onboarding` | self | `{ organization, profile, locations:[], ports:[], services:[], documents:[], completeness:{missing:[...]} }` |
| `PUT /onboarding/organization` | self | company/person details (`legal_name, trade_name, registration_number, tax_id, email, phone, website, address_line1, address_line2, city, postal_code, country_code`) |
| `PUT /onboarding/profile` | self | role-specific: OWNER `{operator_kind, fleet_size, preferred_currency_code, notes}`; AGENT `{description, emergency_phone, default_agency_fee: Money|null}`; MERCHANT `{description, catalog_notes, default_currency_code}` |
| `PUT /onboarding/coverage` | self | `{ location_ids:[], port_ids:[], service_category_ids:[] }` (owners: locations+ports only) |
| `POST /onboarding/documents` | self | multipart `{document_type, title, file}` → VerificationDocument |
| `DELETE /onboarding/documents/{id}` | self | only while PENDING and user not APPROVED |
| `POST /onboarding/submit` | self | → PENDING_REVIEW (validates completeness) |

---

## 3. Master data (read: any approved user; write: X)

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /meta/enums` | approved | all CHECK-enum vocabularies (roles, statuses, vessel types, document types, payment kinds/methods) for the UI |
| `GET /countries` | approved | list |
| `GET /locations?country=IN&q=` | approved | active locations |
| `GET /ports?location_id=&q=` | approved | active ports (with location + country) |
| `GET /service-categories?vendor_only=true` | approved | |
| `GET /cargo-types` | approved | |
| `GET /currencies` | approved | active currencies |
| `GET /fx-rates?base=INR&quote=USD&as_of_lte=2026-11-13` | A, X | list, newest first |
| `GET /fx-rates/latest?base=INR&quote=USD&as_of_lte=` | A, X | the row the FDA builder would pick |
| `POST /fx-rates` | A, X | `{base_currency_code, quote_currency_code, rate, as_of, source:"MANUAL", source_reference}` — append-only |
| `POST /admin/locations`, `PATCH /admin/locations/{id}` | X | create / update (incl. `is_active`) |
| `POST /admin/ports`, `PATCH /admin/ports/{id}` | X | |
| `POST /admin/service-categories`, `PATCH .../{id}` | X | |
| `POST /admin/cargo-types`, `PATCH .../{id}` | X | |
| `PATCH /admin/currencies/{code}` | X | `is_active` only |
| `GET /admin/request-policies`, `PATCH /admin/request-policies/{id}` | X | `{is_enabled}` — the directionality switch |

Master data is never hard-deleted (DELETE not exposed); use `is_active=false`.

---

## 4. Admin — verification & accounts

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /admin/dashboard` | X | `{ pending_users, pending_organizations, pending_documents, users_by_role, port_calls_by_status, recent_audit:[...] }` |
| `GET /admin/users?status=&role=&q=&sort=` | X | sort: created_at, email, display_name, status |
| `GET /admin/users/{id}` | X | user + org + profile + documents + audit tail |
| `POST /admin/users/{id}/approve` | X | `{note?}` — approves user and org (if PENDING_REVIEW) |
| `POST /admin/users/{id}/reject` | X | `{reason}` |
| `POST /admin/users/{id}/suspend` / `/reinstate` | X | `{reason?}` |
| `GET /admin/organizations?type=&verification_status=&q=` | X | |
| `GET /admin/organizations/{id}` | X | full org, profile, coverage, members, documents |
| `POST /admin/organizations` | X | create org directly: `{type, organization:{...}, profile:{...}, coverage:{...}}` → APPROVED |
| `PATCH /admin/organizations/{id}` | X | edit details / coverage |
| `POST /admin/organizations/{id}/approve` / `/reject` / `/suspend` | X | org-level |
| `POST /admin/organizations/{id}/users` | X | `{email, display_name}` → pre-provisioned APPROVED user with `role = org.type`; links on first Google sign-in with that email |
| `POST /admin/documents/{id}/approve` / `/reject` | X | `{note?}` |
| `GET /admin/audit-log?entity_type=&entity_id=&port_call_id=&actor_user_id=&action=&page=` | X | |
| `POST /admin/payments/{id}/confirm` / `/cancel` | X | support path (audited) |

Bootstrap: management command `python manage.py bootstrap_admin --email you@example.com` creates an APPROVED ADMIN user (firebase_uid NULL; links on first sign-in).

---

## 5. Discovery (Owner)

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /agents?port_id=&location_id=&min_rating=&service_category_id=&q=&sort=` | O (A, X read too) | agent orgs serving the port/location. sort: `-rating` (default), `rating`, `name`, `-name`, `id`, `-id`. Row: `OrgSummary + { rating_avg, rating_count, completed_port_calls, services:[{id,code,name}], ports:[{id,name,unlocode}] }` |
| `GET /agents/{org_id}` | O, A, X | profile, coverage, services, last 10 ratings (score, comment, created_at, port reference), rating distribution |

---

## 6. Vessels (Owner)

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /vessels?q=&sort=name` | O (own org) | |
| `POST /vessels` | O | `{name, imo_number?, call_sign?, flag_country_code?, vessel_type, grt?, nrt?, dwt?, loa_m?, beam_m?, max_draft_m?}` |
| `GET /vessels/{id}` / `PATCH` / `DELETE` (soft) | O | DELETE refused (409) if vessel has a non-terminal port call |

Agents/merchants see vessel details embedded in port calls only.

---

## 7. Requests (generic)

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /requests?direction=incoming\|outgoing&request_type=&status=&port_call_id=&sort=-created_at` | O, A, M | scoped to actor org as from/to |
| `GET /requests/{id}` | party | full: header, `details` (PORT_CALL: vessel, port, eta, etd, cargo_type, cargo_description, cargo_quantity, cargo_unit), `services:[{service_category, quantity, unit, notes}]`, `port_call: {id, reference, status}|null`, `chat_thread_id|null` |
| `POST /requests` | O (PORT_CALL), A (VENDOR_SERVICE) — per policy table | body below |
| `POST /requests/{id}/accept` | to_org | `{note?}` → returns request + `port_call` (PORT_CALL) / `chat_thread_id` |
| `POST /requests/{id}/decline` | to_org | `{note?}` |
| `POST /requests/{id}/withdraw` | from_org | |

`POST /requests` body:
```json
{ "request_type": "PORT_CALL", "to_organization_id": 12, "subject": "MV Example – Mumbai Nov",
  "message": "Crew change of 4 at berth.",
  "details": { "vessel_id": 3, "port_id": 7, "eta": "...", "etd": "...", "cargo_type_id": 2,
               "cargo_description": "Steel coils", "cargo_quantity": "12000", "cargo_unit": "MT" },
  "services": [ { "service_category_id": 1 }, { "service_category_id": 5, "quantity": "300", "unit": "MT", "notes": "fresh water" } ],
  "payload": {} }
```
```json
{ "request_type": "VENDOR_SERVICE", "to_organization_id": 40, "port_call_id": 101,
  "subject": "Fresh water 300 MT", "message": "Alongside berth 7, 15 Nov 0600",
  "services": [ { "service_category_id": 5, "quantity": "300", "unit": "MT" } ] }
```
The server derives `from_user/from_organization/from_role/to_role` and rejects pairs not enabled in `request_role_policies` with `policy_denied`.

---

## 8. Port calls

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /port-calls?status=&status_group=&vessel_id=&port_id=&owner_organization_id=&agent_organization_id=&q=&sort=` | O, A, M (M: calls where it has an accepted vendor request or invoice), X | sort: `eta`, `-eta`, `reference`, `-status_changed_at`. `status_group` ∈ pipeline columns (STATE_MACHINES §3). Row: `{id, reference, status, vessel:{id,name,imo_number}, port:{id,name,unlocode}, owner:OrgSummary, agent:OrgSummary, eta, etd, ata, atd, pda_total:Money|null, advance_total:Money, fda_total:Money|null, open_disputes:int, settlement:{direction,outstanding}|null}` |
| `GET /port-calls/{id}` | party | aggregate: header + vessel + port + cargo + `pda:{id,version,status,total}` + `fda:{...}` + `advance_total` + `settlement` + `open_disputes` + `chat_thread_id` + `counts:{vendor_requests, invoices, documents}` + `allowed_actions:[...]` (computed from state machine for the actor — drives the UI buttons) |
| `PATCH /port-calls/{id}` | A | `{eta?, etd?, berth?, notes?}` (not in terminal states) |
| `POST /port-calls/{id}/arrive` | A | `{ata}` |
| `POST /port-calls/{id}/depart` | A | `{atd}` |
| `POST /port-calls/{id}/cancel` | A, O (pre-PDA-approval), X | `{reason}` |
| `POST /port-calls/{id}/close` | A | SETTLED → CLOSED |
| `GET /port-calls/{id}/timeline` | party | audit entries for this call, newest first `{action, actor:UserSummary, from_state, to_state, metadata, created_at}` |
| `GET /port-calls/{id}/vendor-requests` | A (all), M (own) | VENDOR_SERVICE requests on this call |
| `GET /port-calls/{id}/documents` | O, A | generated PDFs + accepted invoice files `[{document_type, version, entity_status, file:FileRef, generated_at}]` |

---

## 9. Disbursement accounts (PDA / FDA)

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /port-calls/{id}/pda` | O, A | current PDA (404 if none) |
| `GET /port-calls/{id}/pda/versions` | O, A | all versions, summary rows |
| `POST /port-calls/{id}/pda` | A | create DRAFT v1 (or next version if last is REJECTED/SUPERSEDED) `{notes?, line_items:[...]}` |
| `GET /port-calls/{id}/fda` / `/fda/versions` | O, A | |
| `POST /port-calls/{id}/fda/generate` | A | `{ fx_rate_ids?: {"INR": 55}, notes? }` → DRAFT built from accepted invoices + agency fee; response includes `warnings:[]` (e.g. invoice currency without a rate) |
| `GET /disbursement-accounts/{id}` | O, A | full: header, `line_items:[LineItem]`, `totals`, and for FDA `variance:{ lines:[{fda_line, pda_line, variance:Money}], pda_total, fda_total, total_variance }`; `disputes:[summary]` for FDA |
| `PUT /disbursement-accounts/{id}/line-items` | A | replace the whole line set (DRAFT only) |
| `POST /disbursement-accounts/{id}/issue` | A | |
| `POST /disbursement-accounts/{id}/approve` | O | PDA only |
| `POST /disbursement-accounts/{id}/reject` | O | PDA only, `{note}` |
| `POST /disbursement-accounts/{id}/accept` | O | FDA only (optional acceptance signal) |
| `POST /disbursement-accounts/{id}/revise` | A | ISSUED/REJECTED → new DRAFT version |
| `POST /disbursement-accounts/{id}/finalize` | A | FDA only → FINAL + settlement |
| `POST /disbursement-accounts/{id}/discard` | A | DRAFT version > 1 |
| `GET /disbursement-accounts/{id}/pdf` | O, A | 302 to signed URL (or stream in dev). DRAFT = watermarked preview |

`LineItem` (request and response):
```json
{ "id": 1, "line_no": 1, "service_category_id": 3, "description": "Pilotage in/out",
  "vendor_organization_id": 40, "quantity": "1", "unit": "lot",
  "local_amount": "185000.00", "local_currency_code": "INR",
  "fx_rate_id": 55, "fx_rate_applied": "0.0120000000", "amount": "2220.00",
  "pda_line_item_id": 9, "vendor_invoice_id": 17, "supersedes_line_item_id": null,
  "is_adjustment": false, "source_dispute_id": null, "notes": "" }
```
On write, the server computes `amount` from `local_amount × fx_rate_applied` (rate taken from `fx_rate_id`; must be `null` with rate 1 when `local_currency_code` equals the account currency) and rejects client-supplied `amount` that disagrees.

---

## 10. Vendor invoices

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /vendor-invoices?port_call_id=&status=&vendor_organization_id=&sort=-issue_date` | M (own), A (billed to me), O (ACCEPTED/PAID on own calls, read-only), X | |
| `POST /vendor-invoices` | M | `{port_call_id, vendor_request_id, service_category_id, invoice_number, issue_date, due_date?, currency_code, subtotal_amount, tax_amount, total_amount, file_id, notes?, lines?:[...]}` → DRAFT |
| `GET /vendor-invoices/{id}` | party | with `lines`, `file:FileRef`, `fda_line:{account_id, version}|null`, `payment:{...}|null` |
| `PUT /vendor-invoices/{id}` | M | DRAFT only |
| `POST /vendor-invoices/{id}/issue` | M | |
| `POST /vendor-invoices/{id}/accept` / `/reject` | A | reject `{note}` |
| `POST /vendor-invoices/{id}/reopen` | M | REJECTED → DRAFT |
| `POST /vendor-invoices/{id}/void` | M | |
| `POST /vendor-invoices/{id}/mark-paid` | A | `{amount, currency_code, paid_at, method, bank_reference}` → creates CONFIRMED VENDOR_PAYMENT and sets PAID |
| `GET /vendor-invoices/{id}/file` | party | 302 signed URL |

---

## 11. Payments & settlement

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /port-calls/{id}/payments?kind=&status=` | O, A (M sees VENDOR_PAYMENTs to itself via invoices) | |
| `POST /port-calls/{id}/payments` | O (ADVANCE, BALANCE), A (REFUND) | `{kind, amount, currency_code, fx_rate_id?, paid_at, method, bank_reference?, provider?:"MANUAL"}`; server sets payer/payee/links; returns PENDING |
| `GET /payments/{id}` | party | |
| `POST /payments/{id}/confirm` | payee org (A for ADVANCE/BALANCE, O for REFUND) | → CONFIRMED; side effects per STATE_MACHINES §6 |
| `POST /payments/{id}/cancel` | payer org (PENDING only), X | `{reason}` |
| `GET /port-calls/{id}/settlement` | O, A | `{reference, direction, pda_total, fda_total, advance_total, balance, outstanding, status, payments:[...], closed_at}` (404 before finalization) |
| `POST /settlements/{id}/force-close` | A | `{note}` — only when outstanding ≤ `SETTLEMENT_WRITEOFF_TOLERANCE` (default 0.00) |
| `GET /settlements/{id}/pdf` | O, A | settlement statement |

---

## 12. Disputes

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /disputes?port_call_id=&status=&sort=-created_at` | O, A (own calls), X | |
| `POST /disputes` | O | `{line_item_id, reason, disputed_amount?}` |
| `GET /disputes/{id}` | O, A | dispute + `line_item` (with account version) + `events:[{event_type, actor:UserSummary, from_status, to_status, body, file:FileRef|null, created_at}]` |
| `POST /disputes/{id}/comment` | O, A | `{body, file_id?}` |
| `POST /disputes/{id}/acknowledge` | A | → UNDER_REVIEW |
| `POST /disputes/{id}/resolve` | A | `{resolution_type:"EXPLAINED"|"ADJUSTED", note, adjusted_local_amount?, mode?:"EDIT_LINE"|"CREDIT_LINE"}` — ADJUSTED creates/uses a DRAFT FDA revision (STATE_MACHINES §8) and returns `{dispute, fda:{id,version,status}}` |
| `POST /disputes/{id}/reject` | A | `{note}` |
| `POST /disputes/{id}/withdraw` | O | |
| `POST /disputes/{id}/reopen` | O | once |

---

## 13. Files

| Method & path | Roles | Purpose |
|---|---|---|
| `POST /files` | approved (and onboarding users for purpose=VERIFICATION) | multipart `{file, purpose}`; allow-list pdf/png/jpg/jpeg/webp; ≤ 15 MB → `FileRef` |
| `GET /files/{id}` | uploader, or party to the owning record | metadata + fresh `download_url` |

File ownership for access checks is resolved through the referencing row (invoice → port call parties; verification doc → org + admin; chat → thread participants; dispute event → dispute parties).

---

## 14. Chat

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /chat/threads?port_call_id=&sort=-last_message_at` | participant orgs | `{id, kind, subject, port_call:{id,reference}, request_id, participants:[OrgSummary], last_message:{...}|null, unread_count, is_closed}` |
| `GET /chat/threads/{id}` | participant | thread + participants |
| `GET /chat/threads/{id}/messages?after_id=&limit=50` | participant | ascending by id; polling with `after_id` |
| `POST /chat/threads/{id}/messages` | participant (thread not closed) | `{body, file_id?}`; throttle 30/min |
| `POST /chat/threads/{id}/read` | participant | `{last_read_message_id}` |

Threads are only ever created by request acceptance; there is no create endpoint. Owner↔Merchant pairs never exist.

---

## 15. Ratings

| Method & path | Roles | Purpose |
|---|---|---|
| `POST /port-calls/{id}/ratings` | O (v1); A→M reserved | `{ratee_organization_id, score, comment?, vendor_request_id?}`; port call ∈ {SETTLED, CLOSED}; one per (call, rater, ratee) |
| `GET /port-calls/{id}/ratings` | parties | |
| `GET /organizations/{id}/ratings?page=` | approved | public ratings received |

---

## 16. Dashboards

| Method & path | Roles | Purpose |
|---|---|---|
| `GET /dashboard` | O, A, M | role-specific payload (below) |
| `GET /admin/dashboard` | X | see §4 |

**Agent:** `{ pipeline: { requested: [RequestRow], pda_sent: [PortCallRow], advance_received: [...], in_port: [...], fda_issued: [...], disputed: [...], settled: [...] }, kpis: { active_calls, pending_requests, open_disputes, invoices_awaiting_review, outstanding_balance_due: Money, outstanding_refund_due: Money }, attention: [ {type, port_call, message} ] }`
`attention` items: PDA draft not issued > 24h, arrival without confirmed advance, FDA issued and owner silent > 7d, dispute open > 3d, invoice ISSUED > 2d.

**Owner:** `{ vessels: [{vessel, active_call|null}], calls_by_status: {...}, pending_actions: [ {type: APPROVE_PDA|RECORD_ADVANCE|REVIEW_FDA|CONFIRM_REFUND|PAY_BALANCE|RATE_AGENT, port_call} ], outgoing_requests: [RequestRow], recent_activity: [audit rows] }`

**Merchant:** `{ incoming_requests: [RequestRow], active_jobs: [ {request, port_call, chat_thread_id} ], invoices_by_status: {...}, unpaid_total: Money, recent_payments: [...] }`

---

## 17. Role × endpoint matrix (summary)

| Area | Owner | Agent | Merchant | Admin |
|---|---|---|---|---|
| Onboarding (self) | ✓ | ✓ | ✓ | – |
| Master data read | ✓ | ✓ | ✓ | ✓ |
| Master data write, approvals, policies | – | – | – | ✓ |
| FX rates write | – | ✓ | – | ✓ |
| Discovery (agents) | ✓ | read | – | read |
| Vessels | ✓ own | – | – | read |
| Requests: PORT_CALL | create/withdraw | accept/decline | – | read |
| Requests: VENDOR_SERVICE | – | create/withdraw | accept/decline | read |
| Port call ops (arrive/depart/edit/close) | – | ✓ | – | read + cancel |
| PDA | approve/reject/read | create/edit/issue/revise | – | read |
| FDA | accept/read/dispute | generate/edit/issue/revise/finalize | – | read |
| Vendor invoices | read accepted | accept/reject/mark-paid | create/issue/void | read |
| Payments | record advance/balance, confirm refund | record refund, confirm advance/balance | see vendor payments | confirm/cancel |
| Settlement | read | read/force-close | – | read |
| Disputes | open/comment/withdraw/reopen | acknowledge/comment/resolve/reject | – | read |
| Chat | with agent | with owner & merchants | with agent | – |
| Ratings | rate agent | (future: rate merchant) | – | read |
| Dashboards | own | own | own | admin |
| Audit log | own calls' timeline | own calls' timeline | – | all |

---

## 18. Non-functional

- Throttling: 600 req/min per user; chat POST 30/min; file upload 20/min.
- All list endpoints are indexed per SCHEMA.md; N+1 avoided with `select_related/prefetch_related` in selectors.
- OpenAPI schema generated with `drf-spectacular` at `/api/schema` and Swagger UI at `/api/docs` (admin-only in prod).
- CORS: `CORS_ALLOWED_ORIGINS` env (Vercel prod + preview domains, localhost:5173).
