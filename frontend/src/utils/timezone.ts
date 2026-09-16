/**
 * Central Timezone & Timestamp Formatter for NeoAlgo Dashboard.
 * 
 * TIMEZONE RULES:
 * 1. Storage & API communication is canonical UTC.
 * 2. All user-facing displays are converted to Asia/Kolkata (IST).
 * 3. Uses standard Intl.DateTimeFormat with timeZone: 'Asia/Kolkata' (no manual +5:30 arithmetic).
 * 4. Handles ISO strings with 'Z', with '+00:00' or other offsets, naive strings, and numeric epochs.
 */

export const APP_TIMEZONE = 'Asia/Kolkata';

/**
 * Parses any incoming timestamp (ISO string, epoch seconds, epoch ms)
 * into a valid JavaScript Date object, ensuring naive strings are treated as UTC.
 */
export function parseToDate(input: string | number | Date | null | undefined): Date | null {
  if (input === null || input === undefined || input === '') {
    return null;
  }

  if (input instanceof Date) {
    return isNaN(input.getTime()) ? null : input;
  }

  if (typeof input === 'number') {
    // Treat < 1e11 as seconds, >= 1e11 as milliseconds
    return new Date(input < 1e11 ? input * 1000 : input);
  }

  const raw = String(input).trim();
  if (!raw || raw === 'null' || raw === 'undefined' || raw === '—' || raw === 'N/A') {
    return null;
  }

  // Pure numeric string (e.g. "1726470804")
  if (/^\d+(\.\d+)?$/.test(raw)) {
    const num = parseFloat(raw);
    return new Date(num < 1e11 ? num * 1000 : num);
  }

  // Replace space with T for standard ISO format: '2026-09-16 07:13:24' -> '2026-09-16T07:13:24'
  let normalized = raw.replace(' ', 'T');

  // If the string lacks an explicit timezone indicator ('Z', '+HH:MM', or '-HH:MM'),
  // treat it as UTC canonical storage.
  if (!normalized.endsWith('Z') && !/[+-]\d{2}(:?\d{2})?$/.test(normalized)) {
    normalized += 'Z';
  }

  const d = new Date(normalized);
  return isNaN(d.getTime()) ? null : d;
}

interface DateParts {
  year: string;
  month: string;
  day: string;
  hour: string;
  minute: string;
  second: string;
  dayPeriod: string;
}

/**
 * Extracts Asia/Kolkata date parts using Intl.DateTimeFormat.
 */
function getKolkataParts(d: Date): DateParts {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: APP_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  });

  const parts = formatter.formatToParts(d);
  const m: Record<string, string> = {};
  for (const p of parts) {
    m[p.type] = p.value;
  }

  return {
    year: m.year || '0000',
    month: m.month || '00',
    day: m.day || '00',
    hour: m.hour || '00',
    minute: m.minute || '00',
    second: m.second || '00',
    dayPeriod: (m.dayPeriod || 'AM').toUpperCase()
  };
}

/**
 * Formats a timestamp into an Asia/Kolkata (IST) date and time string.
 * Example: '2026-09-16 12:43:24 PM'
 */
export function formatLocalDateTime(
  input: string | number | Date | null | undefined,
  fallback = '—'
): string {
  const d = parseToDate(input);
  if (!d) return fallback;
  const p = getKolkataParts(d);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second} ${p.dayPeriod}`;
}

/**
 * Formats a timestamp into an Asia/Kolkata (IST) time-only string.
 * Example: '12:43:24 PM'
 */
export function formatLocalTime(
  input: string | number | Date | null | undefined,
  fallback = '—'
): string {
  const d = parseToDate(input);
  if (!d) return fallback;
  const p = getKolkataParts(d);
  return `${p.hour}:${p.minute}:${p.second} ${p.dayPeriod}`;
}

/**
 * Formats a timestamp into an Asia/Kolkata (IST) date-only string.
 * Example: '2026-09-16'
 */
export function formatLocalDate(
  input: string | number | Date | null | undefined,
  fallback = '—'
): string {
  const d = parseToDate(input);
  if (!d) return fallback;
  const p = getKolkataParts(d);
  return `${p.year}-${p.month}-${p.day}`;
}
