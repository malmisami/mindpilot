const WEEKDAYS = ['su', 'ma', 'ti', 'ke', 'to', 'pe', 'la'];
const WEEKDAYS_LONG = ['sunnuntai', 'maanantai', 'tiistai', 'keskiviikko', 'torstai', 'perjantai', 'lauantai'];

function parts(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return { y, m, d, date: new Date(Date.UTC(y, m - 1, d)) };
}

/** 16.10.2026 */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { y, m, d } = parts(iso);
  return `${d}.${m}.${y}`;
}

/** 16.10. */
export function fmtShort(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { m, d } = parts(iso);
  return `${d}.${m}.`;
}

/** pe 16.10. */
export function fmtWeekday(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { m, d, date } = parts(iso);
  return `${WEEKDAYS[date.getUTCDay()]} ${d}.${m}.`;
}

/** perjantai 16.10.2026 */
export function fmtLong(iso: string | null | undefined): string {
  if (!iso) return '–';
  const { y, m, d, date } = parts(iso);
  return `${WEEKDAYS_LONG[date.getUTCDay()]} ${d}.${m}.${y}`;
}

/** 14.40 */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso || iso.length < 16) return '';
  return iso.slice(11, 16).replace(':', '.');
}

/** 16.10. klo 14.40 */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '–';
  const time = fmtTime(iso);
  return `${fmtShort(iso)}${time ? ` klo ${time}` : ''}`;
}

export function fmtNum(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–';
  return value.toFixed(digits).replace('.', ',');
}

export function fmtThousands(value: number): string {
  return value.toLocaleString('fi-FI').replace(/[\u00a0\u202f]/g, '\u00a0');
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parts(to).date.getTime() - parts(from).date.getTime()) / 86_400_000);
}

/** tänään / huomenna / eilen / 3 päivän päästä / 3 päivää sitten */
export function relativeDay(iso: string | null | undefined, today: string): string {
  if (!iso) return '–';
  const diff = daysBetween(today, iso);
  if (diff === 0) return 'tänään';
  if (diff === 1) return 'huomenna';
  if (diff === -1) return 'eilen';
  return diff > 0 ? `${diff} päivän päästä` : `${-diff} päivää sitten`;
}

export function capitalize(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

export const SOURCE_TEXT: Record<string, string> = {
  demo: 'Valmis tekstipohja (DEMO_AI_MODE)',
  fallback: 'Valmis tekstipohja – tekoälyn teksti hylättiin tai ei ollut saatavilla',
  live: 'Tekoälyn muotoilema (Claude)',
  fixed: 'Kiinteä, ennalta hyväksytty teksti',
  client: 'Sinä',
};

/** Finnish name inflection for the few places a therapist's first name is used in a sentence (demo names only). */
export function illative(name: string): string {
  const last = name.slice(-1).toLowerCase();
  return 'aeiouyäö'.includes(last) ? `${name}${last}n` : `${name}iin`;
}

export function partitive(name: string): string {
  const last = name.slice(-1).toLowerCase();
  return 'aeiouyäö'.includes(last) ? `${name}a` : `${name}ia`;
}

const GENITIVE: Record<string, string> = { Mikko: 'Mikon', Pekka: 'Pekan' };

/** 'Samin', 'Mikon' – genitive of a demo first name. */
export function genitive(name: string): string {
  return GENITIVE[name] ?? `${name}n`;
}

/** Case- and accent-insensitive text for search ("jannitys" finds "jännitys"). */
export function normalizeText(text: string): string {
  return text.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '');
}
