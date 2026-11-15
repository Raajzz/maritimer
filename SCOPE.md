# Maritimer: features and future scope

## 1. Features that solve the problem statement

**Hiring a port agent (Singapore owner, no staff in Mumbai)**
- Owners search port agents by port (e.g. Mumbai Port), location, service and minimum rating.
- Agent profiles show ratings, reviews, completed port calls, services and ports covered.
- The owner sends a port-call request with the vessel, ETA/ETD, cargo and services needed.
- When the agent accepts, a port call is created.

**PDA: the cost estimate**
- The agent prepares a PDA (Proforma Disbursement Account) in USD.
- Ready-made cost categories cover port dues, pilotage, towage (tugs), berth hire, customs clearance and the agency fee.
- The owner approves the PDA, or rejects it with a note.
- The agent can revise it. Every version is kept.
- The PDA can be downloaded as a PDF.

**Advance payment**
- The owner records an advance of any amount, in one payment or several.
- The agent confirms it was received. The port call then shows *Advance received*.
- If the ship arrives without an advance, the agent's dashboard flags it.

**Agent arranges services while the ship is in port**
- Categories for pilots, tugs, berth, crew immigration, fresh water, provisions (food), crew change and cash to master.
- The agent sends service requests to local vendors (merchants).
- Vendors accept or decline the agent's requests.
- The agent records the ship's arrival and departure.

**Vendor bills**
- Vendors create invoices in their own currency (e.g. INR), with the invoice file attached.
- The agent accepts or rejects each invoice, with a reason.
- The agent marks invoices as paid.

**FDA: the final account**
- After departure, the agent generates the FDA (Final Disbursement Account) automatically from all accepted vendor invoices plus the agency fee.
- Every vendor invoice is attached to the FDA PDF.
- A variance view compares the PDA and FDA line by line.

**Refund or balance**
- When the FDA is finalized, a settlement works out whether the agent refunds the difference or the owner pays the balance.
- Refunds and balance payments are recorded by one side and confirmed by the other.
- The settlement closes automatically when nothing is outstanding.
- A settlement statement can be downloaded as a PDF.

**Disputes**
- The owner can dispute any individual FDA line, with a reason and a proposed amount.
- The agent can acknowledge, explain, adjust (which creates a new FDA version automatically) or reject a dispute.
- The owner can withdraw a dispute, or reopen it once.
- The FDA cannot be finalized while any dispute is open.

**One agent, dozens of ships, many owners**
- A pipeline board shows every port call across all owners, by stage.
- KPI tiles: active calls, new requests, open disputes, invoices to review, balances owed and refunds due.
- "Needs attention" alerts for stale PDAs, missing advances, silent owners, old disputes and invoices waiting for review.
- Lists can be searched, filtered and paged.

**USD for owners, rupees for vendors**
- Accounts settle in USD, and vendor invoices can be in INR or another supported currency.
- Each line stores the exact exchange rate used, so any account can be reproduced exactly later.
- Money uses exact decimals only, never floating-point maths.

## 2. Extra features added

**Accounts and access**
- Google sign-in through Firebase.
- New users go through onboarding: company details, profile, coverage and verification documents, saved and submitted with one button.
- An Admin approves or rejects every new user, organization and document.
- Four roles (Owner, Port agent, Merchant, Admin), checked on the server for every action.
- Each company sees only its own data.

**Administration**
- Admin dashboard, approvals queue, and suspending or reinstating users.
- Admins can create organizations and add users to them in advance.
- Master data: ports, locations, service categories, cargo types and currencies.
- Request policies: switch each role-to-role request direction on or off without code changes.
- The admin can confirm or cancel a stuck payment on someone's behalf.

**Multi-currency and live exchange rates**
- Supported currencies: USD, EUR, GBP, INR, SGD, AED, CNY, JPY and MYR.
- Exchange rates are fetched automatically at the time of each transaction from free public APIs:
  - European Central Bank rates (via frankfurter.dev) first;
  - currency-api as a backup.
- Agents can also record rates manually, or fetch a market rate for any date.
- The rate history is append-only, and every rate shows its source.

**Other features**
- **Owner fleet:** owners keep a list of their vessels with IMO number, flag, type and dimensions.
- **Chat:**
  - An Owner ↔ Agent conversation for each port call, and an Agent ↔ Merchant conversation for each vendor job.
  - Created automatically when a request is accepted. Owners and vendors never chat directly.
  - File attachments, unread counts, and new messages arriving automatically (polling).
  - Closed, read-only conversations once a port call is closed or cancelled.
- **Ratings:** owners rate agents 1–5 stars after a port call. Ratings feed discovery and agent profiles.
- **Dashboards:**
  - Owner: a to-do list and the fleet.
  - Agent: the pipeline board.
  - Merchant: jobs, invoices and unpaid totals.
  - Admin: approvals and activity.
- **Audit trail:** every action records who, what and when. Each port call has a timeline.
- **Files:** stored in a private bucket. Downloads use links that expire after 5 minutes.
- **PDFs:** branded PDA, FDA and settlement documents, with drafts marked as previews.
- **Security:** rate limits, HTTPS, and other companies' records answering *not found*.
- **Interface:**
  - Mobile-friendly layout with a bottom tab bar on phones.
  - Light and dark mode (sun/moon switch).
  - A background tint per role: blue for owners, teal for agents, violet for merchants.
  - WCAG AA colour contrast.
- **Deployment:** live on free tiers of Vercel, Render, Neon, Cloudflare R2 and Firebase.
- **Tests:** 109 automated backend tests.

## 3. Future scope

**Realtime and notifications**
- Realtime chat with WebSockets (Django Channels), replacing today's polling.
- Live updates on dashboards and port-call pages when the other party acts.
- Email and push notifications for key events: PDA issued, advance confirmed, FDA issued, new dispute.

**Accounting**
- Receipt uploads for agent-paid costs that have no vendor invoice, such as port dues, berth hire and cash to master.
- Agent rates merchants, which the data model already supports.
- More currencies and per-owner settlement currency (not only USD).
- Accounting exports (CSV/Excel, Tally or QuickBooks) and analytics for agents and owners.

**Integrations**
- Actual bank payments through a payment gateway, instead of recorded payments.
- Vessel tracking (AIS) to fill in arrival and departure times automatically.
- Port tariff tables to auto-calculate port dues and pilotage on the PDA.

**Platform**
- Scheduled jobs: request expiry and reminders for stale items.
- Load testing with large numbers of ships and owners, and a paid hosting plan with no cold starts.
