/**
 * Display formatting for values the server sends as ISO strings.
 *
 * This is presentation only. It never parses a value in order to *compute* anything —
 * every figure, window boundary and total on this screen is calculated server-side and
 * rendered as given (CLAUDE.md §8). The server also does its own date formatting inside
 * the plain-language summaries; this covers the structured fields around them.
 */

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

/** "2027-04-15" → "15 April 2027". Anything unparseable is returned unchanged. */
export function formatDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  const name = MONTHS[Number(month) - 1];
  if (!name || !year || !day) return iso;
  return `${Number(day)} ${name} ${year}`;
}

/** An ISO datetime → "15 April 2027 at 11:36". Falls back to the date alone. */
export function formatDateTime(iso: string): string {
  const date = formatDate(iso);
  const time = /T(\d{2}):(\d{2})/.exec(iso);
  return time ? `${date} at ${time[1]}:${time[2]}` : date;
}
