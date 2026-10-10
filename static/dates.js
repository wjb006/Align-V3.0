/* Shared user-facing dates. Stored values and API payloads stay ISO. */
(function (root) {
  const MONTHS = {
    jan: '01', feb: '02', mar: '03', apr: '04', may: '05', jun: '06',
    jul: '07', aug: '08', sep: '09', oct: '10', nov: '11', dec: '12',
  };

  function pad(value) {
    return String(value).padStart(2, '0');
  }

  function formatDisplayDate(value) {
    if (value == null || value === '') return '';
    if (value instanceof Date) {
      if (Number.isNaN(value.getTime())) return '';
      return `${pad(value.getDate())}/${pad(value.getMonth() + 1)}/${value.getFullYear()}`;
    }
    const text = String(value).trim();
    const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) return text;
    return formatDisplayDate(parsed);
  }

  function partsInZone(date, timeZone) {
    const bag = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
      timeZone: timeZone || undefined,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date).map(part => [part.type, part.value]));
    return `${bag.day}/${bag.month}/${bag.year} ${bag.hour}:${bag.minute}`;
  }

  function formatDisplayDateTime(value, timeZone) {
    if (value == null || value === '') return '';
    if (typeof value === 'number' && Number.isFinite(value)) {
      const instant = new Date(value);
      return Number.isNaN(instant.getTime()) ? '' : partsInZone(instant, timeZone || 'Europe/London');
    }
    if (value instanceof Date) {
      return Number.isNaN(value.getTime()) ? '' : partsInZone(value, timeZone);
    }
    const text = String(value).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return formatDisplayDate(text);
    if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(text)) {
      const instant = new Date(text);
      return Number.isNaN(instant.getTime()) ? text : partsInZone(instant, timeZone || 'Europe/London');
    }
    const wall = text.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    if (wall) return `${wall[3]}/${wall[2]}/${wall[1]} ${wall[4]}:${wall[5]}`;
    const parsed = new Date(text);
    return Number.isNaN(parsed.getTime()) ? text : partsInZone(parsed, timeZone || 'Europe/London');
  }

  function formatDatesInText(text) {
    const source = String(text ?? '');
    const yearInText = source.match(/\b((?:19|20)\d{2})\b/);
    const withYear = source.replace(/\b(\d{1,2}) ([A-Za-z]{3,9}) (\d{4})(?:[ T](\d{2}:\d{2}))?/g, (all, day, month, year, time) => {
      const number = MONTHS[month.toLowerCase().slice(0, 3)];
      if (!number) return all;
      const formatted = formatDisplayDate(`${year}-${number}-${pad(day)}`);
      return time ? `${formatted} ${time}` : formatted;
    });
    if (!yearInText) return withYear;
    return withYear.replace(/\b(\d{1,2}) ([A-Za-z]{3,9}) (\d{1,2}:\d{2})\b/g, (all, day, month, time) => {
      const number = MONTHS[month.toLowerCase().slice(0, 3)];
      if (!number) return all;
      return `${formatDisplayDate(`${yearInText[1]}-${number}-${pad(day)}`)} ${time}`;
    });
  }

  root.formatDisplayDate = formatDisplayDate;
  root.formatDisplayDateTime = formatDisplayDateTime;
  root.formatDatesInText = formatDatesInText;
})(typeof globalThis !== 'undefined' ? globalThis : this);
