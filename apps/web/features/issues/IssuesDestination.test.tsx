import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor } from "@testing-library/react";
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

function queueReturns(body: unknown, overview: Record<string, unknown> | null = null) {
  get.mockImplementation((path: string) => {
    if (path === "/api/v1/cases/{case_id}/issues") return Promise.resolve({ data: body });
    if (path === "/api/v1/cases/{case_id}/overview") {
      return Promise.resolve({ data: overview ?? { groups: [], stale: 0 } });
    }
    return Promise.resolve({ data: undefined, error: {} });
  });
}

/** A payload the reader must refuse rather than render as an empty queue. */
function queueFails() {
  get.mockImplementation((path: string) => {
    if (path === "/api/v1/cases/{case_id}/issues") {
      return Promise.resolve({ data: undefined, error: { detail: "boom" } });
    }
    return Promise.resolve({ data: { groups: [], stale: 0 } });
  });
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

describe("issues destination accessibility", () => {
  it("nests a card title below its group heading rather than beside it", async () => {
    // A card title at the same level as the heading that contains it flattens the
    // outline, and the grouping-by-action this destination exists for disappears from
    // heading navigation.
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    await screen.findByRole("heading", { level: 3, name: /confirm information/i });
    expect(
      screen.getByRole("heading", { level: 4, name: /Recheck Total absences/i }),
    ).toBeInTheDocument();
  });

  it("names each issue card by its own title", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "CONFIRM_INFORMATION", issues: [anIssue()] }],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(
      await screen.findByRole("article", { name: /Recheck Total absences/i }),
    ).toBeInTheDocument();
  });

  it("offers one recheck for the group, not one per card", async () => {
    // Every stale issue is cleared by the same case-wide recalculation. N identically
    // named controls let a second fire while the first was in flight.
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
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    await screen.findAllByRole("article");
    expect(screen.getAllByRole("button", { name: /recheck now/i })).toHaveLength(1);
  });

  it("mounts the live region before it has anything to say", async () => {
    // A live region whose container and text arrive in the same commit is frequently
    // missed by NVDA and JAWS.
    queueReturns(aQueue());
    const { container } = renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(container.querySelector("[aria-live='polite']")).toBeInTheDocument();
    await screen.findByText(/Nothing needs your attention/i);
    expect(container.querySelector("[aria-live='polite']")).toBeInTheDocument();
  });

  it("announces what happened to the queue and returns focus to the heading", async () => {
    // The button that clears the queue is destroyed by the success it reports. Without a
    // region outside the card and a focus target, a screen-reader user hears nothing and
    // lands on <body>.
    // The queue must actually empty. The announcement is derived from the count changing,
    // not from a mutation callback — React Query drops mutate() callbacks when the calling
    // component unmounts, and clearing the queue unmounts the group the button lives in.
    // A mock that returns the same payload twice would let that defect pass, as it did.
    const populated = aQueue({
      open_count: 2,
      groups: [
        { action_group: "CONFIRM_INFORMATION", issues: [anIssue(), anIssue({ id: "i2" })] },
      ],
    });
    const cleared = aQueue({
      history: [anIssue({ status: "RESOLVED", resolved_at: "2026-08-20T11:00:00Z" })],
    });
    let recalculated = false;
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/cases/{case_id}/issues") {
        return Promise.resolve({ data: recalculated ? cleared : populated });
      }
      return Promise.resolve({ data: { groups: [], stale: 0 } });
    });
    post.mockImplementation(() => {
      recalculated = true;
      return Promise.resolve({ data: { requirements: [{ conclusion: "SUPPORTED" }] } });
    });
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    fireEvent.click(await screen.findByRole("button", { name: /recheck now/i }));

    await waitFor(() =>
      expect(screen.getByText(/2 issues resolved/i)).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { level: 2, name: "Issues" }),
      ),
    );
  });

  it("does not claim everything is current when conclusions are stale", async () => {
    // The queue is a write-time projection, so an empty queue is not by itself proof that
    // no conclusion is out of date.
    queueReturns(aQueue(), { groups: [], stale: 3 });
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    expect(
      await screen.findByText(/have not been rechecked since your inputs changed/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Every conclusion reached so far is current/i)).toBeNull();
  });
});

describe("dismissing an issue", () => {
  function dismissibleIssue(overrides: Record<string, unknown> = {}) {
    return anIssue({
      id: "i-dismissible",
      issue_type: "UNCERTAIN_TRAVEL_DATE",
      severity: "INFORMATION",
      dismissibility: "DISMISSIBLE",
      action_group: "FOR_YOUR_AWARENESS",
      title: "Your trip to Japan has uncertain dates",
      affected_object_type: "TravelRecord",
      affected_object_id: "rec-1",
      ...overrides,
    });
  }

  it("offers Dismiss only where the server says the issue may be set aside", async () => {
    queueReturns(
      aQueue({
        open_count: 2,
        groups: [
          { action_group: "CONFIRM_INFORMATION", issues: [anIssue()] },
          { action_group: "FOR_YOUR_AWARENESS", issues: [dismissibleIssue()] },
        ],
      }),
    );
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    // Two cards, one Dismiss: the control's absence mirrors the server's refusal.
    await screen.findAllByRole("article");
    expect(screen.getAllByRole("button", { name: /^dismiss$/i })).toHaveLength(1);
  });

  it("does not hide the card before the server has agreed", async () => {
    // Optimistic dismissal would show the item leaving the queue in exactly the cases the
    // server refuses — the one thing a dismissal must not do.
    let resolveDismiss: (value: unknown) => void = () => {};
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "FOR_YOUR_AWARENESS", issues: [dismissibleIssue()] }],
      }),
    );
    post.mockImplementation(() => new Promise((resolve) => (resolveDismiss = resolve)));
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    fireEvent.click(await screen.findByRole("button", { name: /^dismiss$/i }));

    await waitFor(() => expect(screen.getByText("Dismissing…")).toBeInTheDocument());
    expect(screen.getByRole("article", { name: /Japan/i })).toBeInTheDocument();
    resolveDismiss({ data: { id: "i-dismissible", status: "DISMISSED" } });
  });

  it("announces the dismissal from outside the card it removes", async () => {
    const populated = aQueue({
      open_count: 1,
      groups: [{ action_group: "FOR_YOUR_AWARENESS", issues: [dismissibleIssue()] }],
    });
    const cleared = aQueue({
      history: [dismissibleIssue({ status: "DISMISSED" })],
    });
    let dismissed = false;
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/cases/{case_id}/issues") {
        return Promise.resolve({ data: dismissed ? cleared : populated });
      }
      return Promise.resolve({ data: { groups: [], stale: 0 } });
    });
    post.mockImplementation(() => {
      dismissed = true;
      return Promise.resolve({ data: { id: "i-dismissible", status: "DISMISSED" } });
    });
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    fireEvent.click(await screen.findByRole("button", { name: /^dismiss$/i }));

    await waitFor(() =>
      expect(screen.getByText(/Japan has uncertain dates dismissed/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("heading", { name: /settled/i })).toBeInTheDocument();
  });

  it("says the issue is still open when dismissal fails", async () => {
    queueReturns(
      aQueue({
        open_count: 1,
        groups: [{ action_group: "FOR_YOUR_AWARENESS", issues: [dismissibleIssue()] }],
      }),
    );
    post.mockResolvedValue({ data: undefined, error: { detail: "nope" } });
    renderWithQuery(<IssuesDestination caseId={CASE} />);

    fireEvent.click(await screen.findByRole("button", { name: /^dismiss$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/still open/i);
    expect(screen.getByRole("article", { name: /Japan/i })).toBeInTheDocument();
  });
});
