"use client";

import { useEffect, useRef } from "react";
import type { ReactNode, RefObject } from "react";

// Everything focusable inside the panel — used for the initial focus and the focus trap.
const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The reusable modal shell: the accessibility-critical mechanics live here once so every
 * dialog (confirm, form, …) inherits them rather than re-implementing them.
 *
 * `role="dialog"` + `aria-modal`, named by `labelledBy`; focus moves inside on open (to
 * `initialFocusRef` if given, else the first focusable), Tab is trapped, Escape dismisses,
 * background scroll is locked. Backdrop-click dismissal is opt-out (`dismissOnBackdrop`)
 * so a form can't be lost to a stray outside click. Hand-rolled rather than native
 * <dialog> because showModal() isn't implemented in jsdom, and the gate runs there.
 *
 * Return-focus to the trigger is the caller's job — only it knows the trigger — done in
 * the caller's `onDismiss`/success handlers.
 */
export function Dialog({
  open,
  labelledBy,
  describedBy,
  onDismiss,
  dismissOnBackdrop = true,
  maxWidth = "28rem",
  initialFocusRef,
  children,
}: {
  open: boolean;
  labelledBy: string;
  describedBy?: string | undefined;
  onDismiss: () => void;
  dismissOnBackdrop?: boolean;
  maxWidth?: string;
  initialFocusRef?: RefObject<HTMLElement | null> | undefined;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const target =
      initialFocusRef?.current ?? panelRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    target?.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [open, initialFocusRef]);

  if (!open) return null;

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onDismiss();
      return;
    }
    if (event.key !== "Tab") return;
    const nodes = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
    if (!nodes || nodes.length === 0) return;
    const first = nodes[0]!;
    const last = nodes[nodes.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      onMouseDown={(e) => {
        if (dismissOnBackdrop && e.target === e.currentTarget) onDismiss();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(12, 16, 18, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--cw-space-4)",
        zIndex: 50,
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        {...(describedBy ? { "aria-describedby": describedBy } : {})}
        onKeyDown={onKeyDown}
        style={{
          background: "var(--cw-surface)",
          border: "1px solid var(--cw-border-strong)",
          borderRadius: "var(--cw-radius-lg)",
          boxShadow: "var(--cw-shadow-md)",
          padding: "var(--cw-space-6)",
          maxWidth,
          width: "100%",
          maxHeight: "calc(100dvh - 2rem)",
          overflowY: "auto",
        }}
      >
        {children}
      </div>
    </div>
  );
}
