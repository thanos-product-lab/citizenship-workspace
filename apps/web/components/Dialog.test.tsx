/**
 * The modal shell's own mechanics.
 *
 * These were untested until the release-slice accessibility pass, and the gap was a
 * specific shape rather than a general one: **the call sites were well covered and the
 * primitive was not.** `EvidenceDestination` and `TravelHistory` each assert where focus
 * lands after their dialog closes, because each answers that differently and correctly —
 * the heading when the row is gone, the Delete control when it is still there. What no
 * test anywhere exercised was the shell: the trap, Escape, the backdrop opt-out, the ARIA
 * wiring, the scroll lock.
 *
 * That matters because focus management regressed twice across milestones. Return-focus
 * is caller-owned by design (only the caller knows the trigger, and "back to the trigger"
 * is the wrong answer when the trigger no longer exists), so it is correctly tested per
 * call site. Everything the shell *does* own is tested here, once.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";
import { Dialog } from "./Dialog";

function Shell({
  onDismiss = () => {},
  dismissOnBackdrop,
  withInitialFocus = false,
  extraDisabled = false,
}: {
  onDismiss?: () => void;
  dismissOnBackdrop?: boolean;
  withInitialFocus?: boolean;
  extraDisabled?: boolean;
}) {
  const second = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open
      labelledBy="t"
      describedBy="d"
      onDismiss={onDismiss}
      {...(dismissOnBackdrop === undefined ? {} : { dismissOnBackdrop })}
      {...(withInitialFocus ? { initialFocusRef: second } : {})}
    >
      <h2 id="t">Title</h2>
      <p id="d">Description</p>
      <button type="button">first</button>
      <button type="button" ref={second} aria-disabled={extraDisabled}>
        second
      </button>
      <button type="button">last</button>
    </Dialog>
  );
}

describe("the dialog shell", () => {
  it("is a modal dialog named and described by the ids it was given", () => {
    render(<Shell />);
    const panel = screen.getByRole("dialog");
    expect(panel).toHaveAttribute("aria-modal", "true");
    expect(panel).toHaveAccessibleName("Title");
    expect(panel).toHaveAccessibleDescription("Description");
  });

  it("moves focus into the panel on open", () => {
    render(<Shell />);
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();
  });

  it("prefers the initial focus it was handed over the first focusable", () => {
    render(<Shell withInitialFocus />);
    expect(screen.getByRole("button", { name: "second" })).toHaveFocus();
  });

  it("wraps Tab from the last control back to the first", () => {
    render(<Shell />);
    const last = screen.getByRole("button", { name: "last" });
    last.focus();
    // `fireEvent` is the house convention, and here it is also the sharper instrument: the
    // trap is an `onKeyDown` handler that calls `preventDefault` and `focus()` itself, so
    // dispatching the key exercises the real mechanism rather than the environment's
    // sequential-navigation model, which jsdom does not have.
    fireEvent.keyDown(last, { key: "Tab" });
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();
  });

  it("wraps Shift+Tab from the first control back to the last", () => {
    render(<Shell />);
    const first = screen.getByRole("button", { name: "first" });
    first.focus();
    fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: "last" })).toHaveFocus();
  });

  /**
   * The property the `FOCUSABLE` selector exists for, and the one most likely to be
   * broken by someone "tidying" that selector: `[aria-disabled]` controls stay in the
   * cycle. This codebase prefers `aria-disabled` over `disabled` for busy states
   * precisely because a natively disabled control blurs to `<body>`, outside the panel,
   * taking the trap and Escape with it — so a selector that excluded `aria-disabled`
   * would reintroduce that bug by the back door.
   */
  it("keeps an aria-disabled control inside the trap", () => {
    // The aria-disabled control is deliberately the **last** focusable in this fixture,
    // which is what makes the assertion discriminate. If `FOCUSABLE` stopped matching
    // `[aria-disabled]`, the trap's idea of "last" would become the button above it, this
    // Tab would not match the wrap condition, and focus would not move — so the test fails
    // rather than passing for the wrong reason. An arrangement where the aria-disabled
    // control sits in the middle passes either way and proves nothing.
    render(
      <Dialog open labelledBy="t" onDismiss={() => {}}>
        <h2 id="t">Title</h2>
        <button type="button">first</button>
        <button type="button" aria-disabled>
          busy
        </button>
      </Dialog>,
    );
    const busy = screen.getByRole("button", { name: "busy" });
    expect(busy).not.toBeDisabled();
    busy.focus();
    fireEvent.keyDown(busy, { key: "Tab" });
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();
  });

  it("ignores a natively disabled control, which genuinely cannot hold focus", () => {
    // The other half of the same selector decision, and the reason it is not simply
    // "match everything": a `disabled` button cannot be focused, so including it would put
    // a dead stop in the cycle — Tab would wrap to something that refuses focus and leave
    // the user on `<body>`, behind the backdrop.
    render(
      <Dialog open labelledBy="t" onDismiss={() => {}}>
        <h2 id="t">Title</h2>
        <button type="button">first</button>
        <button type="button">middle</button>
        <button type="button" disabled>
          off
        </button>
      </Dialog>,
    );
    const middle = screen.getByRole("button", { name: "middle" });
    middle.focus();
    fireEvent.keyDown(middle, { key: "Tab" });
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();
  });

  it("dismisses on Escape", () => {
    const onDismiss = vi.fn();
    render(<Shell onDismiss={onDismiss} />);
    fireEvent.keyDown(screen.getByRole("button", { name: "first" }), { key: "Escape" });
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("dismisses on a backdrop press by default", () => {
    const onDismiss = vi.fn();
    const { container } = render(<Shell onDismiss={onDismiss} />);
    fireEvent.mouseDown(container.firstElementChild as HTMLElement);
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("ignores a backdrop press when the caller opted out", () => {
    const onDismiss = vi.fn();
    const { container } = render(<Shell onDismiss={onDismiss} dismissOnBackdrop={false} />);
    fireEvent.mouseDown(container.firstElementChild as HTMLElement);
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("does not treat a press that began inside the panel as a backdrop press", () => {
    // A drag that starts on the description and releases over the backdrop — selecting
    // text, usually — must not dismiss. The `e.target === e.currentTarget` guard is what
    // makes that true; without it, the bubbled event would read as a backdrop press.
    const onDismiss = vi.fn();
    render(<Shell onDismiss={onDismiss} />);
    fireEvent.mouseDown(screen.getByText("Description"));
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("locks background scroll while open and restores it on close", async () => {
    document.body.style.overflow = "auto";
    function Toggle() {
      const [open, setOpen] = useState(true);
      return (
        <>
          <button type="button" onClick={() => setOpen(false)}>
            close
          </button>
          <Dialog open={open} labelledBy="t" onDismiss={() => setOpen(false)}>
            <h2 id="t">Title</h2>
            <button type="button">ok</button>
          </Dialog>
        </>
      );
    }
    render(<Toggle />);
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.click(screen.getByRole("button", { name: "close" }));
    await waitFor(() => expect(document.body.style.overflow).toBe("auto"));
  });

  it("renders nothing at all when closed", () => {
    render(
      <Dialog open={false} labelledBy="t" onDismiss={() => {}}>
        <h2 id="t">Title</h2>
      </Dialog>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = render(<Shell />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("the confirm dialog", () => {
  const props = {
    open: true as const,
    title: "Delete this document?",
    description: "The contents are destroyed and this cannot be undone.",
    confirmLabel: "Delete document",
  };

  it("is an alertdialog, so the consequence is announced rather than merely present", () => {
    render(<ConfirmDialog {...props} onConfirm={() => {}} onCancel={() => {}} />);
    const panel = screen.getByRole("alertdialog");
    expect(panel).toHaveAccessibleName("Delete this document?");
    expect(panel).toHaveAccessibleDescription(
      "The contents are destroyed and this cannot be undone.",
    );
  });

  it("opens focus on the safe action, so a stray Enter cannot confirm", () => {
    render(<ConfirmDialog {...props} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  /**
   * Not `disabled`, on either control, ever. Disabling the element holding focus blurs it
   * to `<body>` — outside the panel — so the trap and Escape both stop working and the
   * user's focus sits behind the backdrop with no indicator (WCAG 2.4.11). jsdom does not
   * model that blur, which is why this is asserted on the attribute rather than on the
   * focus behaviour it prevents.
   */
  it("marks both controls aria-disabled while busy, and disables neither", () => {
    render(<ConfirmDialog {...props} busy onConfirm={() => {}} onCancel={() => {}} />);
    for (const name of ["Cancel", "Working…"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).not.toBeDisabled();
    }
  });

  it("acts on neither control while busy", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<ConfirmDialog {...props} busy onConfirm={onConfirm} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Working…" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("says what the busy action is in the vocabulary of the action pressed", () => {
    render(
      <ConfirmDialog
        {...props}
        busy
        busyLabel="Deleting…"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Deleting…" })).toBeInTheDocument();
  });

  it("has no axe violations, busy or idle", async () => {
    const idle = render(<ConfirmDialog {...props} onConfirm={() => {}} onCancel={() => {}} />);
    expect(await axe(idle.container)).toHaveNoViolations();
    idle.unmount();
    const busy = render(
      <ConfirmDialog {...props} busy onConfirm={() => {}} onCancel={() => {}} />,
    );
    expect(await axe(busy.container)).toHaveNoViolations();
  });
});
