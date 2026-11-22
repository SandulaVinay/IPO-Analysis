// Telegram webhook relay for on-demand IPO questions.
// Only the owner's chat is answered. Replies come from the public state branch,
// which the scheduled workflow updates. No IPO data is computed here.

import { classifyIpos, formatReply, istDate } from "./listing.js";

export const REGISTRY_URL =
  "https://raw.githubusercontent.com/SandulaVinay/IPO-Analysis/state/state/ipo_registry.json";
export const LAST_COMMIT_URL =
  "https://api.github.com/repos/SandulaVinay/IPO-Analysis/commits?sha=state&path=state/ipo_registry.json&per_page=1";

const HELP_TEXT = [
  "Commands:",
  "/ongoing - IPOs open for subscription now, with last date to apply",
  "/upcoming - IPOs opening later",
  "Data is from the last scheduled check, not live.",
].join("\n");

export function defaultDeps(env) {
  return {
    now: () => new Date(),
    async fetchRegistry() {
      const res = await fetch(REGISTRY_URL, { cf: { cacheTtl: 60, cacheEverything: true } });
      if (!res.ok) throw new Error(`registry HTTP ${res.status}`);
      return res.json();
    },
    async fetchCheckedAt() {
      try {
        const res = await fetch(LAST_COMMIT_URL, {
          headers: { Accept: "application/vnd.github+json", "User-Agent": "ipo-telegram-relay" },
        });
        if (!res.ok) return null;
        const commits = await res.json();
        const when = commits?.[0]?.commit?.committer?.date;
        return when ? new Date(when) : null;
      } catch {
        return null;
      }
    },
    async send(chatId, text) {
      const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: true }),
      });
      if (!res.ok) throw new Error(`telegram HTTP ${res.status}`);
    },
  };
}

/**
 * Handle one Telegram update. Returns the command name that was answered, or null.
 * Messages from any chat other than the owner are ignored without a reply.
 */
export async function handleUpdate(update, env, deps = defaultDeps(env)) {
  const msg = update?.message ?? update?.edited_message;
  if (!msg?.chat) return null;
  if (String(msg.chat.id) !== String(env.OWNER_CHAT_ID)) return null;

  const command = String(msg.text ?? "").trim().split(/\s+/)[0].toLowerCase().split("@")[0];

  if (command !== "/ongoing" && command !== "/upcoming") {
    await deps.send(msg.chat.id, HELP_TEXT);
    return "help";
  }

  try {
    const [registry, checkedAt] = await Promise.all([deps.fetchRegistry(), deps.fetchCheckedAt()]);
    const result = classifyIpos(registry, istDate(deps.now()));
    const kind = command === "/ongoing" ? "open" : "upcoming";
    await deps.send(msg.chat.id, formatReply(result, kind, { checkedAt }));
  } catch {
    await deps.send(msg.chat.id, "Could not read the IPO list right now. Try again in a few minutes.");
  }
  return command;
}

export default {
  async fetch(request, env) {
    // Plain GET is a health check; Telegram always sends POST.
    if (request.method !== "POST") return new Response("ok");
    if (!env.WEBHOOK_SECRET || request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("bad request", { status: 400 });
    }
    try {
      await handleUpdate(update, env);
    } catch (err) {
      // Log the error type only; never log message text or secrets.
      console.log("relay error", err?.name ?? "unknown");
    }
    // Always 200 so Telegram does not keep retrying the same update.
    return new Response("ok");
  },
};
