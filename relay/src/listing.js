// Pure helpers for the /ongoing and /upcoming Telegram replies.
// Input is the public IPO registry (state/ipo_registry.json). No network access here.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function partsIst(date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
    minute: get("minute"),
  };
}

/** Today's date in India (IST) as YYYY-MM-DD. */
export function istDate(now = new Date()) {
  const p = partsIst(now);
  return `${p.year}-${p.month}-${p.day}`;
}

/** "2026-11-23" -> "23 Nov 2026". Returns null for anything that is not an ISO date. */
export function formatDate(iso) {
  if (!ISO_DATE.test(iso || "")) return null;
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** Time the registry was last checked, e.g. "22 Nov 2026, 12:41 IST". */
export function formatCheckedAt(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
  const p = partsIst(date);
  const day = Number(p.day);
  const month = MONTHS[Number(p.month) - 1];
  return `${day} ${month} ${p.year}, ${p.hour}:${p.minute} IST`;
}

function dateField(ipo, side) {
  const verified = ipo[`verified_${side}_date`];
  if (ISO_DATE.test(verified || "")) return { date: verified, verified: true };
  const announced = ipo[`announced_${side}_date`];
  if (ISO_DATE.test(announced || "")) return { date: announced, verified: false };
  return { date: null, verified: false };
}

function priceBand(ipo) {
  const low = Number(ipo.min_price);
  const high = Number(ipo.max_price);
  if (!Number.isFinite(low) || !Number.isFinite(high) || low <= 0 || high <= 0) {
    return "price not available";
  }
  const fmt = (n) => `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  return low === high ? fmt(low) : `${fmt(low)}–${fmt(high)}`;
}

/**
 * Split registry entries into IPOs open now and IPOs opening later.
 * IPOs whose closing date has passed are left out.
 */
export function classifyIpos(registry, today) {
  const open = [];
  const upcoming = [];
  for (const ipo of registry?.ipos ?? []) {
    const opening = dateField(ipo, "open");
    const closing = dateField(ipo, "close");
    if (!opening.date && !closing.date) continue;
    if (closing.date && closing.date < today) continue;

    const row = {
      name: String(ipo.company_name || ipo.symbol || "Unknown issuer"),
      symbol: String(ipo.symbol || "—"),
      openDate: opening.date,
      closeDate: closing.date,
      verified: opening.verified && closing.verified,
      conflict: ipo.status === "SOURCE_CONFLICT",
      band: priceBand(ipo),
    };
    if (opening.date && opening.date > today) {
      upcoming.push(row);
    } else {
      open.push(row);
    }
  }
  const byClose = (a, b) => (a.closeDate || "9999").localeCompare(b.closeDate || "9999");
  const byOpen = (a, b) => (a.openDate || "9999").localeCompare(b.openDate || "9999");
  open.sort(byClose);
  upcoming.sort(byOpen);
  return { open, upcoming };
}

function rowLine(row, kind) {
  const star = row.verified ? "" : "*";
  const when =
    kind === "open"
      ? `closes ${formatDate(row.closeDate) ?? "date not available"}`
      : `opens ${formatDate(row.openDate) ?? "date not available"}` +
        (row.closeDate ? `, closes ${formatDate(row.closeDate)}` : "");
  const conflict = row.conflict ? " — official sources disagree on dates; verify" : "";
  return `- ${row.name} (${row.symbol})${star}: ${when}, ${row.band}${conflict}`;
}

/**
 * Build the Telegram reply for one command.
 * kind: "open" for /ongoing, "upcoming" for /upcoming.
 * meta: { checkedAt: Date|null }
 */
export function formatReply(result, kind, meta = {}) {
  const rows = kind === "open" ? result.open : result.upcoming;
  const title = kind === "open" ? "Open now" : "Upcoming";
  const lines = [`${title} (${rows.length}):`];
  if (rows.length === 0) {
    lines.push(kind === "open" ? "No IPOs are open for subscription right now." : "No upcoming IPOs in our list.");
  } else {
    for (const row of rows) lines.push(rowLine(row, kind));
  }
  lines.push("");
  if (rows.some((r) => !r.verified)) {
    lines.push("* Dates are announced but not yet verified against the official filing.");
  }
  const checked = formatCheckedAt(meta.checkedAt);
  lines.push(checked ? `Last checked: ${checked}.` : "Last checked time unavailable.");
  lines.push("Information only, not investment advice.");
  return lines.join("\n");
}
