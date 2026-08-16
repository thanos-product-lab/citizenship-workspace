"use client";

import type { components } from "@cw/api-client";
import {
  AssessedInput,
  AssessmentSummary,
  CalculationBreakdown,
  ExplanationLayer,
  ExplanationStack,
  RequirementStatus,
  SourceReference,
  StaleAssessmentNotice,
  StatusGlyph,
} from "@cw/design-system";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

import { buildCalculationRows } from "./breakdown";
import { formatDate, formatDateTime } from "./dates";

type Detail = components["schemas"]["RequirementDetail"];

/**
 * The requirement explanation — the product's signature interaction.
 *
 * The layers follow UI/UX §7.3 exactly (Assessment → Facts used → Evidence used → Rule
 * used → Limitations → Next action), because that tree *is* the domain model: a result,
 * the versioned inputs it read, the evidence supporting those inputs, the rule version it
 * ran under, its structured limitations and its next actions. Nothing on this page is
 * generated prose — every sentence is either a server-rendered template or a field.
 *
 * The three things this page must not do:
 *
 * - present a stale conclusion as current — the badges and the notice both say otherwise;
 * - let a long list of inputs read as corroboration — each row says whether it counted;
 * - claim a guidance version or retrieval date it does not have.
 */
export function RequirementDetail({
  caseId,
  requirementKey,
}: {
  caseId: string;
  requirementKey: string;
}) {
  const api = useApiClient();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const returnFocusToTitle = useRef(false);

  // Keyed under the case, so any write that touches assessment state invalidates this
  // page too — including writes made from the case screen in another tab. Refetching on
  // window focus is the cache's default here, which is what makes a snapshot page safe.
  const { data, status, error, refetch } = useQuery({
    queryKey: caseKeys.requirement(caseId, requirementKey),
    queryFn: async () => {
      const { data, response } = await api.GET(
        "/api/v1/cases/{case_id}/requirements/{requirement_key}",
        { params: { path: { case_id: caseId, requirement_key: requirementKey } } },
      );
      if (!data) {
        throw Object.assign(new Error("requirement unavailable"), {
          status: response?.status ?? 0,
        });
      }
      // A payload missing the list fields becomes an error rather than a crash. The
      // generated types promise they are present, but types describe the schema this
      // build was generated from — during a deploy an older API can still be answering.
      if (!isRenderable(data)) {
        throw Object.assign(new Error("requirement payload not renderable"), { status: 0 });
      }
      return data;
    },
  });

  const notFound = (error as { status?: number } | null)?.status === 404;
  const detail = data ?? null;

  // The retry button unmounts on click; park focus on the title rather than dropping the
  // user to <body>, where the next Tab restarts from the top of the document.
  useEffect(() => {
    if (status === "success" && returnFocusToTitle.current) {
      returnFocusToTitle.current = false;
      titleRef.current?.focus();
    }
  }, [status]);

  if (status === "pending") {
    return (
      <p role="status" style={{ color: "var(--cw-text-muted)" }}>
        Loading this requirement…
      </p>
    );
  }

  if (notFound) {
    return (
      <div>
        <h1 style={{ fontSize: "var(--cw-text-2xl)" }}>Requirement not found</h1>
        <p style={{ color: "var(--cw-text-muted)" }}>
          There’s no requirement with that name in this case.{" "}
          <a href={`/cases/${caseId}`}>Back to the case</a>.
        </p>
      </div>
    );
  }

  if (status === "error" || !detail) {
    return (
      <div role="alert">
        <p style={{ color: "var(--cw-status-not-satisfied)" }}>
          We couldn’t load this requirement.
        </p>
        <button
          type="button"
          className="cw-button cw-button--secondary"
          onClick={() => {
            returnFocusToTitle.current = true;
            void refetch();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const unassessed = detail.conclusion === "NOT_YET_ASSESSED";
  const rows = buildCalculationRows(
    detail.calculation_breakdown as Record<string, unknown>,
    detail.summary_parameters as Record<string, unknown>,
  );
  const movedInputs = [...detail.facts_used, ...detail.travel_inputs].filter(
    (input) => (!input.is_still_current || input.is_removed) && !input.unavailable,
  );

  return (
    <div>
      <a className="cw-back" href={`/cases/${caseId}`}>
        ← Back to the case
      </a>

      <AssessmentSummary
        title={detail.title}
        description={detail.short_description}
        conclusion={detail.conclusion}
        currency={detail.currency}
        figure={headlineFigure(detail)}
        summary={detail.summary?.text ?? null}
        titleRef={titleRef}
      >
        {detail.stale ? (
          <StaleAssessmentNotice
            reason={detail.stale.reason}
            detail={
              movedInputs.length > 0
                ? `What changed: ${movedInputs.map((i) => i.label).join(", ")}.`
                : null
            }
          />
        ) : null}
      </AssessmentSummary>

      {unassessed ? (
        <ExplanationStack>
          <ExplanationLayer
            id="layer-unassessed"
            title="Assessment"
            emptyMessage="This requirement hasn’t been assessed yet, so there’s nothing to explain. No rule has run against your case for it and no inputs have been read."
          />
          {detail.rule ? (
            <ExplanationLayer
              id="layer-rule-unassessed"
              title="Rule that would apply"
              note="The rule and guidance this requirement will be assessed against."
            >
              <SourceReference
                semanticVersion={detail.rule.semantic_version}
                ruleSet={detail.rule.rule_set}
                lifecycleStatus={detail.rule.lifecycle_status}
                effectiveFrom={detail.rule.effective_from}
                guidance={detail.rule.guidance as { source: string; section?: string }[]}
                guidanceVersionRecorded={detail.rule.guidance_version_recorded}
                formatDate={formatDate}
              />
            </ExplanationLayer>
          ) : null}
        </ExplanationStack>
      ) : (
        <ExplanationStack>
          <ExplanationLayer
            id="layer-why"
            title="Why this assessment was made"
            note="Every figure here is calculated on the server from the inputs below."
            emptyMessage="This requirement has no calculation behind it — the conclusion comes from the answers alone."
          >
            {rows.length > 0 ? (
              <CalculationBreakdown
                rows={rows}
                caption={`How ${detail.title.toLowerCase()} was worked out`}
              />
            ) : null}
          </ExplanationLayer>

          <ExplanationLayer
            id="layer-facts"
            title="Facts used"
            note="The exact versions of your answers this conclusion was reached from."
            emptyMessage="No facts were recorded against this result."
          >
            {detail.facts_used.length > 0 ? (
              <ul className="cw-input-list">
                {detail.facts_used.map((input) => (
                  <AssessedInput
                    key={String(input.input_version_id) + (input.input_key ?? "")}
                    label={input.label}
                    value={input.value}
                    detail={input.detail}
                    provenanceKind={input.provenance_kind}
                    countsAsConfirmed={input.counts_as_confirmed}
                    isStillCurrent={input.is_still_current}
                    unavailable={input.unavailable}
                  />
                ))}
              </ul>
            ) : null}
          </ExplanationLayer>

          <ExplanationLayer
            id="layer-travel"
            title="Travel records used"
            note={detail.travel_inputs.length > 0 ? travelNote(detail) : undefined}
            emptyMessage="This assessment read no travel records."
          >
            {detail.travel_inputs.length > 0 ? (
              <ul className="cw-input-list">
                {detail.travel_inputs.map((input) => (
                  <AssessedInput
                    key={String(input.input_version_id)}
                    label={input.label}
                    value={input.value}
                    detail={input.detail}
                    provenanceKind={input.provenance_kind}
                    countsAsConfirmed={input.counts_as_confirmed}
                    isStillCurrent={input.is_still_current}
                    isRemoved={input.is_removed}
                    unavailable={input.unavailable}
                  />
                ))}
              </ul>
            ) : null}
          </ExplanationLayer>

          {/* The layer stays in the stack rather than being dropped: "no evidence is
              linked" is a true and important statement about this case, and removing the
              layer would let the reader assume the question had been satisfied. */}
          <ExplanationLayer
            id="layer-evidence"
            title="Evidence used"
            emptyMessage="No documents are linked to these records. Every figure above rests on dates you entered yourself, not on evidence the system has checked."
          />

          <ExplanationLayer
            id="layer-rule"
            title="Rule used"
            note="The exact rule version that produced this conclusion."
            emptyMessage="No rule version was recorded for this result."
          >
            {detail.rule ? (
              <SourceReference
                semanticVersion={detail.rule.semantic_version}
                ruleSet={detail.rule.rule_set}
                lifecycleStatus={detail.rule.lifecycle_status}
                effectiveFrom={detail.rule.effective_from}
                guidance={detail.rule.guidance as { source: string; section?: string }[]}
                guidanceVersionRecorded={detail.rule.guidance_version_recorded}
                formatDate={formatDate}
              />
            ) : null}
          </ExplanationLayer>

          <ExplanationLayer
            id="layer-limitations"
            title="Limitations"
            note="Things that reduce confidence in this conclusion."
            emptyMessage="No limitations were recorded against this result."
          >
            {detail.limitations.length > 0 ? (
              <ul className="cw-notes">
                {detail.limitations.map((limitation) => (
                  <li
                    key={limitation.code}
                    className="cw-note"
                    data-severity={limitation.severity}
                  >
                    <StatusGlyph name="scale" size={16} />
                    <span>
                      {limitation.text ?? limitation.code}
                      <span className="cw-note__meta">
                        {limitation.severity.toLowerCase().replace(/_/g, " ")}
                        {limitation.affected_input_ids.length > 0
                          ? ` · affects ${limitation.affected_input_ids.length} record${
                              limitation.affected_input_ids.length === 1 ? "" : "s"
                            }`
                          : ""}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </ExplanationLayer>

          <ExplanationLayer
            id="layer-next"
            title="Next action"
            emptyMessage={nextActionEmptyMessage(detail)}
          >
            {detail.next_actions.length > 0 ? (
              <ul className="cw-notes">
                {detail.next_actions.map((action) => (
                  <li
                    key={action.code}
                    className="cw-note"
                    data-blocking={action.blocking ? "true" : undefined}
                  >
                    <StatusGlyph name="gauge" size={16} />
                    <span>
                      {action.text ?? action.code}
                      {action.blocking ? (
                        <span className="cw-note__meta">
                          blocks this requirement being satisfied
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </ExplanationLayer>

          <ExplanationLayer
            id="layer-history"
            title="Assessment history"
            note="Every conclusion reached for this requirement, newest first. Nothing is overwritten."
            emptyMessage="This requirement has been assessed once."
          >
            {detail.history.length > 1 ? (
              <ul className="cw-history">
                {detail.history.map((entry, index) => (
                  <li
                    key={`${entry.assessment_run_id}-${entry.created_at}`}
                    className="cw-history__item"
                    data-current={index === 0 ? "true" : "false"}
                  >
                    <span>
                      <RequirementStatus
                        conclusion={entry.conclusion}
                        currency={entry.currency}
                        size="sm"
                      />
                      {entry.summary?.text ? (
                        <span className="cw-note__meta">{entry.summary.text}</span>
                      ) : null}
                    </span>
                    <span className="cw-history__when cw-figure">
                      {formatDateTime(entry.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </ExplanationLayer>
        </ExplanationStack>
      )}
    </div>
  );
}

/**
 * What to say when a result carries no next action.
 *
 * Three different situations, and only one of them means "you have nothing to do":
 *
 * - SUPPORTED with no limitations — genuinely nothing outstanding.
 * - Any limitations — point at them. Several evaluators raise limitations without
 *   emitting a next action, and "nothing to do" one layer beneath an unresolved conflict
 *   is false reassurance.
 * - Not SUPPORTED but no limitations either — say only that no action was recorded.
 *   Pointing at the Limitations layer here would contradict it: that layer is empty.
 */
function nextActionEmptyMessage(detail: Detail): string {
  if (detail.limitations.length > 0) {
    return "No next action has been recorded for this result. Anything listed under Limitations is still unresolved.";
  }
  if (detail.conclusion === "SUPPORTED") {
    return "There’s nothing to do for this requirement right now.";
  }
  return "No next action has been recorded for this result.";
}

/**
 * Does this payload carry the fields the stack iterates? Guards against a schema older
 * than this build — the alternative is an unhandled TypeError that blanks the route.
 */
function isRenderable(detail: Detail): boolean {
  return (
    Array.isArray(detail.facts_used) &&
    Array.isArray(detail.travel_inputs) &&
    Array.isArray(detail.limitations) &&
    Array.isArray(detail.next_actions) &&
    Array.isArray(detail.history)
  );
}

/** The headline number, when the result has one. Read straight from the server. */
function headlineFigure(detail: Detail): string | null {
  const params = detail.summary_parameters as Record<string, unknown>;
  const days = params["days"];
  const threshold = params["threshold"];
  if (typeof days !== "number") return null;
  const noun = days === 1 ? "day" : "days";
  // "confirmed" is load-bearing: `days` is the trusted total, and the message registry
  // commits to always naming it as such. This is the one figure composed outside it. The
  // relationship is stated in words, not a middle dot a screen reader skips.
  return typeof threshold === "number"
    ? `${days} confirmed ${noun} against a threshold of ${threshold}`
    : `${days} confirmed ${noun}`;
}

/**
 * Names how many of the listed records actually counted. Without this the reader sees a
 * long list and infers corroboration; the count makes the trust gate explicit.
 */
function travelNote(detail: Detail): string {
  const total = detail.travel_inputs.length;
  const counted = detail.travel_inputs.filter((i) => i.counts_as_confirmed === true).length;
  // Scoped to this run, not to the user's current records: under a stale result the two
  // sets differ, and "all of your travel records" would be a false claim about the present.
  if (counted === total) {
    return `All ${total} travel records this assessment read were confirmed with exact dates, so all of them counted towards the figure.`;
  }
  return `${counted} of the ${total} travel records this assessment read were confirmed with exact dates. Only those counted towards the figure.`;
}
