"use client";

import { BeforeAfterValue, RequirementStatus } from "@cw/design-system";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { formatDate } from "@/features/requirements/dates";

import {
  RecalculationIncomplete,
  SaveConflict,
  type SimulatedRequirement,
  type Simulation,
  useApplicationDate,
  useSaveApplicationDate,
  useSimulateApplicationDate,
} from "./useApplicationDate";
import { yearsFromTodayISO } from "./dates";
import {
  Field,
  buttonStyle,
  cardStyle,
  errorTextStyle,
  inputStyle,
  linkButtonStyle,
  secondaryButtonStyle,
} from "./ui";

// Typo-guard bounds (see dates.ts). The proposed date is often future, so the window
// leans forward; both ends are generous enough never to reject a real planned date.
const MIN_DATE = yearsFromTodayISO(-20);
const MAX_DATE = yearsFromTodayISO(10);

/**
 * Select a proposed application date — by previewing it first.
 *
 * The date is the single input every residence conclusion is measured against, and moving
 * it moves the whole five-year window (ADR-0002). So this surface never saves a date the
 * user has not seen the consequences of: type or pick a candidate, see what the rules
 * conclude at it, then save or cancel.
 *
 * **The preview is a real calculation and not a saved one.** The server evaluates the
 * candidate against the case's actual travel records and writes nothing (Domain §10.3);
 * every figure below is passed through from that response and none is computed here
 * (CLAUDE.md §8). The whole comparison sits inside one region labelled "not saved", and
 * every conclusion in it carries the `Preview` currency badge.
 *
 * **No stepper.** There is a date field and, when the rules find one, a button offering
 * the nearest date that clears a failed presence check. There is deliberately no ±1-day
 * control: clearing an absent anchor means moving past the entire trip covering it, which
 * on the canonical case is ten days, and a stepper would teach that one day is the unit
 * of the problem. ADR-0002 exists because a mockup taught exactly that.
 */
export function ApplicationDateCard({ caseId }: { caseId: string }) {
  const current = useApplicationDate(caseId);
  const simulate = useSimulateApplicationDate(caseId);
  const save = useSaveApplicationDate(caseId);

  const [value, setValue] = useState("");
  const [preview, setPreview] = useState<Simulation | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [awaitingSave, setAwaitingSave] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const previewHeadingRef = useRef<HTMLHeadingElement>(null);

  const currentDate = current.data?.application_date ?? "";
  // The field mirrors the saved date until the user edits it. Keyed off the fetched value
  // so a refetch after a save re-syncs it without a second source of truth.
  useEffect(() => {
    setValue((existing) => existing || currentDate);
  }, [currentDate]);

  // Announce when the *preview settles*, not from a mutate callback. React Query drops
  // callbacks when the calling component unmounts, and this file's own controls unmount as
  // the preview replaces them — the lesson M6 learned three times. Reading observed state
  // also means a preview that resolves to "nothing changed" is announced, where a
  // callback keyed on a changed count would say nothing at all.
  useEffect(() => {
    if (!preview) return;
    const changed = visibleChanges(preview).length;
    setAnnouncement(
      changed === 0
        ? `Preview ready for ${formatDate(preview.candidate_application_date)}. No conclusion changes.`
        : `Preview ready for ${formatDate(preview.candidate_application_date)}. ` +
          `${changed} ${changed === 1 ? "requirement changes" : "requirements change"}. Not saved yet.`,
    );
  }, [preview]);

  // Same discipline for the save, and it must span the refetch: until the invalidated
  // queries settle, the rest of the workspace is still showing the previous run.
  useEffect(() => {
    if (!awaitingSave || save.isPending || current.isFetching) return;
    setAwaitingSave(false);
    if (save.isSuccess) {
      setAnnouncement(
        `Saved. ${save.data.assessedCount} requirements reassessed against ${formatDate(value)}.`,
      );
      // No `flushSync` here, and not by preference: React rejects it from inside a
      // lifecycle method ("React cannot flush when React is already rendering"). It is
      // also unnecessary — the input being focused lives in the form, not in the preview,
      // so it is mounted either way. The two `flushSync` calls that remain are in event
      // handlers and mutation callbacks, where the target *does* mount with the preview.
      setPreview(null);
      inputRef.current?.focus();
    }
  }, [awaitingSave, save.isPending, save.isSuccess, save.data, current.isFetching, value]);

  const load = useCallback(() => {
    void current.refetch();
  }, [current]);

  function handlePreview(event: React.FormEvent) {
    event.preventDefault();
    if (!value) {
      setInvalid(true);
      inputRef.current?.focus();
      return;
    }
    setInvalid(false);
    save.reset();
    simulate.mutate(value, {
      // Setting state from here is safe in a way announcing from here is not: this
      // component owns the preview and does not unmount when the request resolves. The
      // announcement still comes from the effect above, because that is the part a
      // dropped callback would silently lose.
      onSuccess: (data) => {
        flushSync(() => setPreview(data));
        previewHeadingRef.current?.focus();
      },
    });
  }

  function handleUseResolvingDate(date: string) {
    setValue(date);
    setInvalid(false);
    simulate.mutate(date, {
      onSuccess: (data) => {
        flushSync(() => setPreview(data));
        previewHeadingRef.current?.focus();
      },
    });
  }

  function handleCancel() {
    flushSync(() => {
      setPreview(null);
      setValue(currentDate);
      simulate.reset();
    });
    setAnnouncement("Preview discarded. Your application date is unchanged.");
    inputRef.current?.focus();
  }

  function handleSave() {
    if (!preview) return;
    setAwaitingSave(true);
    save.mutate({
      applicationDate: preview.candidate_application_date,
      expectedRevision: current.data?.revision ?? null,
    });
  }

  const busy = simulate.isPending || save.isPending || awaitingSave;

  return (
    <section aria-labelledby="app-date-heading" style={cardStyle}>
      <h3 id="app-date-heading" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
        Proposed application date
      </h3>
      <p
        style={{
          marginTop: "var(--cw-space-2)",
          color: "var(--cw-text-muted)",
          fontSize: "var(--cw-text-sm)",
        }}
      >
        The date your case is assessed against. Moving it moves your whole five-year
        qualifying period, so preview a date before you save it.
      </p>

      {/* Mounted unconditionally, and owned by the section rather than by any control
          inside it: a live region whose container and text arrive in the same commit is
          frequently missed by NVDA and JAWS, and every control below unmounts at some
          point in this flow. */}
      <p aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </p>

      {current.isPending && (
        <p role="status" style={{ color: "var(--cw-text-muted)", marginTop: "var(--cw-space-4)" }}>
          Loading…
        </p>
      )}

      {current.isError && (
        <div role="alert" style={{ marginTop: "var(--cw-space-4)" }}>
          <p style={errorTextStyle}>We couldn’t load the application date.</p>
          <button type="button" onClick={load} style={buttonStyle}>
            Try again
          </button>
        </div>
      )}

      {current.isSuccess && (
        <form onSubmit={handlePreview} style={{ marginTop: "var(--cw-space-4)" }}>
          <Field
            id="app-date"
            label="Application date"
            hint={
              currentDate
                ? `Currently ${formatDate(currentDate)}.`
                : "No date selected yet."
            }
            error={invalid ? "Enter a valid date." : undefined}
            // Focus moves to the input when it is rejected, and a focused control
            // announces its described-by error — role="alert" as well would double-speak.
            errorIsLive={false}
          >
            <input
              id="app-date"
              ref={inputRef}
              type="date"
              value={value}
              min={MIN_DATE}
              max={MAX_DATE}
              className="cw-date-input"
              onChange={(event) => {
                setValue(event.target.value);
                setInvalid(false);
                // A stale preview beside a changed field is a preview of something the
                // user is no longer looking at.
                setPreview(null);
              }}
              style={inputStyle}
            />
          </Field>

          <div
            style={{
              marginTop: "var(--cw-space-4)",
              display: "flex",
              gap: "var(--cw-space-4)",
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <button type="submit" aria-disabled={busy} style={buttonStyle}>
              {simulate.isPending ? "Previewing…" : "Preview this date"}
            </button>
            {value !== currentDate && currentDate && !preview && (
              <button type="button" onClick={handleCancel} style={linkButtonStyle}>
                Reset to {formatDate(currentDate)}
              </button>
            )}
          </div>

          {simulate.isError && (
            <p role="alert" style={{ ...errorTextStyle, marginTop: "var(--cw-space-4)" }}>
              We couldn’t work out what this date would mean.{" "}
              <button type="button" onClick={handlePreview} style={linkButtonStyle}>
                Try again
              </button>
            </p>
          )}
        </form>
      )}

      {preview && (
        <PreviewPanel
          preview={preview}
          headingRef={previewHeadingRef}
          busy={busy}
          onSave={handleSave}
          onCancel={handleCancel}
          onUseResolvingDate={handleUseResolvingDate}
          saveError={save.error}
        />
      )}
    </section>
  );
}

/**
 * Which requirements to put in front of the user.
 *
 * Not every field that differs is a change worth showing. `route.adult_applicant`
 * republishes the applicant's age on every candidate date, so `changed.summary_parameters`
 * is true for it on *every* preview — emphasising that would train the reader to ignore
 * the emphasis. The three things that genuinely moved are: the conclusion, the
 * limitations (which is the *whole* output of `residence.travel_consistency`, a rule with
 * no conclusion of its own), and the headline day count the threshold rules publish.
 *
 * This selects and orders; it computes nothing. Every value rendered is passed through
 * from the server (CLAUDE.md §8).
 */
function visibleChanges(preview: Simulation): SimulatedRequirement[] {
  return preview.requirements.filter((row) => {
    if (row.changed.conclusion || row.changed.limitations) return true;
    return daysOf(row.before.summary_parameters) !== daysOf(row.after.summary_parameters);
  });
}

/**
 * Requirements the candidate date leaves unsatisfied without changing.
 *
 * **A preview that showed only what improved would be false reassurance**, and it is the
 * exact shape this interaction invites: the user moves the date to fix the presence
 * anchor, moves it too little, and sees a shorter absence total and no mention of the
 * thing they were trying to fix. Found by using it — at 20 April 2027 the screen said
 * "439 days → 434 days" and nothing else, while presence still failed.
 *
 * Deliberately general rather than a special case for the presence rule. Anything the
 * candidate date leaves not-satisfied gets said, whether or not it moved.
 */
function unresolvedAtCandidate(
  preview: Simulation,
  changes: SimulatedRequirement[],
): SimulatedRequirement[] {
  const shown = new Set(changes.map((row) => row.requirement_key));
  return preview.requirements.filter(
    (row) =>
      !shown.has(row.requirement_key) &&
      row.after.conclusion !== "SUPPORTED" &&
      row.after.conclusion !== "NOT_YET_ASSESSED",
  );
}

function daysOf(parameters: Record<string, unknown>): number | null {
  const days = parameters["days"];
  return typeof days === "number" ? days : null;
}

function dayLabel(count: number | null): string {
  if (count === null) return "—";
  return count === 1 ? "1 day" : `${count} days`;
}

function PreviewPanel({
  preview,
  headingRef,
  busy,
  onSave,
  onCancel,
  onUseResolvingDate,
  saveError,
}: {
  preview: Simulation;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  busy: boolean;
  onSave: () => void;
  onCancel: () => void;
  onUseResolvingDate: (date: string) => void;
  saveError: Error | null;
}) {
  const changes = visibleChanges(preview);
  const unresolved = unresolvedAtCandidate(preview, changes);
  const resolving = preview.resolving_application_date;
  const alreadyPreviewingResolving = resolving === preview.candidate_application_date;

  return (
    <section
      aria-labelledby="app-date-preview-heading"
      className="cw-preview"
      style={{
        marginTop: "var(--cw-space-5)",
        padding: "var(--cw-space-4)",
        border: "1px dashed var(--cw-border-strong)",
        borderRadius: "var(--cw-radius-md)",
      }}
    >
      <h4
        id="app-date-preview-heading"
        ref={headingRef}
        tabIndex={-1}
        style={{ margin: 0, fontSize: "var(--cw-text-md)" }}
      >
        Preview — not saved
      </h4>
      <p
        style={{
          marginTop: "var(--cw-space-2)",
          color: "var(--cw-text-muted)",
          fontSize: "var(--cw-text-sm)",
        }}
      >
        What the rules conclude if you apply on{" "}
        <strong>{formatDate(preview.candidate_application_date)}</strong> instead of{" "}
        {formatDate(preview.current_application_date)}. Nothing has been changed yet.
      </p>

      {preview.windows_before && (
        <BeforeAfterValue
          label="Five-year qualifying period"
          before={`${formatDate(preview.windows_before.qualifying_period_start)} to ${formatDate(preview.windows_before.qualifying_period_end)}`}
          after={`${formatDate(preview.windows_after.qualifying_period_start)} to ${formatDate(preview.windows_after.qualifying_period_end)}`}
        />
      )}
      <BeforeAfterValue
        label="First day of the qualifying period"
        before={
          preview.windows_before
            ? formatDate(preview.windows_before.presence_anchor)
            : "not assessed"
        }
        after={formatDate(preview.windows_after.presence_anchor)}
      />

      {changes.length === 0 ? (
        <p style={{ marginTop: "var(--cw-space-4)" }}>
          No conclusion changes. The window moves, but every requirement reaches the same
          conclusion it does today.
        </p>
      ) : (
        <ul className="cw-preview__changes">
          {changes.map((row) => (
            <li key={row.requirement_key}>
              <p className="cw-preview__title">{row.title}</p>
              <p className="cw-preview__badges">
                <RequirementStatus
                  conclusion={row.before.conclusion}
                  currency={row.before.currency}
                  size="sm"
                />
                <span aria-hidden="true" className="cw-change__arrow">
                  →
                </span>
                <span className="cw-visually-hidden">would become</span>
                <RequirementStatus
                  conclusion={row.after.conclusion}
                  currency={row.after.currency}
                  size="sm"
                />
              </p>
              {daysOf(row.before.summary_parameters) !==
                daysOf(row.after.summary_parameters) && (
                <BeforeAfterValue
                  label="Days outside the UK"
                  before={dayLabel(daysOf(row.before.summary_parameters))}
                  after={dayLabel(daysOf(row.after.summary_parameters))}
                />
              )}
              {row.after.summary?.text && (
                <p className="cw-preview__summary">{row.after.summary.text}</p>
              )}
              {newLimitations(row).map((limitation) => (
                <p key={limitation.code} className="cw-preview__limitation">
                  {limitation.text ?? limitation.code}
                </p>
              ))}
            </li>
          ))}
        </ul>
      )}

      {unresolved.length > 0 && (
        <div className="cw-preview__unresolved">
          <p className="cw-preview__title">Still not satisfied on this date</p>
          <ul className="cw-preview__changes">
            {unresolved.map((row) => (
              <li key={row.requirement_key}>
                <p className="cw-preview__title">{row.title}</p>
                <p className="cw-preview__badges">
                  <RequirementStatus
                    conclusion={row.after.conclusion}
                    currency={row.after.currency}
                    size="sm"
                  />
                </p>
                {row.after.summary?.text && (
                  <p className="cw-preview__summary">{row.after.summary.text}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {resolving && !alreadyPreviewingResolving && (
        <p style={{ marginTop: "var(--cw-space-4)" }}>
          <button
            type="button"
            onClick={() => onUseResolvingDate(resolving)}
            aria-disabled={busy}
            style={secondaryButtonStyle}
          >
            Preview {formatDate(resolving)} instead
          </button>{" "}
          <span style={{ color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
            the nearest later date whose first day is clear of confirmed absence
          </span>
        </p>
      )}

      <div
        style={{
          marginTop: "var(--cw-space-5)",
          display: "flex",
          gap: "var(--cw-space-4)",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <button type="button" onClick={onSave} aria-disabled={busy} style={buttonStyle}>
          {busy ? "Saving…" : `Save ${formatDate(preview.candidate_application_date)}`}
        </button>
        <button type="button" onClick={onCancel} aria-disabled={busy} style={secondaryButtonStyle}>
          Cancel
        </button>
        <span style={{ color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
          Saving reassesses your case against this date.
        </span>
      </div>

      {saveError && (
        <p role="alert" style={{ ...errorTextStyle, marginTop: "var(--cw-space-4)" }}>
          {saveErrorMessage(saveError)}
        </p>
      )}
    </section>
  );
}

/** Limitations the candidate date introduces that the current date does not carry. */
function newLimitations(row: SimulatedRequirement) {
  const before = new Set(row.before.limitations.map((item) => item.code));
  return row.after.limitations.filter((item) => !before.has(item.code));
}

function saveErrorMessage(error: Error): string {
  if (error instanceof SaveConflict) {
    return "This date changed elsewhere while you were previewing, so this comparison is out of date. Reload the page and preview again.";
  }
  if (error instanceof RecalculationIncomplete) {
    return "Your date was saved, but the reassessment didn’t finish. Your conclusions are marked stale — open Issues to recheck them.";
  }
  return "We couldn’t save this date. Please try again.";
}
