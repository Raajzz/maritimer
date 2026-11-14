# Maritimer features

Maritimer runs a ship's **port call** from start to finish: an owner hires a port agent, the agent estimates the costs, hires local vendors, collects their invoices, produces the final account, and both sides settle the money. Disputes, chat, ratings, PDFs and a full audit trail are built in.

For the technical design, see [ARCHITECTURE.md](ARCHITECTURE.md), [API.md](API.md) and [STATE_MACHINES.md](STATE_MACHINES.md).

---

## Contents

1. [Roles](#1-roles)
2. [Sign-in, onboarding and approval](#2-sign-in-onboarding-and-approval)
3. [Finding an agent (owners)](#3-finding-an-agent-owners)
4. [Vessels](#4-vessels)
5. [Requests](#5-requests)
6. [Port calls](#6-port-calls)
7. [PDA: the cost estimate](#7-pda-the-cost-estimate)
8. [Vendor invoices](#8-vendor-invoices)
9. [FX rates and money handling](#9-fx-rates-and-money-handling)
10. [FDA: the final account](#10-fda-the-final-account)
11. [Disputes](#11-disputes)
12. [Payments and settlement](#12-payments-and-settlement)
13. [Chat](#13-chat)
14. [Ratings](#14-ratings)
15. [Dashboards](#15-dashboards)
16. [PDF documents](#16-pdf-documents)
17. [Files](#17-files)
18. [Administration](#18-administration)
19. [Audit trail and timeline](#19-audit-trail-and-timeline)
20. [Security](#20-security)
21. [Interface: mobile, dark mode and accessibility](#21-interface-mobile-dark-mode-and-accessibility)

---

## 1. Roles

| Role | Who they are | What they do |
|---|---|---|
| **Owner** | Shipowner or ship operator | Finds and hires an agent, approves the estimate, pays the advance and balance, reviews and disputes the final account, rates the agent |
| **Port agent** | Agency at the port | Accepts port calls, writes estimates (PDA), hires vendors, reviews invoices, records FX rates, issues the final account (FDA), resolves disputes, settles |
| **Merchant** | Local vendor (pilots, tugs, supplies, customs…) | Accepts service requests from agents, chats with them, issues invoices with the invoice file, sees payments |
| **Admin** | Platform operator | Approves users, organizations and documents, manages reference data and request rules, reads the audit log |

One Google account has exactly one role. Every user belongs to an organization (company), and all data access is scoped to that organization.

## 2. Sign-in, onboarding and approval

- **Google sign-in only**, through Firebase. There are no passwords to manage.
- The **backend decides** who you are and what you may do. Your role and approval status live in Maritimer's database, not in Firebase, and are checked on every API call.
- First-time flow:
  1. **Choose a role:** Owner, Port agent or Merchant.
  2. **Onboarding form** with several sections:
     - Company details: legal and trading name, registration and tax IDs, address, contact.
     - Role profile:
       - Owners: operator type, fleet size, preferred currency.
       - Agents: description, emergency phone, default agency fee.
       - Merchants: description, catalogue notes, default currency.
     - Coverage: the locations and ports you work in. Agents and merchants also pick the services they offer.
     - Verification documents: upload certificates and licences (PDF or image).
  3. **Submit for review.** The form checks completeness and lists anything missing.
  4. **Pending review** screen until an Admin approves you. A rejection includes the reason and lets you fix and resubmit. Suspended accounts see a suspension screen.
- The **first Admin** is created from the `BOOTSTRAP_ADMIN_EMAIL` setting and becomes linked when that Google account first signs in.
- Admins can also **pre-create** organizations and users. Those users skip onboarding and are linked on first sign-in.

## 3. Finding an agent (owners)

- Search agents by **port** or **location**, **service offered**, **minimum rating** and free-text name.
- Sort by **rating**, **name** or **ID**.
- Each result shows the average rating, number of ratings, completed port calls, services and ports covered.
- An **agent profile** shows the description, coverage, services, rating distribution and the latest reviews with their port-call reference.
- From the profile, the owner can send a **port-call request**.

## 4. Vessels

- Owners keep a **fleet list** with name, IMO number, call sign, flag, type, tonnages (GRT, NRT, DWT), length, beam and maximum draft.
- Vessels can be edited and archived. A vessel with an active port call can't be removed.
- Agents and merchants see a vessel's details only inside the port calls they're part of.

## 5. Requests

One generic request system covers every role-to-role direction:

| Type | From → To | Accepting it creates |
|---|---|---|
| **Port call request** | Owner → Port agent | a **port call** and an Owner↔Agent chat |
| **Vendor service request** | Port agent → Merchant | a job on that port call and an Agent↔Merchant chat |

- A port call request carries the vessel, port, ETA/ETD, cargo type, description and quantity, the services needed and a message.
- A vendor request carries the services, quantities and units, plus notes.
- The recipient can **accept** or **decline** (with a note). The sender can **withdraw** while the request is pending. Optional expiry dates are supported.
- **Which role may send which request to which role is a policy table** that the Admin can switch on or off. A new direction needs no code change.
- Requests have **Incoming** and **Outgoing** views with status filters.

## 6. Port calls

Each port call gets a reference (e.g. `PC-2026-000030`) and moves through a fixed lifecycle:

```
PDA pending → PDA sent → PDA approved → Advance received → In port → Departed
→ FDA issued ⇄ Disputed → FDA final → Settled → Closed          (or Cancelled before arrival)
```

- A **progress bar** and **status badge** show where the call is.
- The port-call page has tabs:
  - **Overview:** vessel, port, cargo, dates, parties
  - **PDA**, **Vendors**, **Invoices**, **FDA**, **Payments** and **Disputes**
  - **Chat** with the other party
  - **Documents:** generated PDFs and accepted invoices
  - **Timeline**
- **Only valid actions are shown.** The server computes `allowed_actions` from the state machine for the current user, and the buttons follow it. The server enforces the same rules again if someone calls the API directly.
- Agents record **arrival (ATA)** and **departure (ATD)**, and edit the ETA, ETD, berth and notes until the account is final.
- **Cancellation** is possible before arrival:
  - The agent can cancel.
  - The owner can cancel only before the PDA is approved.
  - The admin can cancel at any pre-arrival stage.
  - A reason is required, the PDA is voided and pending vendor requests are withdrawn.
- Arriving without a confirmed advance is allowed but **flagged** on the agent's dashboard.

## 7. PDA: the cost estimate

- The agent drafts a **PDA (proforma disbursement account)** in **USD**. Each line has a service category, description, quantity, unit and amount, and can include local-currency (INR) costs converted at a recorded FX rate.
- The draft has a watermarked **PDF preview**.
- **Issue** sends it to the owner, who can then:
  - **Approve** it, which unlocks the advance payment.
  - **Reject** it with a note, sending it back to the agent.
- The agent can **revise** an issued PDA the owner hasn't answered yet. Every revision becomes a new **version** (v1, v2, …), and older versions are kept and viewable.

## 8. Vendor invoices

- Merchants create invoices against a job they accepted. Each invoice has:
  - an invoice number, issue and due dates, and a currency (typically **INR**);
  - subtotal, tax and total;
  - optional line items;
  - the **invoice file** (PDF or image), which is required.
- Lifecycle:
  1. **Draft**
  2. **Issue**
  3. The agent **accepts** it or **rejects** it with a note.
  4. A rejected invoice can be **reopened** and corrected.
  5. A merchant can **void** an invoice.
- When the agent pays a vendor, they **mark it paid** with the amount, date, method and bank reference, which records a confirmed vendor payment.
- Merchants can work from a phone: there's a mobile invoice form with file upload.
- Owners see accepted and paid invoices on their own port calls (read-only), because these back the final account.

## 9. FX rates and money handling

- **No floating-point money anywhere.** All amounts are exact decimals, stored as `NUMERIC` in PostgreSQL and sent as strings in the API.
- Every amount has a **currency code**. Rounding is half-up to the currency's minor unit and applied once per line.
- **Main currencies supported:** USD, EUR, GBP, INR, SGD, AED, CNY, JPY and MYR, so owners and vendors can be in any of those countries. Accounts settle in USD, and any of these converts into it. Yen has no decimals and is rounded accordingly.
- **Rates are taken at the time of the transaction, automatically.** When a conversion needs a rate and none is recorded for that day, Maritimer fetches the market rate for that date from free public APIs and stores it as the latest rate:
  1. **European Central Bank** reference rates (via frankfurter.dev), the official source;
  2. **currency-api** (fawazahmed0) for currencies the ECB doesn't publish (e.g. AED), or when the first is down.
- "Transaction time" means:

  | Converted item | Rate date used |
  |---|---|
  | Vendor invoice | the invoice's issue date |
  | Payment | its payment date |
  | PDA line | the moment the line is saved |
  | Agency fee or manual FDA line | the vessel's departure (ATD) |

- Agents and admins can also **record a rate manually** (e.g. a bank's rate) or click **Fetch market rate** for any pair and date. Whichever rate is the latest on or before the transaction is used.
- The history is **append-only**, so old rates are never edited, and every rate shows its source (Market (ECB), Market (currency-api) or Manual).
- Inverse quotes work too: a USD→INR rate can price an INR line.
- Each converted line stores **which rate was used and its exact value** (up to 10 decimals), so any account can be reproduced exactly later.
- If the market APIs are unreachable, the latest recorded rate is used. If there is no rate at all, the FDA isn't silently built with a guess: generation fails with a clear message.

## 10. FDA: the final account

- After departure, the agent clicks **Generate FDA**. The **FDA (final disbursement account)** is built automatically from:
  - every **accepted vendor invoice**, converted to USD with the latest rate dated on or before departure;
  - the **agency fee**.
- The agent can edit lines while it's a draft, then **issue** it to the owner.
- A **PDA vs FDA variance** view compares estimate and actual line by line and in total.
- The owner can **accept** it or **dispute** individual lines.
- The FDA **can't be finalized while any dispute is open.** Finalizing creates the **settlement**.
- Optionally, a dispute window (a set number of days after issue) can be configured before finalizing is allowed.
- Like the PDA, the FDA is **versioned**. Revisions keep history, and dispute adjustments create a new version.

## 11. Disputes

- The owner can dispute **any individual FDA line**, giving a reason and optionally the amount they think is right.
- Opening a dispute puts the port call in **Disputed**.
- Each dispute has a threaded **history** of comments, with optional file attachments, from both sides.
- The agent can:
  - **Acknowledge** it, moving it to *under review*.
  - **Resolve as explained**: the charge stands, with an explanation.
  - **Resolve as adjusted**: the amount changes. The agent can either **edit the line** or add a **credit line**, and either way a new FDA revision is created automatically.
  - **Reject** it with a note.
- The owner can **withdraw** a dispute, and can **reopen** it once.
- When the last open dispute closes, the port call returns to *FDA issued* automatically.

## 12. Payments and settlement

- **Two-sided payments:** the payer records a payment, and the payee **confirms** it actually arrived. Pending payments can be cancelled by the payer.

  | Payment | Recorded by | Confirmed by |
  |---|---|---|
  | **Advance** (against the approved PDA) | Owner | Agent |
  | **Balance** (owner still owes money after the FDA) | Owner | Agent |
  | **Refund** (agent holds too much) | Agent | Owner |
  | **Vendor payment** | Agent (marks invoice paid) | — |

- Payment details include the amount, currency, date, method (bank transfer and others) and bank reference.
- The first confirmed advance moves the call to *Advance received*.
- The **settlement** is a snapshot taken when the FDA is finalized:
  - PDA total, FDA total, advances received;
  - the **direction**: owner owes, agent refunds, or nil;
  - the **outstanding** amount.
- The settlement **closes automatically** when outstanding reaches zero. A nil settlement closes at once.
- The agent can **force-close** a settlement with a note, but only within a configured write-off tolerance (default 0.00).
- After settlement, the agent **closes** the port call. This counts towards their *completed port calls* and opens rating.
- A **settlement statement PDF** is available to both sides.

## 13. Chat

- **Owner ↔ Agent** chat per port call, and **Agent ↔ Merchant** chat per vendor job. Owners and merchants never chat directly.
- Threads are created automatically when a request is accepted. Nobody can start an arbitrary thread.
- Messages can include **file attachments**. Threads show **unread counts**, and new messages arrive by polling.
- A port call's threads close when the call is closed or cancelled, and stay readable.
- Sending is rate-limited (30 messages per minute).

## 14. Ratings

- After a port call is settled or closed, the owner can **rate the agent** from 1 to 5 stars with an optional comment. There's one rating per port call.
- Ratings feed the agent's **average**, **count** and **distribution**, which owners see in discovery and on the profile.
- Agent→merchant ratings are reserved in the data model for a later version.

## 15. Dashboards

Each role lands on its own home screen.

| Role | Dashboard |
|---|---|
| **Owner** | Fleet with each vessel's active call; port calls by status; **to-do list** (approve PDA, record advance, review FDA, confirm refund, pay balance, rate agent); outgoing requests; recent activity |
| **Port agent** | **Pipeline board**: Requested → PDA → Advance → In port → FDA issued → Disputed → Settled. KPIs: active calls, new requests, open disputes, invoices to review, balances owed by owners, refunds owed to owners. **Attention items**: PDA draft not issued after 24 h, arrival without confirmed advance, FDA unanswered for 7 days, dispute open more than 3 days, invoice waiting more than 2 days |
| **Merchant** | Incoming requests, active jobs with chat links, invoices by status, **unpaid total**, recent payments |
| **Admin** | Pending users, organizations and documents; users by role; port calls by status; recent audit entries |

## 16. PDF documents

- Generated server-side with WeasyPrint, in a consistent branded layout:
  - **PDA**: the estimate with line items and totals.
  - **FDA**: the final account with FX details. **The accepted vendor invoice PDFs are appended** to it as supporting documents.
  - **Settlement statement**: totals, direction, outstanding, and the payments made.
- **Drafts are watermarked** as previews.
- Generated files are **cached** per document version and status, and rebuilt only when something changes.
- Downloads go through a permission check and a short-lived signed link.

## 17. Files

- Used for invoice files, verification documents, chat attachments and dispute evidence.
- **Allowed types:** PDF, PNG, JPG and WEBP, **up to 15 MB**, with an upload rate limit.
- Files sit in a **private** Cloudflare R2 bucket in production (the local disk in development).
- **Downloads use 5-minute signed links**, issued only to people allowed to see the record the file belongs to: the invoice's port call, the chat's participants, the dispute's parties, or the organization plus admins for verification documents.

## 18. Administration

- **Approvals queue:** review new users with their organization, profile, coverage and documents, then **approve** or **reject** with a reason. Each **verification document** is approved or rejected separately.
- **Users:** search and filter by role and status. **Suspend** and **reinstate** accounts.
- **Organizations:**
  - Browse by type and verification status.
  - Edit details and coverage.
  - Approve, reject or suspend at organization level.
  - **Create an organization directly**, already approved, and **add users** to it in advance.
- **Master data**, never hard-deleted (deactivated instead):
  - Locations, ports (with UN/LOCODE) and service categories (including whether vendors offer them)
  - Cargo types, and currencies (activated or deactivated)
- **Request policies:** switch each role-to-role request direction on or off.
- **FX rates:** view and add.
- **Payment support:** confirm or cancel a stuck payment on someone's behalf, with an audit entry.
- **Audit log:** filter by entity, port call, user or action.
- **API docs:** an OpenAPI schema and Swagger UI (admin-only in production).

## 19. Audit trail and timeline

- **Every state change and important edit** writes an audit entry recording:
  - who did it and their role;
  - the action, with the before and after state;
  - extra details;
  - the time.
- The audit log is **append-only**. Optionally, the database itself can block edits and deletes on audit and dispute-history tables (`AUDIT_LOG_REVOKE_ROLE`).
- Each port call has a **Timeline** tab, which is its audit history newest first, visible to the owner and agent.

## 20. Security

- **Server-side enforcement on every endpoint**, in this order:
  1. a valid Google token;
  2. the user (and their organization) is approved;
  3. the role is allowed;
  4. the object belongs to their organization.
- **No existence leaks:** records outside your organization return *not found*, not *forbidden*.
- **Every state change runs inside a single service function.** The function:
  - checks permission;
  - **locks the row** to prevent double-processing;
  - validates the transition against the state-machine table;
  - writes the audit entry;
  - does all of this in one database transaction.
- **A test checks the state machines in code against the diagrams** in STATE_MACHINES.md.
- **Database-level invariants** (CHECK constraints and partial unique indexes) back up the application rules.
- **Rate limits:** 600 requests per minute per user, 30 chat messages per minute, 20 uploads per minute.
- **Production hardening:**
  - HTTPS redirect and HSTS;
  - development tokens disabled;
  - CORS limited to the real frontend domain;
  - no demo accounts or developer sign-in in the production build.
- A suite of **109 backend tests** covers permissions, state machines, money and FX, settlement, disputes, database invariants, full API flows and PDFs.

## 21. Interface: mobile, dark mode and accessibility

- **Mobile-first, responsive layout:**
  - **Desktop:** a sidebar.
  - **Phones:** a bottom tab bar with a *More* page.
  - Tables turn into stacked cards on small screens, and dialogs become bottom sheets.
  - Touch targets are at least 44 px.
- **Light and dark mode:**
  - A **sun / moon switch** in the top bar and on the sign-in and onboarding screens.
  - It follows the system setting until you choose, and your choice is remembered on that device.
  - The theme is applied before the page paints, so there's no flash.
- **Brand palette:**
  - Navy `#0B3C5D`, teal `#0E8A9A`, orange call-to-action `#FF6B1A`, plus success green and error red.
  - Every text and background pair meets **WCAG AA contrast** in both themes.
- **Accessible forms:**
  - Every input has a linked label.
  - Errors are shown next to the field.
  - Focus rings are clearly visible.
- Maritime terms are shown properly: PDA, FDA, ETA and ATD in capitals, and money with currency codes and exact decimals.
