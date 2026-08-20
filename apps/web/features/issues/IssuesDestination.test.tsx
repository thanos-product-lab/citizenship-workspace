import "@testing-library/jest-dom/vitest";

import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery } from "@/test/render";

const get = vi.fn();
const post = vi.fn();
const client = { GET: get, POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { IssuesDestination } from "./IssuesDestination";

const CASE = "c1";

function anIssue(overrides: Record<string, unknown> = {}) {
  return {
    id: "i1",
    issue_type: "STALE_ASSESSMENT",
    severity: "ACTION_REQUIRED",
    status: "OPEN",
    dismissibility: "NOT_DISMISSIBLE",
    action_group: "CONFIRM_INFORMATION",
    title: "Recheck Total absences",
    body: "An input behind this conclusion changed, so it has not been rechecked.",
    impact: "Until it is rechecked, this conclusion may no longer match your case data.",
    affected_object_type: "Requirement",
    affected_object_id: "residence.total_absences",
    opened_at: "2026-08-20T10:00:00Z",
    resolved_at: null,
    reopened_at: null,
    has_recurred: false,
    resolutions: [],
    ...overrides,
  };
}

function aQueue(overrides: Record<string, unknown> = {}) {
  return { case_id: CASE, open_count: 0, groups: [], history: [], ...overrides };
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

function queueReturns(body: unknown) {
  get.mockResolvedValue({ data: body });
}

/** A payload the reader must refuse rather than render as an empty queue. */
function queueFails() {
  get.mockResolvedValue({ data: undefined, error: { detail: "boom" } });
}

describe("issues destination", () => {
  it("says nothing needs attention only when the queue actually loaded", async () => {
    queueReturns(aQueue());
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(await screen.findByText(/Nothing needs your attention/i)).toBeInTheDocument();
  });

  it("never renders a failed fetch as an empty queue", async () => {
    // Silence and "all clear" must not look alike: an unreachable queue cannot claim the
    // system looked and found nothing.
    queueFails();
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn’t be loaded/i);
    expect(screen.queryByText(/Nothing needs your attention/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("groups open issues by the action they need, with a real heading", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(
      await screen.findByRole("heading", { name: /confirm information/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Recheck Total absences/i })).toBeInTheDocument();
  });

  it("shows severity as a word, not only a colour", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(await screen.findByText("Needs an action")).toBeInTheDocument();
  });

  it("renders the server's wording and never composes its own", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(await screen.findByText(/has not been rechecked/i)).toBeInTheDocument();
    expect(screen.getByText(/may no longer match your case data/i)).toBeInTheDocument();
  });

  it("never implies the preserved conclusion still holds", async () => {
    // The trap StaleAssessmentNotice names: a stale conclusion has not been rechecked, so
    // nothing may describe it as standing, holding, or still valid.
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    const { container } = renderWithQuery(<IssuesDestination caseId={CASE} />);
    await screen.findByRole("heading", { name: /Recheck Total absences/i });

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/still (stands|holds|valid|applies)/i);
    expect(text).not.toMatch(/no longer valid/i);
  });

  it("marks an issue that has come back", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [
          { action_group: "CONFIRM_INFORMATION", issues: [anIssue({ has_recurred: true })] },
        ],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(await screen.findByText(/resolved before and has come back/i)).toBeInTheDocument();
  });

  it("keeps settled issues visible as history rather than deleting them", async () => {
    queueReturns(
      aQueue({
        history: [
          anIssue({ id: "i9", status: "RESOLVED", resolved_at: "2026-08-20T11:00:00Z" }),
        ],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(await screen.findByRole("heading", { name: /settled/i })).toBeInTheDocument();
    expect(screen.getByText(/Resolved/)).toBeInTheDocument();
  });

  it("links each issue back to what it is about", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    const link = await screen.findByRole("link", { name: /open total absences/i });
    expect(link).toHaveAttribute(
      "href",
      "/cases/c1/requirements/residence.total_absences",
    );
  });

  it("shows a count, never a fraction", async () => {
    queueReturns(
      aQueue({
        open_count: 2,
        groups: [
          {
            action_group: "CONFIRM_INFORMATION",
            issues: [anIssue(), anIssue({ id: "i2" })],
          },
        ],
      }),
    );
    const { container } = renderWithQuery(<IssuesDestination caseId={CASE} />);
    await screen.findByText("2 items");

    expect(container.textContent ?? "").not.toMatch(/\d+\s*\/\s*\d+/);
    expect(container.textContent ?? "").not.toMatch(/%/);
  });

  it("offers a recheck on a stale issue", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /recheck now/i })).toBeInTheDocument(),
    );
  });
});
