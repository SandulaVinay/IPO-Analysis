import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyIpos, formatReply, formatDate, formatCheckedAt, istDate } from "../src/listing.js";
import { handleUpdate } from "../src/worker.js";

// Mirrors the three entries in state/ipo_registry.json on 22 Nov 2026.
const registry = {
  ipos: [
    {
      company_name: "Crystal Crop Protection Limited", symbol: "CRYSTALCP", status: "IPO_DISCOVERED",
      verified_open_date: "2026-11-18", verified_close_date: "2026-11-20",
      min_price: 259, max_price: 272,
    },
    {
      company_name: "Mahanadi Coalfields Limited", symbol: "MAHACOAL", status: "IPO_DISCOVERED",
      verified_open_date: "2026-11-19", verified_close_date: "2026-11-23",
      min_price: 129, max_price: 136,
    },
    {
      company_name: "Watrana Rentals Limited", symbol: "WATRANA", status: "IPO_DISCOVERED",
      announced_open_date: "2026-11-19", announced_close_date: "2026-11-23",
      min_price: 232, max_price: 245,
    },
    {
      company_name: "Example Ltd", symbol: "EXMPL", status: "IPO_DISCOVERED",
      verified_open_date: "2026-11-25", verified_close_date: "2026-11-27",
      min_price: 100, max_price: 110,
    },
    {
      company_name: "Conflict Ltd", symbol: "CONF", status: "SOURCE_CONFLICT",
      verified_open_date: "2026-11-24", verified_close_date: "2026-11-26",
      min_price: 50, max_price: 55,
    },
  ],
};

test("classifies open, upcoming and closed IPOs against today", () => {
  const { open, upcoming } = classifyIpos(registry, "2026-11-22");
  assert.deepEqual(open.map((r) => r.symbol), ["MAHACOAL", "WATRANA"]);
  assert.deepEqual(upcoming.map((r) => r.symbol), ["CONF", "EXMPL"]);
  // Crystal Crop closed on 20 Nov, so it appears in neither list.
  assert.equal([...open, ...upcoming].some((r) => r.symbol === "CRYSTALCP"), false);
});

test("marks announced-only dates as unverified", () => {
  const { open } = classifyIpos(registry, "2026-11-22");
  const watrana = open.find((r) => r.symbol === "WATRANA");
  assert.equal(watrana.verified, false);
  assert.equal(open.find((r) => r.symbol === "MAHACOAL").verified, true);
});

test("ongoing reply shows last date to apply and price band", () => {
  const result = classifyIpos(registry, "2026-11-22");
  const text = formatReply(result, "open", { checkedAt: new Date("2026-11-22T07:11:47Z") });
  assert.match(text, /^Open now \(2\):/);
  assert.match(text, /Mahanadi Coalfields Limited \(MAHACOAL\): closes 23 Nov 2026, ₹129–₹136/);
  assert.match(text, /Watrana Rentals Limited \(WATRANA\)\*: closes 23 Nov 2026, ₹232–₹245/);
  assert.match(text, /Last checked: 22 Nov 2026, 12:41 IST\./);
  assert.match(text, /not yet verified/);
  assert.doesNotMatch(text, /Upcoming/);
});

test("upcoming reply shows opening and closing dates", () => {
  const result = classifyIpos(registry, "2026-11-22");
  const text = formatReply(result, "upcoming", { checkedAt: null });
  assert.match(text, /^Upcoming \(2\):/);
  assert.match(text, /Example Ltd \(EXMPL\): opens 25 Nov 2026, closes 27 Nov 2026, ₹100–₹110/);
  assert.match(text, /official sources disagree on dates; verify/);
  assert.match(text, /Last checked time unavailable\./);
});

test("empty lists say so plainly", () => {
  const empty = { open: [], upcoming: [] };
  assert.match(formatReply(empty, "open"), /No IPOs are open for subscription right now\./);
  assert.match(formatReply(empty, "upcoming"), /No upcoming IPOs in our list\./);
});

test("date and time helpers format Indian dates", () => {
  assert.equal(formatDate("2026-11-03"), "3 Nov 2026");
  assert.equal(formatDate("not a date"), null);
  assert.equal(formatCheckedAt(new Date("2026-11-22T07:11:47Z")), "22 Nov 2026, 12:41 IST");
  assert.equal(istDate(new Date("2026-11-21T20:00:00Z")), "2026-11-22");
});

function fakeDeps(overrides = {}) {
  const sent = [];
  return {
    sent,
    deps: {
      now: () => new Date("2026-11-22T07:11:47Z"),
      fetchRegistry: async () => registry,
      fetchCheckedAt: async () => new Date("2026-11-22T07:11:47Z"),
      send: async (chatId, text) => sent.push({ chatId, text }),
      ...overrides,
    },
  };
}

const env = { OWNER_CHAT_ID: "111", WEBHOOK_SECRET: "s", TELEGRAM_BOT_TOKEN: "t" };
const update = (chatId, text) => ({ message: { chat: { id: chatId }, text } });

test("owner /ongoing gets the open list", async () => {
  const { sent, deps } = fakeDeps();
  assert.equal(await handleUpdate(update(111, "/ongoing"), env, deps), "/ongoing");
  assert.equal(sent.length, 1);
  assert.match(sent[0].text, /^Open now/);
});

test("owner /upcoming works with a bot-name suffix and extra spaces", async () => {
  const { sent, deps } = fakeDeps();
  await handleUpdate(update(111, "  /Upcoming@IPOAlertsBot  "), env, deps);
  assert.match(sent[0].text, /^Upcoming/);
});

test("other chats are ignored without any reply", async () => {
  const { sent, deps } = fakeDeps();
  assert.equal(await handleUpdate(update(999, "/ongoing"), env, deps), null);
  assert.equal(sent.length, 0);
});

test("unknown text gets the help reply", async () => {
  const { sent, deps } = fakeDeps();
  assert.equal(await handleUpdate(update(111, "hello"), env, deps), "help");
  assert.match(sent[0].text, /\/ongoing/);
});

test("a registry failure gives a plain error, not a stack trace", async () => {
  const { sent, deps } = fakeDeps({ fetchRegistry: async () => { throw new Error("HTTP 503"); } });
  await handleUpdate(update(111, "/ongoing"), env, deps);
  assert.match(sent[0].text, /Could not read the IPO list/);
  assert.doesNotMatch(sent[0].text, /HTTP 503/);
});

test("webhook rejects requests without the Telegram secret header", async () => {
  const worker = (await import("../src/worker.js")).default;
  const res = await worker.fetch(
    new Request("https://relay.example", { method: "POST", body: "{}", headers: { "X-Telegram-Bot-Api-Secret-Token": "wrong" } }),
    { WEBHOOK_SECRET: "right", OWNER_CHAT_ID: "111", TELEGRAM_BOT_TOKEN: "t" },
  );
  assert.equal(res.status, 403);
});

test("GET is a health check and returns ok", async () => {
  const worker = (await import("../src/worker.js")).default;
  const res = await worker.fetch(new Request("https://relay.example", { method: "GET" }), {});
  assert.equal(await res.text(), "ok");
});
