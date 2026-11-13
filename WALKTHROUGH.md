# WALKTHROUGH.md — end-to-end demo checklist

Run against a fresh `seed_demo`, locally or in production (DEPLOY.md §6).
- **Locally:** use the "Development sign-in" buttons to switch roles.
- **In production:** sign in with the Google accounts you passed to `seed_demo`.

Each box is one thing to verify. Port-call references (`PC-…`) differ per seed; the table below says which seeded call to use.

| Seeded call | State | Used in |
|---|---|---|
| MV Straits Pioneer (first `PC-…`) | CLOSED with refund, 2 disputes, rating | §5 history |
| MV Orchard Star | DISPUTED | §4 |
| MV Lion Voyager | DEPARTED, one invoice awaiting review | §3 |
| MT Temasek Spirit | IN_PORT, vendor request pending | §3 |
| MV Merlion Trader | PDA_APPROVED, advance not yet confirmed | §2 |
| MV Sentosa Bay | PDA_SENT | §2 |

Automated equivalents: `backend/tests/test_api_flow.py` covers the HTTP flow. The UI flows below were also scripted with Playwright during Phase 3 on desktop (1280px) and phone (390px) viewports.

---

## 1. Onboarding and approval (new user → Admin)

- [ ] Sign in as a **new** account. Locally, type any email such as `new.agent@example.com` in the dev box. In production, use an unseeded Google account.
- [ ] **Choose role** shows Owner / Port agent / Merchant. Pick **Port agent** and click **Continue**.
- [ ] Onboarding shows four sections. **Submit for review** is disabled, and the warning lists what's missing.
- [ ] Fill in the legal name and city, then **Save company details**.
- [ ] Add a description and an agency fee, then **Save profile**.
- [ ] Tick **Mumbai Port** and a few services, then **Save coverage**.
- [ ] Upload a PDF as *Company registration*. It appears with a *Pending* badge.
- [ ] **Submit for review** shows the *Under review* screen. Try a deep link such as `/port-calls`; you stay on *Under review*. The API returns `403 not_approved`.
- [ ] Sign in as **Admin**. On **Approvals**, the user is listed as *Pending review*. Open the user.
- [ ] Open the document; it views in a new tab. Click **Approve document**, then **Approve user & organization**.
- [ ] Sign back in as the new agent and confirm the **Pipeline** loads.
- [ ] Rejection path: as Admin, reject another applicant (`applicant.pilots.demo@…`) with a reason. That user sees the reason on the onboarding page. Their first edit re-opens onboarding, and they can resubmit.

## 2. Owner: discovery, request, PDA, advance

- [ ] As **Owner**, open **Find agents**, pick location *Mumbai*, then port *Mumbai Port*. Agents are listed with rating and review count.
- [ ] Sort by Name, ID and Rating, and filter by minimum rating and service; the list updates. Open an agent profile to see the rating breakdown and recent reviews.
- [ ] Click **Send request**: choose a vessel, ETA/ETD, cargo, services and notes, then **Send request**. It lands on the request page as *Pending*.
- [ ] As **Agent**, the request appears in the **Requested** pipeline column. Open it and click **Accept**. You land on the new port call, and a chat with the owner exists.
- [ ] On the **PDA** tab, click **Prepare PDA**; the agency fee line is pre-filled. Add an INR line (e.g. Pilotage INR 185000). **Save lines** shows the USD amount computed by the server at the recorded FX rate. Then **Issue PDA to owner**.
- [ ] As **Owner**, open *MV Sentosa Bay* → **PDA**. **Approve PDA** works, and **Reject** asks for a reason.
  - After a reject, the agent sees the note, clicks **Start revised PDA**, and v2 is created with v1 in the version history.
- [ ] **PDF** opens the PDA PDF with branded header, line items and FX rates.
- [ ] Owner → **Payments** → **Record advance** (amount, reference). It shows *Pending*.
- [ ] As **Agent**, **Payments** → **Confirm received**. The port call becomes *Advance received*.
- [ ] *MV Merlion Trader* already has a pending advance for the agent to confirm.

## 3. Agent: arrival, vendors, invoices, FDA

- [ ] Agent → **Overview** → **Record arrival** (status *In port*), then **Record departure** (*Departed*).
- [ ] On *MT Temasek Spirit* → **Vendors**, click **Request a merchant**. Pick services; merchants serving that port appear. Send the request.
- [ ] As **Merchant (supplies)**, the dashboard shows the new request. **Accept** it and **Open conversation**. The agent and merchant can chat; the owner never sees this thread.
- [ ] Merchant → **Create invoice**: number, service, INR subtotal and GST (the total computes), attach a PDF, then **Issue to agent**.
- [ ] As **Agent** on **Invoices**, filter defaults to *Issued*. Open the invoice; **Accept**, or **Reject** with a note, which the merchant can reopen and fix.
- [ ] *MV Lion Voyager* → **FDA** → **Generate FDA from invoices**. One line per accepted invoice plus the agency fee is converted to USD at the latest rate on or before departure.
  - Warnings name PDA lines without invoices; add them as agent-paid lines.
  - If an FX rate is missing, the error names the pair and links to **FX rates**.
- [ ] Add an agent-paid line (Port dues INR), link it to the PDA line, then **Save lines**. The **Variance against the PDA** table shows per-line and total variance.
- [ ] **Issue FDA to owner**.
- [ ] **FX rates** page: record a rate. The history is append-only.

## 4. Disputes and finalization

- [ ] As **Owner** on *MV Orchard Star* → **FDA**, each line has **Dispute**, and the pilotage line already shows *Disputed*.
  - Dispute another line with a reason and proposed amount.
  - The port call is *Disputed*, and the Disputes tab lists both.
- [ ] As **Agent**, **Finalize FDA** is refused ("Resolve all open disputes…").
- [ ] Open a dispute and **Acknowledge** it (*Under review*), then comment. The owner sees the comment in the history.
- [ ] **Resolve → Adjusted**: enter the corrected amount, then **Resolve**.
  - A new FDA version (v2, Draft) carries a credit line, or the edited line for agent-paid lines.
  - The dispute links to it, and v1 shows as *Superseded* in the version history.
- [ ] **Reject** the other dispute with a note. As **Owner**, **Reopen (once)** is available a single time; reject again, and reopen is no longer offered.
- [ ] Agent: **Issue FDA** (v2), then **Finalize FDA** and confirm. The FDA is *Final*, and **Payments** shows the settlement:
  - FDA total, advance and balance (*Balance due* or *Refund due*), plus outstanding.
- [ ] Balance due: the owner clicks **Record balance payment** and the agent confirms. Refund due: the agent clicks **Record refund** and the owner confirms.
  - Partial payments show *Partially paid*, and over-payment is refused.
  - Once outstanding is 0 the settlement is *Closed* and the port call *Settled*.
- [ ] **Statement** opens the settlement PDF. The FDA **PDF** includes the variance table, disputes and appended vendor invoice PDFs.
- [ ] Agent: open each accepted invoice and click **Mark as paid**; the merchant sees the payment on their dashboard.
- [ ] Agent → **Overview** → **Close port call**. Chat becomes read-only.
- [ ] Owner → **Rate the agent** (1–5 plus comment). The agent profile's rating and review count update.

## 5. Dashboards, documents, audit

- [ ] **Agent pipeline** columns: Requested → PDA → Advance → In port → FDA issued → Disputed → Settled, with KPI tiles.
  - The *Needs attention* list fills as items age (stale PDA drafts, missing advances, aging disputes, invoices waiting).
- [ ] **Owner dashboard**: *Needs your action* (approve PDA, record advance, review FDA, pay balance or confirm refund, rate agent), the fleet with active calls, and recent requests and activity.
- [ ] **Merchant dashboard**: new requests, active jobs with chat and invoice shortcuts, invoices by status, unpaid totals and recent payments.
- [ ] Port call → **Documents**: issued and final PDA/FDA/settlement PDFs and accepted invoices. → **Timeline**: every transition with actor and time.
- [ ] **Admin**:
  - **Organizations → Create organization**, an agent with a pre-approved user email; that user signs in straight to the app.
  - **Master data**: add a port, deactivate it, and confirm it disappears from owner discovery.
  - **Request policies**: enabling *Vendor service · Merchant → Agent* opens that direction with no deploy.
  - **Audit log**: filter by `dispute.`.

## 6. Mobile (phone width, about 390px)

- [ ] The bottom tab bar shows four destinations plus **More**. Sign-out is under More and in the top bar.
- [ ] Tables become stacked cards, and modals open as bottom sheets. Nothing scrolls sideways except the agent pipeline and the tab strip, which scroll by design.
- [ ] Complete §2's advance confirmation and §4's dispute resolution on a phone. Both were verified on a 390px viewport.

## 7. Security spot checks

- [ ] As Owner A, open another owner's port-call URL: *Page not found* (the API returns 404, not 403).
- [ ] As Merchant, a port call shows no PDA/FDA/payments tabs and no owner name. `GET /port-calls/{id}/pda` returns 403.
- [ ] Remove `VITE_DEV_AUTH` in production; the dev sign-in box disappears. Production Django rejects `Bearer dev:` tokens anyway.
