/**
 * Shared by the review screen and the library row, so a field is called the same thing
 * in the place you decide it and the place that says it is still open.
 */

/**
 * What each claim type is called on screen.
 *
 * `travel.departure_date` is the domain's name for the field and the right thing to
 * store; it is not a thing to show anybody. A missing entry falls back to a humanised
 * form rather than rendering the key, so a claim type added on the server appears as
 * readable words here before this map catches up.
 */
const FIELD_LABELS: Record<string, string> = {
  "travel.departure_date": "Departure date",
  "travel.return_date": "Return date",
  "travel.origin": "Departing from",
  "travel.destination": "Arriving at",
  "travel.booking_reference": "Booking reference",
  "travel.traveller_name": "Traveller name",
};

/** What a claim type is called on screen. */
export function claimLabel(claimType: string): string {
  return FIELD_LABELS[claimType] ?? humanise(claimType);
}

function humanise(claimType: string): string {
  const field = claimType.split(".").pop() ?? claimType;
  const words = field.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
