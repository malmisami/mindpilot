const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const WEEKDAYS_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November',
  'December'];

function parts(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return { y, m, d, date: new Date(Date.UTC(y, m - 1, d)) };
}

/** 16 Oct 2026 */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { y, m, d } = parts(iso);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** 16 Oct */
export function fmtShort(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { m, d } = parts(iso);
  return `${d} ${MONTHS[m - 1]}`;
}

/** Fri 16 Oct */
export function fmtWeekday(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { m, d, date } = parts(iso);
  return `${WEEKDAYS[date.getUTCDay()]} ${d} ${MONTHS[m - 1]}`;
}

/** Friday 16 October 2026 */
export function fmtLong(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { y, m, d, date } = parts(iso);
  return `${WEEKDAYS_LONG[date.getUTCDay()]} ${d} ${MONTHS_LONG[m - 1]} ${y}`;
}

/** 14:40 */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso || iso.length < 16) return '';
  return iso.slice(11, 16);
}

/** 16 Oct at 14:40 */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '–';
  const time = fmtTime(iso);
  return `${fmtShort(iso)}${time ? ` at ${time}` : ''}`;
}

export function fmtNum(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–';
  return value.toFixed(digits);
}

export function fmtThousands(value: number): string {
  return value.toLocaleString('en-GB');
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parts(to).date.getTime() - parts(from).date.getTime()) / 86_400_000);
}

/** "1 day" / "3 days" – a count with its noun in the singular or plural (regular plurals; pass `many` otherwise). */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** A one-word due label in the middle of a sentence: "Tomorrow" → "tomorrow"; a date such as "Wed 21 Oct" stays as it is. */
export function dayWord(label: string): string {
  return /^\S+$/.test(label) ? label.toLowerCase() : label;
}

/** today / tomorrow / yesterday / in 3 days / 3 days ago */
export function relativeDay(iso: string | null | undefined, today: string): string {
  if (!iso) return '–';
  const diff = daysBetween(today, iso);
  if (diff === 0) return 'today';
  if (diff === 1) return 'tomorrow';
  if (diff === -1) return 'yesterday';
  return diff > 0 ? `in ${plural(diff, 'day')}` : `${plural(-diff, 'day')} ago`;
}

export function capitalize(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

export const SOURCE_TEXT: Record<string, string> = {
  demo: 'Ready-made text (DEMO_AI_MODE)',
  fallback: 'Ready-made text – the AI text was rejected or not available',
  live: 'Phrased by AI (Claude)',
  fixed: 'Fixed, pre-approved text',
  client: 'You',
};

/* Finnish needed name inflection where a therapist's first name is used in a sentence; English does not. The helpers
   stay so that callers keep working: the name in a sentence ("Get to know Anna"), and the possessive ("Sami's"). */
export function illative(name: string): string {
  return name;
}

export function partitive(name: string): string {
  return name;
}

/** 'Sami's', 'Mikko's' – the possessive of a demo first name. */
export function genitive(name: string): string {
  return /s$/i.test(name) ? `${name}'` : `${name}'s`;
}

/** Case- and accent-insensitive text for search ("jannitys" finds "jännitys"). */
export function normalizeText(text: string): string {
  return text.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '');
}
