"use client";

import type { components } from "@cw/api-client";
import type { JSX } from "react";
import { useEffect, useRef, useState } from "react";

import { useApiClient } from "@/lib/api";

type Case = components["schemas"]["CaseResponse"];
type DeleteState = "idle" | "confirming" | "deleting" | "error";

/**
 * Deleting a case is terminal and irreversible, so it does not sit in the primary
 * journey. It lives at the foot of Case data, separated from readiness and assessment
 * work, behind an in-page confirm.
 *
 * The confirm is deliberately a rendered step rather than a `window.confirm`: a native
 * dialog cannot be styled, cannot be described to assistive technology beyond its own
 * string, and blocks the page.
 */
export function DeleteCaseControl({
  caseId,
  onDeleted,
}: {
  caseId: string;
  onDeleted: (updated: Case) => void;
}): JSX.Element {
  const api = useApiClient();
  const [state, setState] = useState<DeleteState>("idle");
  const confirmRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const prevState = useRef<DeleteState>("idle");

  // Focus post-render (the target must be mounted): opening the confirm lands on
  // "Delete permanently"; cancelling back to idle returns focus to the trigger.
  useEffect(() => {
    if (state === "confirming") confirmRef.current?.focus();
    else if (prevState.current === "confirming" && state === "idle") triggerRef.current?.focus();
    prevState.current = state;
  }, [state]);

  async function doDelete() {
    setState("deleting");
    const { data } = await api.DELETE("/api/v1/cases/{case_id}", {
      params: { path: { case_id: caseId } },
    });
    if (data) {
      onDeleted(data);
      return;
    }
    setState("error");
  }

  return (
    <section className="cw-danger-zone" aria-labelledby="danger-zone-heading">
      <h2 id="danger-zone-heading" className="cw-danger-zone__heading">
        Delete this case
      </h2>
      <p className="cw-danger-zone__note">
        Deleting removes the case and everything recorded against it. This can’t be undone.
      </p>

      {state === "confirming" ? (
        <div role="group" aria-label="Confirm deletion" className="cw-danger-zone__confirm">
          <p id="delete-warning" style={{ margin: 0 }}>
            Delete this case? This can’t be undone.
          </p>
          <div style={{ display: "flex", gap: "var(--cw-space-3)", flexWrap: "wrap" }}>
            <button
              ref={confirmRef}
              type="button"
              onClick={doDelete}
              aria-describedby="delete-warning"
              className="cw-button cw-button--danger"
            >
              Delete permanently
            </button>
            <button
              type="button"
              onClick={() => setState("idle")}
              className="cw-button cw-button--secondary"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setState("confirming")}
          disabled={state === "deleting"}
          className="cw-button cw-button--secondary"
        >
          {state === "deleting" ? "Deleting…" : "Delete case"}
        </button>
      )}

      {state === "error" && (
        <p role="alert" style={{ color: "var(--cw-status-not-satisfied)", marginTop: "var(--cw-space-3)" }}>
          Could not delete this case. Please try again.
        </p>
      )}
    </section>
  );
}
