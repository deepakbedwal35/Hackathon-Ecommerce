import { test, describe, beforeEach, afterEach, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  formatAge,
  formatMoney,
  formatRefundReviewNotice,
  getEnumLabel,
  getRoleHomePath,
  mergeMessagesById,
} from "../utils/format.js";
import { api, setStoredToken } from "../api/client.js";
import { fetchMetaConfig, fetchMetaEnums } from "../hooks/useMeta.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const srcDir = path.resolve(__dirname, "..");

async function compileJsxToModule(relPath) {
  const fullPath = path.join(srcDir, relPath);
  const outDir = path.join(srcDir, "tests/.tmp_compiled");
  fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, `${path.basename(relPath, ".jsx")}.mjs`);
  await build({
    entryPoints: [fullPath],
    bundle: true,
    format: "esm",
    platform: "node",
    outfile: outFile,
    external: ["react", "react-dom", "react-router-dom"],
    jsx: "automatic",
  });
  return import(`${pathToFileURL(outFile).href}?t=${Date.now()}`);
}

describe("Role routing & meta helpers", () => {
  test("getRoleHomePath routes customer to / and agent/admin to /staff", () => {
    assert.equal(getRoleHomePath({ role: "customer" }), "/");
    assert.equal(getRoleHomePath({ role: "agent" }), "/staff");
    assert.equal(getRoleHomePath({ role: "admin" }), "/staff");
    assert.equal(getRoleHomePath(null), "/");
  });

  test("formatRefundReviewNotice renders rule dynamically in both modes", () => {
    const allModeText = formatRefundReviewNotice({
      refund_review_mode: "all",
      auto_refund_limit: 5000,
    });
    assert.equal(
      allModeText,
      "Every refund is reviewed and approved by our team before it is issued."
    );

    const aboveLimitText = formatRefundReviewNotice({
      refund_review_mode: "above_limit",
      auto_refund_limit: 5000,
    });
    assert.equal(
      aboveLimitText,
      "Refunds above INR 5,000 are reviewed by our team."
    );
  });

  test("getEnumLabel resolves matching option label and falls back safely", () => {
    const opts = [{ value: "order_issue", label: "Order issue" }];
    assert.equal(getEnumLabel(opts, "order_issue"), "Order issue");
    assert.equal(getEnumLabel(opts, "unknown_code"), "unknown code");
    assert.equal(getEnumLabel(null, "custom_status"), "custom status");
  });

  test("mergeMessagesById deduplicates polling responses and maintains chronological order", () => {
    const existing = [
      { id: "m1", content: "First", created_at: "2026-11-26T10:00:00Z" },
      { id: "m2", content: "Second", created_at: "2026-11-26T10:01:00Z" },
    ];
    const incoming = [
      { id: "m2", content: "Second", created_at: "2026-11-26T10:01:00Z" },
      { id: "m3", content: "Third", created_at: "2026-11-26T10:02:00Z" },
    ];
    const merged = mergeMessagesById(existing, incoming);
    assert.equal(merged.length, 3);
    assert.deepEqual(
      merged.map((m) => m.id),
      ["m1", "m2", "m3"]
    );
  });

  test("formatAge formats durations cleanly", () => {
    const now = new Date("2026-11-26T12:00:00Z").getTime();
    assert.equal(formatAge("2026-11-24T10:00:00Z", now), "2d 2h");
    assert.equal(formatAge("2026-11-26T09:30:00Z", now), "2h 30m");
    assert.equal(formatAge("2026-11-26T11:45:00Z", now), "15m");
  });
});

describe("API client meta, error handling, and staff endpoints", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setStoredToken("test-jwt-token");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    setStoredToken(null);
    fs.rmSync(path.join(srcDir, "tests/.tmp_compiled"), { recursive: true, force: true });
  });

  test("fetchMetaEnums loads options from /api/v1/meta/enums and fails loudly on HTTP 500", async () => {
    let callCount = 0;
    globalThis.fetch = async (url) => {
      callCount++;
      assert.ok(url.endsWith("/api/v1/meta/enums"));
      if (callCount === 1) {
        return new Response(
          JSON.stringify({ error: { code: "SERVER_ERROR", message: "Backend failed" } }),
          { status: 500, headers: { "content-type": "application/json" } }
        );
      }
      return new Response(
        JSON.stringify({
          ticket_categories: [
            { value: "order_issue", label: "Order issue" },
            { value: "refund", label: "Refund" },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    };

    await assert.rejects(() => fetchMetaEnums(true), (err) => {
      assert.equal(err.status, 500);
      return true;
    });

    const data = await fetchMetaEnums(true);
    assert.equal(data.ticket_categories.length, 2);
    assert.equal(data.ticket_categories[0].value, "order_issue");

    // Subsequent call uses in-memory cache (staleTime Infinity)
    const cached = await fetchMetaEnums(false);
    assert.equal(cached.ticket_categories.length, 2);
    assert.equal(callCount, 2);
  });

  test("fetchMetaConfig reads review mode and limit", async () => {
    globalThis.fetch = async (url) => {
      assert.ok(url.endsWith("/api/v1/meta/config"));
      return new Response(
        JSON.stringify({
          refund_review_mode: "all",
          auto_refund_limit: 5000,
          return_window_days: 30,
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    };

    const cfg = await fetchMetaConfig(true);
    assert.equal(cfg.refund_review_mode, "all");
    assert.equal(formatRefundReviewNotice(cfg), "Every refund is reviewed and approved by our team before it is issued.");
  });

  test("API client surfaces 403 and 500 errors instead of returning empty arrays", async () => {
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({ error: { code: "FORBIDDEN", message: "Customer role required." } }),
        { status: 403, headers: { "content-type": "application/json" } }
      );

    await assert.rejects(() => api.tickets.list(), (err) => {
      assert.equal(err.status, 403);
      assert.equal(err.code, "FORBIDDEN");
      return true;
    });

    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({ error: { code: "INTERNAL_ERROR", message: "Database unavailable" } }),
        { status: 500, headers: { "content-type": "application/json" } }
      );

    await assert.rejects(() => api.staff.overview(), (err) => {
      assert.equal(err.status, 500);
      return true;
    });
  });

  test("staff.listTickets and staff.getMessages serialize filters and after cursor", async () => {
    const requestedUrls = [];
    globalThis.fetch = async (url) => {
      requestedUrls.push(url);
      return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };

    await api.staff.listTickets({
      status: "escalated",
      priority: "urgent",
      has_escalation: "true",
      escalation_decision: "pending",
      assigned_to: "me",
      q: "earbuds",
      sort: "sla",
      page: 2,
    });

    assert.ok(requestedUrls[0].includes("status=escalated"));
    assert.ok(requestedUrls[0].includes("priority=urgent"));
    assert.ok(requestedUrls[0].includes("escalation_decision=pending"));
    assert.ok(requestedUrls[0].includes("assigned_to=me"));
    assert.ok(requestedUrls[0].includes("q=earbuds"));
    assert.ok(requestedUrls[0].includes("page=2"));

    await api.staff.getMessages("tick-123", "2026-11-26T10:00:00Z");
    assert.ok(
      requestedUrls[1].includes("/api/v1/staff/tickets/tick-123/messages?after=2026-11-26T10%3A00%3A00Z")
    );
  });

  test("staff.decideEscalation exposes 409 ALREADY_DECIDED and 502 PAYMENT_FAILED", async () => {
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({ error: { code: "ALREADY_DECIDED", message: "Already decided" } }),
        { status: 409, headers: { "content-type": "application/json" } }
      );

    await assert.rejects(
      () => api.staff.decideEscalation("esc-1", { decision: "approve", note: "Approved note" }),
      (err) => err.status === 409 && err.code === "ALREADY_DECIDED"
    );

    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({ error: { code: "PAYMENT_FAILED", message: "Gateway drop" } }),
        { status: 502, headers: { "content-type": "application/json" } }
      );

    await assert.rejects(
      () => api.staff.decideEscalation("esc-1", { decision: "approve", note: "Approved note" }),
      (err) => err.status === 502 && err.code === "PAYMENT_FAILED"
    );
  });
});

describe("React component rendering and structural invariants", () => {
  after(() => {
    fs.rmSync(path.join(srcDir, "tests/.tmp_compiled"), { recursive: true, force: true });
  });

  test("ConfirmationModal renders order number, exact amount, and required note input", async () => {
    const { ConfirmationModal } = await compileJsxToModule("components/staff/ConfirmationModal.jsx");
    const html = renderToStaticMarkup(
      React.createElement(ConfirmationModal, {
        open: true,
        title: "Confirm refund approval",
        description: "Approving refund of INR 8,999.00 for order ORD-1003.",
        confirmLabel: "Approve and issue refund",
        requireNote: true,
        onConfirm: () => {},
        onCancel: () => {},
      })
    );
    assert.ok(html.includes("Confirm refund approval"));
    assert.ok(html.includes("ORD-1003"));
    assert.ok(html.includes("8,999.00"));
    assert.ok(html.includes("<textarea"));
    assert.ok(html.includes("required"));
  });

  test("Dashboard, NewTicket, StaffTickets, StaffTicketDetail, Approvals, ApprovalDetail enforce UI rules", () => {
    const newTicketSrc = fs.readFileSync(path.join(srcDir, "pages/NewTicket.jsx"), "utf-8");
    assert.ok(!newTicketSrc.includes("refund_request"), "No hardcoded old category strings");
    assert.ok(newTicketSrc.includes("useMetaEnums"), "Must load enums from backend");
    assert.ok(newTicketSrc.includes("enumsLoading || Boolean(enumsError)"), "Disables select when meta fails");
    assert.ok(newTicketSrc.includes("refetchEnums"), "Provides Retry on enum fetch error");

    const dashboardSrc = fs.readFileSync(path.join(srcDir, "pages/Dashboard.jsx"), "utf-8");
    assert.ok(!dashboardSrc.includes(".catch(() => [])"), "Must not swallow API errors into empty arrays");
    assert.ok(dashboardSrc.includes("Unable to load dashboard"), "Must render error banner on failure");

    const approvalDetailSrc = fs.readFileSync(path.join(srcDir, "pages/staff/ApprovalDetail.jsx"), "utf-8");
    assert.ok(approvalDetailSrc.includes("Only an admin can approve or reject refunds."));
    assert.ok(approvalDetailSrc.includes("isAdmin &&"), "Approve and reject buttons hidden for non-admin");
    assert.ok(approvalDetailSrc.includes("submitting"), "Double click disabled while in flight");
    assert.ok(approvalDetailSrc.includes("The refund was NOT completed. The request is still open, you can retry."));
    assert.ok(approvalDetailSrc.includes("Another admin already decided this escalation."));

    const ticketDetailSrc = fs.readFileSync(path.join(srcDir, "pages/staff/StaffTicketDetail.jsx"), "utf-8");
    assert.ok(ticketDetailSrc.includes("allowed_transitions"), "Renders only allowed_transitions");
    assert.ok(!ticketDetailSrc.includes("dangerouslySetInnerHTML"), "Never renders raw HTML");
    assert.ok(ticketDetailSrc.includes("4000"), "Polls messages every 4 seconds");
    assert.ok(ticketDetailSrc.includes("mergeMessagesById"), "Merges messages without duplicates");
  });
});
