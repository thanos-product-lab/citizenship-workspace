/**
 * One field a model proposed, and the act by which a person decides about it.
 *
 * This is where prime directive 1 stops being an argument about types and becomes
 * something someone does with a keyboard. Three rules shape it, and none of them is a
 * styling preference.
 *
 * **A high-risk field is confirmed blind (RFC §41.4).** There is no proposed value on
 * screen and no default in the input: the person reads the document and types what it
 * says, and the server works out from the entry whether that was a confirmation or a
 * correction. `proposedValue` is `null` for a pending blind field because the API does
 * not send it — the guarantee is at the wire, and this component could not render it
 * even if someone added the markup.
 *
 * **One affirmative control for a blind field, not two.** A value beside Confirm and
 * Correct makes Confirm the path of least resistance, and a system recording
 * `USER_CONFIRMED_AI_CLAIM` cannot then tell "I checked" from "I clicked". Save is the
 * only affirmative action; which decision it was is reported back afterwards.
 *
 * **The input is `type="text"`, deliberately, for a date.** A native date input imposes a
 * locale format, so someone reading `03/04/2025` off a page would enter it through a
 * picker that silently resolves the ambiguity the whole design exists to preserve — and
 * `parse_entered_date` on the server would never get the chance to refuse it. The hint
 * names the formats the server actually accepts.
 *
 * Presentational: it holds no state, fetches nothing, and decides nothing. The app owns
 * the entry, the mutation and the outcome; this owns what a person sees and reaches.
 */

import type { JSX, ReactNode } from "react";

import { BeforeAfterValue } from "./BeforeAfterValue";
import { ProvenanceBadge } from "./AssessedInput";
import { StatusGlyph } from "./StatusGlyph";

export interface FieldDecision {
  /** `CONFIRM`, `CORRECT` or `REJECT`. */
  decision: string;
  /** `BLIND_ENTRY` or `PREFILLED` — how the decision was taken, not what it was. */
  reviewMode: string;
  /** What the decision authorised. Null for a rejection: a rejection creates no value. */
  value: string | null;
  reasonCode: string | null;
  reviewedAt: string;
}

export interface RejectionOption {
  value: string;
  label: string;
}

export interface ExtractedFieldReviewProps {
  /** Unique within the page; used to wire label, hint and error to the control. */
  id: string;
  /** What the field is, in the user's words — "Departure date", not `travel.departure_date`. */
  label: string;
  /** Whether this field must be confirmed blind. Comes from the API, never re-derived here. */
  blind: boolean;
  /**
   * The model's words. **Null for a pending blind field** — see the note above — and
   * present once a decision exists, which is what lets a correction be shown as one.
   */
  proposedValue: string | null;
  /** Null while the field is still open. */
  decision: FieldDecision | null;
  /** What the person has typed. Controlled by the app so a refusal can keep it. */
  entered: string;
  onEnteredChange: (value: string) => void;
  /** Blind: save the entry. Pre-filled: confirm as proposed, or save the correction. */
  onSubmit: () => void;
  onReject: (reasonCode: string) => void;
  /** Pre-filled only: switch from confirming to editing. */
  correcting: boolean;
  onCorrectingChange: (correcting: boolean) => void;
  /** Whether the reject reason picker is open. Held by the app so only one opens at a time. */
  rejecting: boolean;
  onRejectingChange: (rejecting: boolean) => void;
  rejectionOptions: readonly RejectionOption[];
  rejectionReason: string;
  onRejectionReasonChange: (value: string) => void;
  /** A server refusal, bound to the input. */
  error?: string | null | undefined;
  busy?: boolean | undefined;
  /**
   * Set once slice 4 detects a claim disagreeing with a record the case already holds.
   * Accepted now and never passed, so the state exists in one place rather than being
   * invented twice — but nothing fabricates it in the meantime.
   */
  conflictsWith?: string | null | undefined;
  /** Format hint for a blind entry, e.g. the date formats the server accepts.
   *  `| undefined` explicitly: `exactOptionalPropertyTypes` is on, and a caller that
   *  computes the hint conditionally passes `undefined` rather than omitting the prop. */
  hint?: string | undefined;
  /**
   * What tells this field apart from an identically-named one elsewhere on the page —
   * "Journey 2" on a two-leg booking.
   *
   * Appended to the control's **accessible name**, not to the visible label. A booking
   * with two journeys renders two blind date inputs whose names were character-identical,
   * distinguished only by a heading in a plain `div` above them — which is no
   * distinction at all in forms mode or in a screen reader's list of controls. The
   * consequence on this screen is typing the outbound date into the return field, which
   * is a wrong trip boundary entering the case through the one interaction the trust
   * model rests on.
   */
  context?: string | undefined;
}

const DECISION_PROVENANCE: Record<string, string> = {
  CONFIRM: "user_confirmed",
  CORRECT: "user_corrected",
};

export function ExtractedFieldReview({
  id,
  label,
  blind,
  proposedValue,
  decision,
  entered,
  onEnteredChange,
  onSubmit,
  onReject,
  correcting,
  onCorrectingChange,
  rejecting,
  onRejectingChange,
  rejectionOptions,
  rejectionReason,
  onRejectionReasonChange,
  error = null,
  busy = false,
  conflictsWith = null,
  hint,
  context,
}: ExtractedFieldReviewProps): JSX.Element {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const decided = decision !== null;

  return (
    <div
      // Focusable only programmatically, and it exists so the app can put focus here
      // after a decision. The control the user activated is unmounted the moment the
      // field settles, which dropped focus to `<body>` — a keyboard user lost their place
      // on every save, and a screen-reader user's virtual cursor jumped to the top of the
      // page. The deletion flow solved the same problem the same way in M7.
      id={`${id}-card`}
      tabIndex={-1}
      className="cw-field-review"
      data-decided={decided}
      data-blind={blind}
    >
      <div className="cw-field-review__head">
        <span className="cw-field-review__label" id={`${id}-name`}>
          {label}
        </span>
        <ProvenanceBadge kind={badgeKind(decision, conflictsWith)} />
      </div>

      {decided ? (
        <Settled
          decision={decision}
          proposedValue={proposedValue}
          label={label}
        />
      ) : (
        <Open
          id={id}
          label={label}
          blind={blind}
          proposedValue={proposedValue}
          entered={entered}
          onEnteredChange={onEnteredChange}
          onSubmit={onSubmit}
          onReject={onReject}
          correcting={correcting}
          onCorrectingChange={onCorrectingChange}
          rejecting={rejecting}
          onRejectingChange={onRejectingChange}
          rejectionOptions={rejectionOptions}
          rejectionReason={rejectionReason}
          onRejectionReasonChange={onRejectionReasonChange}
          error={error}
          busy={busy}
          hint={hint}
          context={context}
          hintId={hintId}
          errorId={errorId}
        />
      )}

      {conflictsWith ? (
        <p className="cw-field-review__conflict">
          <StatusGlyph name="conflict" size={14} />
          <span>{conflictsWith}</span>
        </p>
      ) : null}
    </div>
  );
}

/** What the badge says about a field nobody has decided about yet, or has. */
function badgeKind(
  decision: FieldDecision | null,
  conflictsWith: string | null,
): string {
  if (conflictsWith) return "conflicting";
  if (decision === null) return "ai_proposed";
  // A rejection is neither confirmed nor corrected: nothing was trusted. `unavailable`
  // is the provenance token for "this contributes nothing", which is exactly true.
  return DECISION_PROVENANCE[decision.decision] ?? "unavailable";
}

function Settled({
  decision,
  proposedValue,
  label,
}: {
  decision: FieldDecision;
  proposedValue: string | null;
  label: string;
}): JSX.Element {
  if (decision.decision === "REJECT") {
    return (
      <p className="cw-field-review__settled">
        You said this was wrong, so nothing was recorded from it.
        {decision.reasonCode ? (
          <> Reason: {humanise(decision.reasonCode)}.</>
        ) : null}
      </p>
    );
  }
  const corrected = decision.decision === "CORRECT";
  return (
    <div className="cw-field-review__settled">
      <p className="cw-field-review__value cw-figure">{decision.value}</p>
      {corrected && proposedValue ? (
        // The original proposal, preserved and shown — MVP §8.11 requires the record to
        // keep it, and §9.4 requires the split view to show it. A correction the user
        // cannot see the shape of is a correction they have to take on trust.
        <BeforeAfterValue
          label={`What we read, and what you read (${label})`}
          before={proposedValue}
          after={decision.value ?? ""}
        />
      ) : null}
    </div>
  );
}

interface OpenFieldProps {
  id: string;
  label: string;
  blind: boolean;
  proposedValue: string | null;
  entered: string;
  onEnteredChange: (value: string) => void;
  onSubmit: () => void;
  onReject: (reasonCode: string) => void;
  correcting: boolean;
  onCorrectingChange: (correcting: boolean) => void;
  rejecting: boolean;
  onRejectingChange: (rejecting: boolean) => void;
  rejectionOptions: readonly RejectionOption[];
  rejectionReason: string;
  onRejectionReasonChange: (value: string) => void;
  error: string | null;
  busy: boolean;
  // `| undefined` rather than `hint?:` — `exactOptionalPropertyTypes` is on, so an
  // optional property refuses an explicitly-undefined value, and this is an internal
  // component whose caller always passes the prop.
  hint: string | undefined;
  context: string | undefined;
  hintId: string;
  errorId: string;
}

function Open({
  id,
  label,
  blind,
  proposedValue,
  entered,
  onEnteredChange,
  onSubmit,
  onReject,
  correcting,
  onCorrectingChange,
  rejecting,
  onRejectingChange,
  rejectionOptions,
  rejectionReason,
  onRejectionReasonChange,
  error,
  busy,
  hint,
  context,
  hintId,
  errorId,
}: OpenFieldProps): JSX.Element {
  const typing = blind || correcting;
  const describedBy = [hint ? hintId : null, error ? errorId : null]
    .filter(Boolean)
    .join(" ");

  const submit = () => {
    // Guarded rather than relying on `aria-disabled` alone. The attribute tells a screen
    // reader the control is unavailable and does nothing to stop the click, so three
    // clicks on a Save announced as unavailable sent three requests — the second and
    // third refused as already-reviewed, into a field that no longer rendered the error.
    // A control that announces one thing and does another is worse than either.
    if (busy) return;
    onSubmit();
  };

  return (
    <form
      className="cw-field-review__open"
      // Enter in the box submits, which is the first thing anybody tries and did nothing
      // at all before this: the entry was not in a form, so there was no implicit
      // submission and no feedback either. On a phone the keyboard's return key was
      // equally inert.
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {!blind ? (
        // Shown only for a low-risk field. RFC §41.4 spends the friction where a wrong
        // value changes an assessment conclusion, and not where it does not.
        <p className="cw-field-review__value cw-figure">{proposedValue}</p>
      ) : null}

      {typing ? (
        <div className="cw-field-review__entry">
          <label className="cw-field-review__entry-label" htmlFor={id}>
            {blind
              ? `${label}, as the document writes it`
              : `${label}, corrected`}
            {/* Off-screen, because the journey is already a visible heading above the
                group — but a heading in a `div` is no distinction at all in forms mode,
                where the two blind date inputs of a two-leg booking had
                character-identical names. */}
            {context ? (
              <span className="cw-visually-hidden">, {context}</span>
            ) : null}
          </label>
          {hint ? (
            <p className="cw-field-review__hint" id={hintId}>
              {hint}
            </p>
          ) : null}
          <input
            id={id}
            // `text`, never `date` — see the note at the top of this file. This is the
            // single most deliberate line in the component.
            type="text"
            className="cw-field-review__input"
            value={entered}
            onChange={(event) => onEnteredChange(event.target.value)}
            aria-describedby={describedBy || undefined}
            aria-invalid={error ? true : undefined}
            autoComplete="off"
            spellCheck={false}
            // `readOnly` + `aria-disabled`, never `disabled` — `components.css` records
            // why for buttons and it is the same here: the browser blurs a focused
            // element the moment it becomes `disabled`, dropping keyboard focus
            // mid-keystroke. `readOnly` refuses input while keeping the field focusable
            // and in the tab order.
            readOnly={busy}
            aria-disabled={busy || undefined}
          />
          {error ? (
            <p className="cw-field-review__error" id={errorId} role="alert">
              <StatusGlyph name="conflict" size={14} />
              <span>{error}</span>
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="cw-field-review__controls">
        <button
          type="submit"
          className="cw-button"
          onClick={submit}
          aria-disabled={busy || undefined}
        >
          {blind ? "Save" : correcting ? "Save correction" : "Confirm"}
        </button>
        {!blind && !correcting ? (
          <button
            type="button"
            className="cw-button cw-button--secondary"
            onClick={() => onCorrectingChange(true)}
          >
            Correct
          </button>
        ) : null}
        {!blind && correcting ? (
          <button
            type="button"
            className="cw-button cw-button--secondary"
            onClick={() => onCorrectingChange(false)}
          >
            Cancel
          </button>
        ) : null}
        <button
          type="button"
          className="cw-button cw-button--secondary"
          onClick={() => {
            if (busy) return;
            onRejectingChange(!rejecting);
          }}
          aria-disabled={busy || undefined}
          aria-expanded={rejecting}
          // Only while the panel exists. A permanent `aria-controls` pointing at an
          // element that is not in the DOM is a dangling IDREF.
          aria-controls={rejecting ? `${id}-reject` : undefined}
        >
          This is wrong
        </button>
      </div>

      {rejecting ? (
        // A reason picker rather than a bare Reject, because RFC §10 wants "why was this
        // wrong" answerable across a corpus rather than one claim at a time — and because
        // a rejection with no reason tells a later evaluation nothing.
        <div className="cw-field-review__reject" id={`${id}-reject`}>
          <label
            className="cw-field-review__entry-label"
            htmlFor={`${id}-reason`}
          >
            Why is it wrong?
          </label>
          <select
            id={`${id}-reason`}
            className="cw-field-review__select"
            value={rejectionReason}
            onChange={(event) => onRejectionReasonChange(event.target.value)}
          >
            {rejectionOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="cw-button cw-button--danger"
            onClick={() => {
              if (busy) return;
              onReject(rejectionReason);
            }}
            aria-disabled={busy || undefined}
          >
            Reject this value
          </button>
        </div>
      ) : null}
    </form>
  );
}

function humanise(code: string): ReactNode {
  return code.toLowerCase().replace(/_/g, " ");
}
