/** Today as YYYY-MM-DD in the viewer's local timezone (not UTC). */
export function todayISO(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/**
 * YYYY-MM-DD `delta` years from today (negative = past), used for native date-input
 * `min`/`max` bounds. These are typo guards, not business rules — they keep a mistyped
 * year (e.g. "0026") out of the field while staying generous enough never to block a
 * real travel or application date.
 */
export function yearsFromTodayISO(delta: number): string {
  const [y, m, d] = todayISO().split("-").map(Number);
  return new Date(Date.UTC(y! + delta, m! - 1, d!)).toISOString().slice(0, 10);
}
