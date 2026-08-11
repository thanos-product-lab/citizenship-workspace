"use client";

import { useRef } from "react";

import { Dialog } from "./Dialog";
import { dangerButtonStyle, secondaryButtonStyle } from "./ui";

/**
 * A confirmation modal for a discrete destructive action, built on the shared `Dialog`
 * shell. Focus opens on the **safe** action (Cancel) so an accidental Enter can't confirm;
 * the shell owns the trap, Escape, backdrop, and scroll lock.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  return (
    <Dialog
      open={open}
      labelledBy="confirm-dialog-title"
      describedBy="confirm-dialog-desc"
      onDismiss={onCancel}
      initialFocusRef={cancelRef}
    >
      <h2 id="confirm-dialog-title" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
        {title}
      </h2>
      <p id="confirm-dialog-desc" style={{ margin: "var(--cw-space-3) 0 0", color: "var(--cw-text-muted)" }}>
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
        <button ref={cancelRef} type="button" onClick={onCancel} style={secondaryButtonStyle}>
          Cancel
        </button>
        <button type="button" onClick={onConfirm} disabled={busy} style={dangerButtonStyle}>
          {busy ? "Removing…" : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
