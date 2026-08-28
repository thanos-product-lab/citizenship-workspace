"use client";

import { useRef } from "react";

import { Dialog } from "./Dialog";
import { dangerButtonStyle, secondaryButtonStyle } from "@/components/ui";

/**
 * A confirmation modal for a discrete destructive action, built on the shared `Dialog`
 * shell. Focus opens on the **safe** action (Cancel) so an accidental Enter can't confirm;
 * the shell owns the trap, Escape, backdrop, and scroll lock.
 *
 * Lives in `components/` rather than in a feature: it is a two-consumer,
 * accessibility-critical shell, and the copy that would otherwise be made "could drift on
 * exactly the associations the accessibility gate turns on" — the reasoning `ui.tsx`
 * already records for `Field`.
 *
 * **Neither button is ever `disabled` while busy.** Disabling the element that currently
 * holds focus blurs it to `<body>`, which is outside the panel — so the Tab trap and
 * Escape both stop working (they are `onKeyDown` handlers on the panel, and a keydown on
 * `<body>` never reaches them) and the user's focus sits behind the backdrop with no
 * indicator, which is WCAG 2.4.11 in as many words. The rule is written down in
 * `globals.css` and in `TravelHistory.tsx`; this shell was the one place still breaking
 * it, and this product's single irreversible action runs through it. jsdom does not model
 * the blur, which is why the tests were green.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busyLabel = "Working…",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  /**
   * What the confirm button says while the action is in flight. Defaulted rather than
   * fixed because the previous hardcoded "Removing…" spoke the vocabulary of the *safe*
   * operation: in this product "Remove" is detaching a document from a trip, which is
   * reversible. A user who presses "Delete document" and is told "Removing…" is being
   * told about a different, gentler action.
   */
  busyLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  return (
    <Dialog
      open={open}
      // `alertdialog`, not `dialog`: this modal exists to state a consequence before an
      // irreversible action, and that consequence lives entirely in the description. The
      // ARIA APG role is the one that makes announcing the description the expected
      // behaviour rather than the likely one.
      role="alertdialog"
      labelledBy="confirm-dialog-title"
      describedBy="confirm-dialog-desc"
      onDismiss={onCancel}
      initialFocusRef={cancelRef}
    >
      <h2 id="confirm-dialog-title" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
        {title}
      </h2>
      <p
        id="confirm-dialog-desc"
        style={{ margin: "var(--cw-space-3) 0 0", color: "var(--cw-text-muted)" }}
      >
        {description}
      </p>
      <div
        style={{
          marginTop: "var(--cw-space-6)",
          display: "flex",
          gap: "var(--cw-space-3)",
          justifyContent: "flex-end",
          flexWrap: "wrap",
        }}
      >
        <button
          ref={cancelRef}
          type="button"
          // Cancel is inert while the action is in flight, and this is not tidiness. It
          // used to stay live and cancel *nothing*: the request continued, and the user
          // who pressed it watched the document disappear anyway — having been given an
          // affordance that said they had stopped it. Worse without sight, where the only
          // signal is the "deleted" announcement contradicting what Cancel implied.
          aria-disabled={busy}
          onClick={() => {
            if (busy) return;
            onCancel();
          }}
          style={secondaryButtonStyle}
        >
          Cancel
        </button>
        <button
          type="button"
          aria-disabled={busy}
          onClick={() => {
            if (busy) return;
            onConfirm();
          }}
          style={dangerButtonStyle}
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
