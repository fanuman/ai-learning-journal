# Day 44 - The web app: sign in, upload, review, reconcile

Status: **proposal, nothing written to your repo yet.** Read it, ask about anything unclear, then say "write it". Backend: no changes today.

## What we build and why
Until now the product could only be used through Swagger. Today a person gets real screens:
1. **Sign in / create a company account**
2. **Documents**: upload a file, see the list, watch statuses change by themselves
3. **One document**: what was read, the checks' findings, and, if the machine was unsure, **the review panel** (approve / correct / reject). For an invoice, a **Compare with the quote** button and the result.

"Thin" on purpose: no UI library, no Tailwind, no state library. About 1,100 lines of TypeScript plus one 330-line stylesheet, small enough to read in one sitting, so you can explain every line in an interview.

## Decisions I made (tell me if you want any changed)
| Decision | Choice | Why | Trade-off |
|---|---|---|---|
| Framework | Next.js (App Router) + TypeScript | The design doc and the job market ask for it | More to learn than plain React |
| Rendering | Every page is a **client component** (`"use client"`) | The login token lives in the browser, so the server cannot know who you are while building a page | We do not use Next.js's server rendering strengths; fine for a logged-in tool |
| Talking to the API | A **proxy**: the browser calls `/api/...`, Next.js forwards to FastAPI (`next.config.ts`) | One origin, so **no CORS** settings in the backend; the same shape as production behind a load balancer | One more hop in development. If an upload ever fails only through the proxy, the fallback is CORS in FastAPI |
| Token storage | `sessionStorage` | Simple; gone when the tab closes | Readable by any script on the page. Production: httpOnly cookie. We say this in the README |
| Live updates | **Polling** every 3 s while a document is `uploaded` or `processing` | Matches the 202 + poll design from Day 43; no extra infrastructure | Not instant; websockets or server-sent events are the upgrade |
| Styling | One plain CSS file, light and dark | Nothing to install or learn | Not pretty-pixel-perfect (non-goal in the design doc) |
| Fonts | System fonts | `next/font/google` downloads at build time; one less thing to fail | - |
| CI | A second job `web`: install, lint, type-check, build | A broken UI is caught on every push | +1 minute per run |

## What I could and could not check before showing you
- **Checked here:** the non-React code (`types`, `auth`, `format`, `api`) and all components type-check under TypeScript strict mode (against hand-written stubs for React/Next, because this workspace cannot reach the npm registry). I ran the helper functions and the API client against a fake server (token header, error messages, upload as form data, 401 clears the token, "reviewer" is never sent). I rendered the table and review components to HTML and checked their text.
- **Not checked here:** `npm install`, the real Next.js build, ESLint, and the pages in a real browser. **Your `npm run build` and clicking through are the real test.** If anything fails, paste the output.

---

# Part 1 - Concepts

## Glossary
- **Next.js.** A framework on top of React that adds pages by folder name, a dev server and a production build. A file `src/app/login/page.tsx` becomes the URL `/login`. (Django analogy: `urls.py` is replaced by the folder tree.)
- **React component.** A function that returns a piece of screen (JSX). `<StatusBadge status="failed" />` calls `StatusBadge({status: "failed"})`.
- **JSX/TSX.** HTML-looking syntax inside TypeScript. `{x}` inserts a value. React **escapes** it, so text from a document can never become HTML on the page (important: documents can contain hostile text).
- **TypeScript.** JavaScript plus types. Types exist only while you write and build; the browser receives plain JavaScript. `interface DocumentSummary {...}` describes a JSON shape.
- **State (`useState`).** A value React remembers between renders; changing it with its setter redraws the component. `const [busy, setBusy] = useState(false)`.
- **Effect (`useEffect`).** Code that runs *after* the screen is drawn: loading data, timers. The returned function is a clean-up that runs when the component goes away or the effect restarts.
- **Hook.** A function whose name starts with `use` and that may only be called at the top level of a component (or another hook). `usePolled` is ours.
- **`"use client"`.** First line of a file that uses state, effects or browser APIs.
- **Rewrite (proxy).** A rule in `next.config.ts`: requests for `/api/x` are answered by fetching `http://127.0.0.1:8000/x`. The browser never sees the second address.
- **CORS.** A browser rule: a page from origin A may not read responses from origin B unless B says so in headers. The proxy avoids the whole topic.
- **Polling.** Asking again every few seconds: "is it finished?".
- **`key`.** A label React uses to tell list items (or components) apart. Changing a component's `key` throws away its state and starts it fresh. We use this on purpose in the review panel.
- **Stale response.** A slow answer arriving after the page moved on. The `cancelled` flag in `usePolled` ignores it.

## How a click travels (upload)
```
UploadForm (browser)  --POST /api/documents + file-->  Next.js dev server
                                                        |  rewrite
                                                        v
                                            FastAPI  POST /documents  --> 202 + id (+ background job starts)
UploadForm calls onUploaded() -> usePolled.reload() -> GET /api/documents -> list shows "uploaded"
... every 3 s while any row is uploaded/processing ... -> row becomes "processed" or "needs review"
```

## The review loop as the person sees it
```
status "needs review" --> ReviewPanel (shows issues + the question from the server)
   Approve  -> POST /review {action:"approve", note}                 -> processed
   Reject   -> POST /review {action:"reject", note}                  -> rejected
   Correct  -> POST /review {action:"correct", note, extraction:{..}}
                   server re-runs the SAME checks on your values
                   still errors?  -> status stays "needs review", new question  -> panel resets (new key)
                   clean?         -> processed
```
The browser never sends who you are: the server reads it from the token.

---

# Part 2 - Step 0, before any file is written (you run this)

The workspace cannot reach npm, so you create the Next.js skeleton on your Mac; we then replace its files. From the repo root (`freight-doc-intelligence`):
```
npx create-next-app@latest web --typescript --eslint --app --src-dir --import-alias "@/*" --use-npm --no-tailwind
```
If it asks extra questions (for example about React Compiler or a linter), choose the defaults / **No** for the compiler. Afterwards run these and paste the output, so I can match your exact versions:
```
cat web/package.json
cat web/tsconfig.json
ls web web/src/app
node --version
```

---

# Part 3 - Every file (what it does, then the exact code)

Backend files changed today: **none**. Frontend: 4 scaffold files replaced + 15 new. Then CI and README.

| # | File (inside `web/`) | New or replaced | Job |
|---|---|---|---|
| 1 | `next.config.ts` | REPLACES the scaffold's file | Forwards `/api/...` to FastAPI. This is what makes the browser talk to one origin only. |
| 2 | `src/lib/types.ts` | new | TypeScript descriptions of every JSON shape the API returns. A mistake like `doc.extractoin` becomes a red underline instead of a blank screen. |
| 3 | `src/lib/auth.ts` | new | Keeps the login token in the browser tab (`sessionStorage`). |
| 4 | `src/lib/format.ts` | new | Money, dates, status colours. No React, so it is easy to test. |
| 5 | `src/lib/api.ts` | new | The single door to the backend: adds the token, turns errors into readable messages. |
| 6 | `src/lib/usePolled.ts` | new | A reusable hook: load once, and keep asking while the server is still working. |
| 7 | `src/components/StatusBadge.tsx` | new | The coloured status label. |
| 8 | `src/components/AppHeader.tsx` | new | Top bar: product name, company and e-mail, Sign out. |
| 9 | `src/components/UploadForm.tsx` | new | File picker + Upload button. |
| 10 | `src/components/IssueList.tsx` | new | Lists the checking code's findings. |
| 11 | `src/components/ExtractionView.tsx` | new | What was read: header fields, charge lines, checks. |
| 12 | `src/components/ReconciliationView.tsx` | new | The invoice-versus-quote result. |
| 13 | `src/components/ReconcileBox.tsx` | new | The Compare button and the sentence explaining the outcome. |
| 14 | `src/components/ReviewPanel.tsx` | new | The review screen proper: approve, correct or reject. |
| 15 | `src/app/layout.tsx` | REPLACES the scaffold's file | The page shell (title, language, stylesheet). |
| 16 | `src/app/globals.css` | REPLACES the scaffold's file | All styling, light and dark. |
| 17 | `src/app/page.tsx` | REPLACES the scaffold's file | The home page: upload + the list of documents. |
| 18 | `src/app/login/page.tsx` | new | Sign in / create a company account. |
| 19 | `src/app/documents/[id]/page.tsx` | new | One document: status, review panel, results, reconcile, history. |

## Reading guide: the four ideas that matter most

**1. `api.ts` is the only door.** No component calls `fetch`. Every request goes through `request()`, which (a) adds `Authorization: Bearer <token>`, (b) refuses to call the server without a token, (c) turns FastAPI's two error shapes into one readable sentence, (d) clears a dead token on 401. Upload sends `FormData` and sets *no* `Content-Type`: the browser must add it itself, because it includes a random boundary.

**2. `usePolled` is the "live" feeling.** `fetcher` loads; if `keepPolling(value)` is true, a timer calls `load` again in 3 s. The effect's clean-up sets `cancelled = true` and clears the timer, so leaving the page stops the polling, and an old slow response can never overwrite newer data. `reload()` bumps a counter, which restarts the effect: that is how an upload or a review refreshes the page instantly. Because the effect restarts when `fetcher` changes, callers must pass a stable function (`useCallback`, or a function defined outside the component).

**3. The review panel resets by `key`.** After a correction that still has errors, the server asks again with the remaining findings. The page renders `<ReviewPanel key={JSON.stringify(doc.pending_review)} .../>`: a new question means a new key, so React throws away the old text box content and starts with the new values. Without this you would keep staring at your own old edit.

**4. The server stays the judge.** The form disables *Approve* when errors exist and there is no note, but that is only courtesy. The same rule is enforced by the backend, and a rejected answer comes back as a readable message in the red box. A correction goes through the same `validate()` as the model's reading. The UI adds no business rules.

## Safe by default
- Document text and notes are rendered as React text, never as HTML (no `dangerouslySetInnerHTML` anywhere).
- The browser cannot choose who the reviewer is (`ReviewDecision` has no such field, and the backend would answer 422 if it did).
- A 401 anywhere clears the token and goes to `/login`.

## Known limits of the screens (honest list for the README)
- **The reviewer cannot see the original file next to the values.** There is no download endpoint yet. A proper review screen shows the PDF beside the extracted fields; the natural next step is `GET /documents/{id}/file` plus a viewer.
- The list shows the latest 50 documents (no paging controls).
- Polling, not push; the token is in `sessionStorage`; "Correct" asks for raw JSON (a field-by-field form is a nice upgrade).
- Not tested in a real browser by me; no automated UI tests yet (the CI job checks lint, types and build only).

---

## The code

### 1. `web/next.config.ts` (REPLACES the scaffold's file)
Forwards `/api/...` to FastAPI. This is what makes the browser talk to one origin only.

```ts
import type { NextConfig } from "next";

// Where the FastAPI server lives. The browser never talks to it directly: it calls /api/..., and Next.js
// forwards the request. That keeps everything on one origin, so the API needs no CORS settings, and it is
// the same shape we will use when a load balancer routes /api to the backend after deployment.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
```

### 2. `web/src/lib/types.ts` (new)
TypeScript descriptions of every JSON shape the API returns. A mistake like `doc.extractoin` becomes a red underline instead of a blank screen.

```ts
// The shapes the FastAPI backend returns (src/freight_intel/schemas/documents.py and schemas/auth.py, user.py).
// They are written out by hand, so when a backend schema changes, change it here too.
// Money is always an integer in minor units (cents), with the currency next to it.

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface MeResponse {
  user_id: string;
  email: string;
  role: string;
  tenant_id: string;
  tenant_name: string;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  doc_type: string; // unknown until it has been read, then quote | invoice | rate_sheet
  status: string; // uploaded | processing | needs_review | processed | rejected | failed
  created_at: string; // ISO date-time
}

export interface Issue {
  code: string;
  message: string;
  severity: string; // "error" | "warning"
  field: string | null;
}

export interface Charge {
  position: number;
  code: string; // canonical charge name, "OTHER" when the label was not recognised
  label: string; // exactly as printed
  amount_minor: number | null; // null = the amount could not be read
  known: boolean;
}

export interface Extraction {
  id: string;
  status: string; // ok | needs_review | reviewed
  doc_type: string;
  reference: string | null;
  quote_reference: string | null;
  doc_date: string | null;
  valid_until: string | null;
  currency: string | null;
  origin: string | null;
  destination: string | null;
  equipment: string | null;
  total_minor: number | null; // the total as PRINTED on the document
  issues: Issue[];
  charges: Charge[];
}

export interface Discrepancy {
  position: number;
  type: string;
  charge_code: string | null;
  label: string | null;
  quoted_minor: number | null;
  invoiced_minor: number | null;
  variance_minor: number | null;
  note: string;
  explanation: string | null;
}

export interface Reconciliation {
  id: string;
  quote_document_id: string;
  match_method: string;
  currency: string | null;
  total_variance_minor: number | null;
  status: string; // clean | has_discrepancies
  discrepancies: Discrepancy[];
}

export interface ReviewRecord {
  action: string; // approve | correct | reject
  note: string;
  reviewer_id: string;
  created_at: string;
  corrected: boolean; // true when this decision replaced the extracted values
}

// What a person must answer while a document is paused (pipeline/review.py: build_review_request).
// `extraction` is in the model's text shape: the same shape a correction must be sent back in.
export interface PendingReview {
  doc_type: string;
  extraction: Record<string, unknown>;
  issues: Issue[];
  attempts: number;
  error?: string; // set when the last answer could not be used
}

export interface DocumentDetail extends DocumentSummary {
  extraction: Extraction | null;
  reconciliation: Reconciliation | null;
  reviews: ReviewRecord[];
  pending_review: PendingReview | null;
}

export interface UploadResponse {
  id: string;
  status: string;
}

export interface ReviewDecision {
  action: "approve" | "correct" | "reject";
  note: string;
  extraction?: Record<string, unknown>; // "correct" only: the whole corrected extraction
}

export interface ReviewResponse {
  document_status: string;
  question: PendingReview | null; // set while the person is asked again; null when the review is over
}

export interface ReconcileResponse {
  // reconciled | reference_not_found | ambiguous | no_candidate | route_unknown | unreadable_amount
  status: string;
  reconciliation_id: string | null;
  discrepancy_count: number;
}
```

### 3. `web/src/lib/auth.ts` (new)
Keeps the login token in the browser tab (`sessionStorage`).

```ts
// Where the login token is kept in the browser.
//
// sessionStorage lives as long as the tab: close the tab and you are signed out. That is simple and fine for
// a demo, but any script running on the page could read it (cross-site scripting). A production app would
// keep the token in an httpOnly cookie that JavaScript cannot read. Every access is wrapped in try/catch
// because browsers can block storage (private windows, strict settings).

const KEY = "freightlens_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null; // during server rendering there is no browser
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.sessionStorage.setItem(KEY, token);
  } catch {
    // storage blocked: the user has to sign in again on the next page load
  }
}

export function clearToken(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // nothing to clear
  }
}
```

### 4. `web/src/lib/format.ts` (new)
Money, dates, status colours. No React, so it is easy to test.

```ts
// Small display helpers. No React in here, so they are easy to test and reuse.

const FALLBACK_DIGITS = 2;

/** 219000 + "USD" -> "$2,190.00". The API sends integers in minor units; the number of decimals depends on the currency. */
export function formatMoney(minor: number | null | undefined, currency: string | null | undefined): string {
  if (minor === null || minor === undefined) return "—";
  const code = currency && /^[A-Za-z]{3}$/.test(currency) ? currency.toUpperCase() : null;
  if (code) {
    try {
      const formatter = new Intl.NumberFormat("en-US", { style: "currency", currency: code });
      const digits = formatter.resolvedOptions().maximumFractionDigits ?? FALLBACK_DIGITS;
      return formatter.format(minor / 10 ** digits);
    } catch {
      // an unknown currency code: fall through to the plain format below
    }
  }
  const plain = (minor / 10 ** FALLBACK_DIGITS).toFixed(FALLBACK_DIGITS);
  return code ? `${plain} ${code}` : plain;
}

/** Like formatMoney, but a difference always shows its sign: "+$5.00" or "-$12.50". */
export function formatVariance(minor: number | null | undefined, currency: string | null | undefined): string {
  if (minor === null || minor === undefined) return "—";
  const text = formatMoney(minor, currency);
  return minor > 0 ? `+${text}` : text;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

/** "needs_review" -> "needs review" */
export function humanize(value: string): string {
  return value.replace(/_/g, " ");
}

/** Statuses where the server is still working, so a page should keep asking for news. */
const BUSY = new Set(["uploaded", "processing"]);

export function isBusy(status: string): boolean {
  return BUSY.has(status);
}

export type Tone = "good" | "warn" | "bad" | "busy" | "neutral";

export function statusTone(status: string): Tone {
  switch (status) {
    case "processed":
    case "ok":
    case "reviewed":
    case "clean":
      return "good";
    case "needs_review":
    case "has_discrepancies":
      return "warn";
    case "failed":
    case "rejected":
      return "bad";
    case "uploaded":
    case "processing":
      return "busy";
    default:
      return "neutral";
  }
}
```

### 5. `web/src/lib/api.ts` (new)
The single door to the backend: adds the token, turns errors into readable messages.

```ts
// Every call to the backend goes through this file, so the token header, the error handling and the URL
// prefix exist in exactly one place. Pages and components never use fetch() themselves.

import { clearToken, getToken, setToken } from "./auth";
import type {
  DocumentDetail,
  DocumentSummary,
  MeResponse,
  ReconcileResponse,
  ReviewDecision,
  ReviewResponse,
  TokenResponse,
  UploadResponse,
} from "./types";

const BASE = "/api"; // next.config.ts forwards this to the FastAPI server

export class ApiError extends Error {
  status: number; // 0 = the server could not be reached at all

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/** A sentence that is safe to show a person, whatever was thrown. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

// FastAPI sends {"detail": "text"} for errors we raise, and {"detail": [{"msg": "..."}]} when the request
// itself does not match the schema.
function describe(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: { msg?: unknown }) => (typeof item?.msg === "string" ? item.msg : ""))
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (authenticated) {
    const token = getToken();
    if (!token) throw new ApiError(401, "Please sign in");
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the API running?");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401 && authenticated) clearToken(); // the token expired or is invalid
    // When the API is down, the Next.js proxy answers with a plain-text 500: no JSON, so no "detail".
    const fallback =
      response.status >= 500
        ? `The server did not answer properly (${response.status}). Is the API running?`
        : `The request failed (${response.status})`;
    throw new ApiError(response.status, describe(body?.detail, fallback));
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown, authenticated = true): Promise<T> {
  return request<T>(
    path,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    authenticated,
  );
}

// --- sign in -----------------------------------------------------------------------------------------

export async function signIn(email: string, password: string): Promise<void> {
  const token = await postJson<TokenResponse>("/auth/login", { email, password }, false);
  setToken(token.access_token);
}

export async function signUp(companyName: string, email: string, password: string): Promise<void> {
  const token = await postJson<TokenResponse>(
    "/auth/register",
    { company_name: companyName, email, password },
    false,
  );
  setToken(token.access_token);
}

export function signOut(): void {
  clearToken();
}

export function getMe(): Promise<MeResponse> {
  return request<MeResponse>("/me");
}

// --- documents ---------------------------------------------------------------------------------------

export function listDocuments(): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>("/documents?limit=50");
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`);
}

export function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file); // the field name must match the parameter name in the FastAPI route
  // No Content-Type header here: the browser adds it, including the boundary that separates the parts.
  return request<UploadResponse>("/documents", { method: "POST", body: form });
}

export function submitReview(id: string, decision: ReviewDecision): Promise<ReviewResponse> {
  // Who is reviewing is never sent: the server takes it from the login token.
  return postJson<ReviewResponse>(`/documents/${encodeURIComponent(id)}/review`, decision);
}

export function reconcileDocument(id: string): Promise<ReconcileResponse> {
  return postJson<ReconcileResponse>(`/documents/${encodeURIComponent(id)}/reconcile`, {});
}
```

### 6. `web/src/lib/usePolled.ts` (new)
A reusable hook: load once, and keep asking while the server is still working.

```ts
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { errorMessage, isUnauthorized } from "./api";

/**
 * Load something from the API and keep it fresh while it is still changing.
 *
 * - `fetcher` must be stable (wrap it in useCallback), or the effect would restart on every render.
 * - `keepPolling(value)` says whether the server is still working; if so, ask again after `intervalMs`.
 * - A 401 sends the person to the login page. Any other error is returned as text, and polling stops.
 * - `reload()` fetches again right now (after an upload, a review, a reconcile, or the Retry button).
 */
export function usePolled<T>(fetcher: () => Promise<T>, keepPolling: (value: T) => boolean, intervalMs = 3000) {
  const router = useRouter();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      try {
        const value = await fetcher();
        if (cancelled) return;
        setData(value);
        setError(null);
        if (keepPolling(value)) timer = setTimeout(load, intervalMs);
      } catch (err) {
        if (cancelled) return;
        if (isUnauthorized(err)) router.replace("/login");
        else setError(errorMessage(err));
      }
    }

    load();
    return () => {
      cancelled = true; // a later response must not overwrite a newer page
      if (timer) clearTimeout(timer);
    };
  }, [fetcher, keepPolling, intervalMs, router, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, reload };
}
```

### 7. `web/src/components/StatusBadge.tsx` (new)
The coloured status label.

```tsx
import { humanize, statusTone } from "@/lib/format";

/** A small coloured label for a status. The colour is only a hint: the words carry the meaning. */
export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${statusTone(status)}`}>{humanize(status)}</span>;
}
```

### 8. `web/src/components/AppHeader.tsx` (new)
Top bar: product name, company and e-mail, Sign out.

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getMe, isUnauthorized, signOut } from "@/lib/api";
import type { MeResponse } from "@/lib/types";

/** The bar at the top of every signed-in page: the product name, who you are, and Sign out. */
export function AppHeader() {
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((value) => {
        if (!cancelled) setMe(value);
      })
      .catch((err) => {
        if (!cancelled && isUnauthorized(err)) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  function handleSignOut() {
    signOut();
    router.push("/login");
  }

  return (
    <header className="topbar">
      <Link href="/" className="brand">
        FreightLens
      </Link>
      <div className="topbar-right">
        {me && (
          <span className="muted">
            {me.tenant_name} · {me.email}
          </span>
        )}
        <button type="button" className="button-secondary" onClick={handleSignOut}>
          Sign out
        </button>
      </div>
    </header>
  );
}
```

### 9. `web/src/components/UploadForm.tsx` (new)
File picker + Upload button.

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { errorMessage, isUnauthorized, uploadDocument } from "@/lib/api";

/** Choose a file and send it. The server answers at once; reading happens in the background. */
export function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadDocument(file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = ""; // empty the file picker
      onUploaded();
    } catch (err) {
      if (isUnauthorized(err)) router.replace("/login");
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card upload" onSubmit={handleSubmit}>
      <label htmlFor="file">Upload a quote or an invoice (PDF, Excel or e-mail)</label>
      <div className="row">
        <input
          id="file"
          ref={inputRef}
          type="file"
          accept=".pdf,.xlsx,.eml"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <button type="submit" disabled={!file || busy}>
          {busy ? "Uploading…" : "Upload"}
        </button>
      </div>
      {error && (
        <p className="callout callout-bad" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
```

### 10. `web/src/components/IssueList.tsx` (new)
Lists the checking code's findings.

```tsx
import type { Issue } from "@/lib/types";

/** The findings of the checking code. Errors must be fixed or explained; warnings are for information. */
export function IssueList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return <p className="muted">No findings.</p>;
  return (
    <ul className="issues">
      {issues.map((issue, index) => (
        <li key={`${issue.code}-${index}`} className={issue.severity === "error" ? "issue-error" : "issue-warning"}>
          <strong>{issue.severity}</strong> · {issue.message}
          {issue.field && <span className="muted"> ({issue.field})</span>}
        </li>
      ))}
    </ul>
  );
}
```

### 11. `web/src/components/ExtractionView.tsx` (new)
What was read: header fields, charge lines, checks.

```tsx
import { formatMoney } from "@/lib/format";
import type { Extraction } from "@/lib/types";
import { IssueList } from "./IssueList";
import { StatusBadge } from "./StatusBadge";

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || "—"}</dd>
    </div>
  );
}

/** What was read from the document: the header fields, the charge lines and the checking findings. */
export function ExtractionView({ extraction }: { extraction: Extraction }) {
  const isInvoice = extraction.doc_type === "invoice";
  return (
    <section className="card">
      <h2>
        What was read <StatusBadge status={extraction.status} />
      </h2>
      <dl className="fields">
        <Field label={isInvoice ? "Invoice number" : "Quote number"} value={extraction.reference} />
        {isInvoice && <Field label="Quote cited" value={extraction.quote_reference} />}
        <Field label="Date" value={extraction.doc_date} />
        {!isInvoice && <Field label="Valid until" value={extraction.valid_until} />}
        <Field label="Currency" value={extraction.currency} />
        <Field label="From" value={extraction.origin} />
        <Field label="To" value={extraction.destination} />
        <Field label="Container" value={extraction.equipment} />
        <Field label="Total printed" value={formatMoney(extraction.total_minor, extraction.currency)} />
      </dl>

      <h3>Charges</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>As printed</th>
              <th>Recognised as</th>
              <th className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {extraction.charges.map((charge) => (
              <tr key={charge.position}>
                <td>{charge.position}</td>
                <td>{charge.label}</td>
                <td>{charge.known ? charge.code : <span className="issue-warning">not recognised</span>}</td>
                <td className="num">
                  {charge.amount_minor === null ? (
                    <span className="issue-error">unreadable</span>
                  ) : (
                    formatMoney(charge.amount_minor, extraction.currency)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Checks</h3>
      <IssueList issues={extraction.issues} />
    </section>
  );
}
```

### 12. `web/src/components/ReconciliationView.tsx` (new)
The invoice-versus-quote result.

```tsx
import Link from "next/link";
import { formatMoney, formatVariance, humanize } from "@/lib/format";
import type { Reconciliation } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

/** The invoice compared with its quote. Every number here was computed by code; the wording is only an explanation. */
export function ReconciliationView({ reconciliation }: { reconciliation: Reconciliation }) {
  const { currency } = reconciliation;
  return (
    <section className="card">
      <h2>
        Invoice versus quote <StatusBadge status={reconciliation.status} />
      </h2>
      <p>
        Matched to <Link href={`/documents/${reconciliation.quote_document_id}`}>this quote</Link> by{" "}
        {humanize(reconciliation.match_method)}. Total difference:{" "}
        <strong>{formatVariance(reconciliation.total_variance_minor, currency)}</strong>
      </p>

      {reconciliation.discrepancies.length === 0 ? (
        <p className="muted">No differences found.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Finding</th>
                <th>Charge</th>
                <th className="num">Quoted</th>
                <th className="num">Invoiced</th>
                <th className="num">Difference</th>
              </tr>
            </thead>
            <tbody>
              {reconciliation.discrepancies.map((item) => (
                <tr key={item.position}>
                  <td>
                    <strong>{humanize(item.type.toLowerCase())}</strong>
                    <div className="muted">{item.explanation ?? item.note}</div>
                  </td>
                  <td>{item.label ?? item.charge_code ?? "—"}</td>
                  <td className="num">{formatMoney(item.quoted_minor, currency)}</td>
                  <td className="num">{formatMoney(item.invoiced_minor, currency)}</td>
                  <td className="num">{formatVariance(item.variance_minor, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
```

### 13. `web/src/components/ReconcileBox.tsx` (new)
The Compare button and the sentence explaining the outcome.

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { errorMessage, isUnauthorized, reconcileDocument } from "@/lib/api";

// Not finding exactly one safe quote is an outcome, not an error (the server answers 200), so each one
// gets a plain sentence.
const OUTCOMES: Record<string, string> = {
  reconciled: "Compared with the quote. The findings are shown below.",
  reference_not_found: "The invoice cites a quote that has not been uploaded (or is not unique). Upload that quote first.",
  route_unknown: "The invoice names no quote and its ports, container or date could not be read, so no quote can be matched safely.",
  ambiguous: "More than one quote fits this invoice's route, so none was chosen. The invoice would need to cite its quote.",
  no_candidate: "No quote for this route has been uploaded yet.",
  unreadable_amount: "A charge amount could not be read, so the comparison was not made.",
};

/** The button that compares an invoice with its quote, and the sentence that says what came of it. */
export function ReconcileBox({
  documentId,
  hasResult,
  onDone,
}: {
  documentId: string;
  hasResult: boolean;
  onDone: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const outcome = await reconcileDocument(documentId);
      setMessage(OUTCOMES[outcome.status] ?? `Result: ${outcome.status}`);
      onDone();
    } catch (err) {
      if (isUnauthorized(err)) router.replace("/login");
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Compare with the quote</h2>
      <p className="muted">
        Finds the quote this invoice belongs to and lists every difference. Only readings that passed the checks, or
        that a person reviewed, are used.
      </p>
      <button type="button" onClick={handleClick} disabled={busy}>
        {busy ? "Comparing…" : hasResult ? "Compare again" : "Compare with quote"}
      </button>
      {message && <p className="callout">{message}</p>}
      {error && (
        <p className="callout callout-bad" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
```

### 14. `web/src/components/ReviewPanel.tsx` (new)
The review screen proper: approve, correct or reject.

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { errorMessage, isUnauthorized, submitReview } from "@/lib/api";
import type { PendingReview, ReviewDecision, ReviewResponse } from "@/lib/types";
import { IssueList } from "./IssueList";

type Mode = "approve" | "correct" | "reject";

const MODES: { value: Mode; title: string; help: string }[] = [
  { value: "approve", title: "Approve", help: "The reading is a faithful copy of the document, even if the document itself has a problem." },
  { value: "correct", title: "Correct", help: "Fix the values below. The same checks run again on what you send." },
  { value: "reject", title: "Reject", help: "Do not use this document." },
];

/**
 * The question a paused document is waiting on, and the three ways to answer it.
 *
 * The page gives this component a `key` built from the question, so when the server asks again after a
 * correction that still has errors, the panel starts over with the new values instead of showing old text.
 */
export function ReviewPanel({
  documentId,
  pending,
  onDone,
}: {
  documentId: string;
  pending: PendingReview;
  onDone: (result: ReviewResponse) => void;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("approve");
  const [note, setNote] = useState("");
  const [json, setJson] = useState(() => JSON.stringify(pending.extraction, null, 2));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasErrors = pending.issues.some((issue) => issue.severity === "error");
  // The server enforces this too; the form just saves a round trip.
  const needsNote = mode === "approve" && hasErrors && note.trim() === "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const decision: ReviewDecision = { action: mode, note: note.trim() };
    if (mode === "correct") {
      try {
        const parsed: unknown = JSON.parse(json);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          setError("The corrected values must be a JSON object, like the one shown.");
          return;
        }
        decision.extraction = parsed as Record<string, unknown>;
      } catch {
        setError("That is not valid JSON. Check for a missing quote, comma or bracket.");
        return;
      }
    }

    setBusy(true);
    try {
      onDone(await submitReview(documentId, decision));
    } catch (err) {
      if (isUnauthorized(err)) router.replace("/login");
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card card-attention">
      <h2>This document needs a person</h2>
      <p>
        The checks still found problems after {pending.attempts} {pending.attempts === 1 ? "try" : "tries"}. Decide what
        should happen. Your name is recorded with the decision.
      </p>
      {pending.error && (
        <p className="callout callout-bad" role="alert">
          The last answer could not be used: {pending.error}
        </p>
      )}
      <IssueList issues={pending.issues} />

      <form onSubmit={handleSubmit}>
        <fieldset className="modes">
          <legend>Your decision</legend>
          {MODES.map((item) => (
            <label key={item.value} className={mode === item.value ? "mode mode-selected" : "mode"}>
              <input
                type="radio"
                name="mode"
                value={item.value}
                checked={mode === item.value}
                onChange={() => setMode(item.value)}
              />
              <span>
                <strong>{item.title}</strong>
                <span className="muted"> — {item.help}</span>
              </span>
            </label>
          ))}
        </fieldset>

        {mode === "correct" && (
          <>
            <label htmlFor="corrected">Corrected values (JSON, every field present)</label>
            <textarea
              id="corrected"
              className="code"
              rows={16}
              spellCheck={false}
              value={json}
              onChange={(event) => setJson(event.target.value)}
            />
          </>
        )}

        <label htmlFor="note">
          Note {mode === "approve" && hasErrors ? "(required: say why you approve despite the errors)" : "(optional)"}
        </label>
        <textarea
          id="note"
          rows={3}
          maxLength={1000}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />

        {error && (
          <p className="callout callout-bad" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || needsNote}>
          {busy ? "Saving…" : "Save decision"}
        </button>
      </form>
    </section>
  );
}
```

### 15. `web/src/app/layout.tsx` (REPLACES the scaffold's file)
The page shell (title, language, stylesheet).

```tsx
import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "FreightLens",
  description: "Upload freight documents, review what the model could not settle, and compare invoices with quotes.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

### 16. `web/src/app/globals.css` (REPLACES the scaffold's file)
All styling, light and dark.

```css
/* Plain CSS, no framework: the whole look of the app is in this one file. */

:root {
  --bg: #f6f7f9;
  --card: #ffffff;
  --text: #1c2430;
  --muted: #5f6b7a;
  --line: #dde2e8;
  --accent: #1f5fbf;
  --accent-text: #ffffff;
  --good-bg: #e3f4e8;
  --good-text: #1d6b37;
  --warn-bg: #fdf0d5;
  --warn-text: #8a5a00;
  --bad-bg: #fbe3e1;
  --bad-text: #a02a21;
  --busy-bg: #e5edfb;
  --busy-text: #25508f;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12161c;
    --card: #1b2129;
    --text: #e6eaf0;
    --muted: #97a3b3;
    --line: #2d3641;
    --accent: #5b9bf0;
    --accent-text: #0c1117;
    --good-bg: #17331f;
    --good-text: #7fd39a;
    --warn-bg: #3a2c0c;
    --warn-text: #f0c26a;
    --bad-bg: #3d1a17;
    --bad-text: #f19a93;
    --busy-bg: #172a47;
    --busy-text: #8db8f5;
  }
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

main {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 64px;
}

main.narrow {
  max-width: 440px;
  padding-top: 64px;
}

h1 {
  font-size: 1.6rem;
  margin: 8px 0;
}
h2 {
  font-size: 1.15rem;
  margin: 0 0 12px;
}
h3 {
  font-size: 1rem;
  margin: 20px 0 8px;
}

a {
  color: var(--accent);
}

.muted {
  color: var(--muted);
}

/* top bar */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: var(--card);
  border-bottom: 1px solid var(--line);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.9rem;
}
.brand {
  font-weight: 700;
  text-decoration: none;
  color: var(--text);
}

/* cards */
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
}
.card-attention {
  border-color: var(--warn-text);
}

/* forms */
label {
  display: block;
  font-weight: 600;
  margin: 12px 0 4px;
}
input[type="text"],
input[type="email"],
input[type="password"],
input:not([type]),
textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text);
  font: inherit;
}
textarea.code {
  font: 0.85rem/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
}
input[type="file"] {
  max-width: 100%;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.upload label {
  margin-top: 0;
}

button {
  margin-top: 12px;
  padding: 8px 16px;
  border: 0;
  border-radius: 6px;
  background: var(--accent);
  color: var(--accent-text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.upload button {
  margin-top: 0;
}
.button-secondary {
  margin-top: 0;
  background: transparent;
  color: var(--text);
  border: 1px solid var(--line);
}
.button-link {
  margin-top: 0;
  padding: 0 4px;
  background: none;
  color: var(--accent);
  font-weight: 400;
  text-decoration: underline;
}

fieldset.modes {
  border: 1px solid var(--line);
  border-radius: 6px;
  margin: 16px 0 0;
  padding: 8px 12px 12px;
}
.mode {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-weight: 400;
  padding: 6px;
  border-radius: 6px;
}
.mode-selected {
  background: var(--busy-bg);
}

/* messages */
.callout {
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--busy-bg);
  color: var(--busy-text);
}
.callout-bad {
  background: var(--bad-bg);
  color: var(--bad-text);
}

/* status badge */
.badge {
  display: inline-block;
  padding: 1px 10px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  vertical-align: middle;
}
.badge-good {
  background: var(--good-bg);
  color: var(--good-text);
}
.badge-warn {
  background: var(--warn-bg);
  color: var(--warn-text);
}
.badge-bad {
  background: var(--bad-bg);
  color: var(--bad-text);
}
.badge-busy {
  background: var(--busy-bg);
  color: var(--busy-text);
}
.badge-neutral {
  background: var(--line);
  color: var(--muted);
}

/* tables */
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th {
  font-size: 0.85rem;
  color: var(--muted);
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* extraction fields */
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px 16px;
  margin: 0;
}
.fields dt {
  font-size: 0.8rem;
  color: var(--muted);
}
.fields dd {
  margin: 0;
  font-weight: 600;
}

/* findings and history */
.issues,
.history {
  padding-left: 20px;
  margin: 8px 0;
}
.issue-error {
  color: var(--bad-text);
}
.issue-warning {
  color: var(--warn-text);
}
```

### 17. `web/src/app/page.tsx` (REPLACES the scaffold's file)
The home page: upload + the list of documents.

```tsx
"use client";

import Link from "next/link";
import { useCallback } from "react";
import { AppHeader } from "@/components/AppHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { UploadForm } from "@/components/UploadForm";
import { listDocuments } from "@/lib/api";
import { formatDateTime, humanize, isBusy } from "@/lib/format";
import type { DocumentSummary } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

// Defined outside the component so it is the same function on every render (usePolled needs that).
const anyBusy = (rows: DocumentSummary[]) => rows.some((row) => isBusy(row.status));

export default function DocumentsPage() {
  const fetchDocuments = useCallback(() => listDocuments(), []);
  const { data: documents, error, reload } = usePolled(fetchDocuments, anyBusy);

  return (
    <>
      <AppHeader />
      <main>
        <h1>Documents</h1>
        <UploadForm onUploaded={reload} />

        {error && (
          <p className="callout callout-bad" role="alert">
            {error} <button type="button" className="button-link" onClick={reload}>Retry</button>
          </p>
        )}

        {documents === null && !error && <p className="muted">Loading…</p>}
        {documents !== null && documents.length === 0 && (
          <p className="muted">Nothing here yet. Upload a quote or an invoice above.</p>
        )}
        {documents !== null && documents.length > 0 && (
          <div className="card table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <Link href={`/documents/${doc.id}`}>{doc.filename}</Link>
                    </td>
                    <td>{humanize(doc.doc_type)}</td>
                    <td>
                      <StatusBadge status={doc.status} />
                    </td>
                    <td>{formatDateTime(doc.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  );
}
```

### 18. `web/src/app/login/page.tsx` (new)
Sign in / create a company account.

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { errorMessage, signIn, signUp } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [creating, setCreating] = useState(false); // false = sign in, true = create a company account
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (creating) await signUp(company.trim(), email.trim(), password);
      else await signIn(email.trim(), password);
      router.push("/");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="narrow">
      <h1>FreightLens</h1>
      <p className="muted">Read freight quotes and invoices, check them, and compare each invoice with its quote.</p>

      <form className="card" onSubmit={handleSubmit}>
        <h2>{creating ? "Create your company account" : "Sign in"}</h2>

        {creating && (
          <>
            <label htmlFor="company">Company name</label>
            <input id="company" required maxLength={200} value={company} onChange={(e) => setCompany(e.target.value)} />
          </>
        )}

        <label htmlFor="email">Email</label>
        <input id="email" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />

        <label htmlFor="password">Password{creating ? " (at least 12 characters)" : ""}</label>
        <input
          id="password"
          type="password"
          required
          minLength={creating ? 12 : 1}
          maxLength={128}
          autoComplete={creating ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && (
          <p className="callout callout-bad" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? "Please wait…" : creating ? "Create account" : "Sign in"}
        </button>
        <button
          type="button"
          className="button-link"
          onClick={() => {
            setCreating(!creating);
            setError(null);
          }}
        >
          {creating ? "I already have an account" : "Create a company account"}
        </button>
      </form>
    </main>
  );
}
```

### 19. `web/src/app/documents/[id]/page.tsx` (new)
One document: status, review panel, results, reconcile, history.

```tsx
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { ExtractionView } from "@/components/ExtractionView";
import { ReconcileBox } from "@/components/ReconcileBox";
import { ReconciliationView } from "@/components/ReconciliationView";
import { ReviewPanel } from "@/components/ReviewPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { getDocument } from "@/lib/api";
import { formatDateTime, humanize, isBusy } from "@/lib/format";
import type { DocumentDetail, ReviewResponse } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

const stillWorking = (doc: DocumentDetail) => isBusy(doc.status);

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const fetchDocument = useCallback(() => getDocument(id), [id]);
  const { data: doc, error, reload } = usePolled(fetchDocument, stillWorking);
  const [notice, setNotice] = useState<string | null>(null);

  function handleReviewed(result: ReviewResponse) {
    setNotice(
      result.question
        ? "Saved. The checks still found problems, so the corrected values are shown again."
        : `Saved. The document is now ${humanize(result.document_status)}.`,
    );
    reload();
  }

  // An invoice can be compared with its quote once its reading is settled (it passed the checks, or a person reviewed it).
  const canReconcile =
    doc?.extraction?.doc_type === "invoice" && ["ok", "reviewed"].includes(doc.extraction.status);

  return (
    <>
      <AppHeader />
      <main>
        <p>
          <Link href="/">← All documents</Link>
        </p>

        {error && (
          <p className="callout callout-bad" role="alert">
            {error} <button type="button" className="button-link" onClick={reload}>Retry</button>
          </p>
        )}
        {doc === null && !error && <p className="muted">Loading…</p>}

        {doc && (
          <>
            <h1>
              {doc.filename} <StatusBadge status={doc.status} />
            </h1>
            <p className="muted">
              {humanize(doc.doc_type)} · uploaded {formatDateTime(doc.created_at)}
            </p>

            {notice && <p className="callout">{notice}</p>}

            {isBusy(doc.status) && (
              <p className="callout">Reading the document. This page refreshes by itself.</p>
            )}
            {doc.status === "failed" && (
              <p className="callout callout-bad">
                Reading this document failed. Uploading the file again is the way to retry.
              </p>
            )}
            {doc.status === "rejected" && <p className="callout callout-bad">This document was rejected by a reviewer.</p>}

            {doc.status === "needs_review" && doc.pending_review && (
              <ReviewPanel
                // A new question (after a correction that still had errors) gives a new key: the panel starts fresh.
                key={JSON.stringify(doc.pending_review)}
                documentId={doc.id}
                pending={doc.pending_review}
                onDone={handleReviewed}
              />
            )}
            {doc.status === "needs_review" && !doc.pending_review && (
              <p className="callout callout-bad">
                This document is waiting, but it has no open question: the review ended without a decision. Upload the
                file again to start over.
              </p>
            )}

            {doc.extraction && <ExtractionView extraction={doc.extraction} />}

            {canReconcile && (
              <ReconcileBox documentId={doc.id} hasResult={doc.reconciliation !== null} onDone={reload} />
            )}
            {doc.reconciliation && <ReconciliationView reconciliation={doc.reconciliation} />}

            {doc.reviews.length > 0 && (
              <section className="card">
                <h2>Review history</h2>
                <ul className="history">
                  {doc.reviews.map((review) => (
                    <li key={`${review.created_at}-${review.action}`}>
                      <strong>{review.action}</strong>
                      {review.corrected ? " (values replaced)" : ""} · {formatDateTime(review.created_at)}
                      {review.note && <div className="muted">“{review.note}”</div>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </main>
    </>
  );
}
```

---

# Part 4 - CI, README, run instructions

## `.github/workflows/ci.yml` (append at the end, under `jobs:`, after a blank line)
It is a second job that runs next to `test`. The existing lines do not change.
```yaml
  # Checks the web app on every push: dependencies install cleanly, lint passes, types are correct,
  # and the production build succeeds. No API or database is needed for any of these.
  web:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: web/package-lock.json

      - name: Install exactly what package-lock.json says
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Type check
        run: npx tsc --noEmit

      - name: Production build
        run: npm run build
```
Note: `npm ci` needs `web/package-lock.json` committed (create-next-app makes it; commit it).

## `README.md` (exact edits)
1. Status paragraph (line ~16): replace `The review screen and cloud deployment are planned (see [Roadmap](#roadmap)).` with `A web app (sign in, upload, review, compare) is built on top of it; cloud deployment is planned (see [Roadmap](#roadmap)).`
2. New section after "The documents API": **"The web app"** - what the three screens do, that it talks to the API through a same-origin `/api` proxy, the demo path below, and the known limits above. (Screenshots are added at the end of the day, once you have taken them.)
3. Quick start: new step after the API step:
```
# 4b. run the web app (second terminal)
cd web && npm install
npm run dev                                       # http://localhost:3000, needs the API running on port 8000
```
4. Project layout: add the line `web/            Next.js + TypeScript web app (sign in, upload, review, compare)`.
5. Roadmap: change `Review screen (web UI) and demo | planned` to two rows: `Web app: sign in, upload, review, compare | done` and `Demo (screenshots, short video) | planned`.

`docs/design-doc.md` (one line, section "Frontend"): append `It calls the API through a same-origin /api proxy, so the API needs no CORS settings.`

## Run it (after "write it" and the scaffold)
Terminal 1 (repo root, venv active): `uvicorn freight_intel.api.main:app --reload`
Terminal 2: `cd web && npm run dev`, then open http://localhost:3000

## Demo path with your synthetic data
`python -m freight_intel.synth` already made `data/synthetic/cases/case-XXX/` with a `quote.*` and an `invoice.*` file (the formats vary per case: pdf or xlsx). A real model reads each upload, so each costs a few cents (needs `OPENAI_API_KEY` in `.env`).
1. Create a company account, and you land on Documents.
2. **Overcharge:** upload `case-004/quote.pdf`, then `case-004/invoice.xlsx`. Both become `processed`. Open the invoice, click *Compare with quote*: one overcharge finding appears (ISPS: quoted 20.00, invoiced 22.00).
3. **Review screen:** `ARITHMETIC_ERROR` cases (case-009, 018, 027, 036) have an invoice whose printed total does not add up. Upload `case-009/quote.xlsx` and `case-009/invoice.xlsx`. The invoice should stop at *needs review*. Open it, choose **Approve**, write "total on the document is wrong, reading is correct", save. Then *Compare with quote*: an arithmetic-error finding appears (printed total 99.00 lower than the sum of the lines).
4. Try **Correct** on another one: change a charge amount in the JSON and watch the checks run again.
(If a given case does not pause, the model read it fully correctly; try another case from the same list.)

## Troubleshooting
- "Cannot reach the server" / "Is the API running?" - uvicorn is not running on port 8000 (or `API_URL` is different).
- Upload answers "503" - `OPENAI_API_KEY` is missing in `.env`; restart uvicorn after adding it.
- Port 3000 busy - `npm run dev -- -p 3001`.
- Everything redirects to /login - the token expired (60 minutes) or the tab was closed; sign in again.