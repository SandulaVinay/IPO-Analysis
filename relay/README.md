# Telegram relay: /ongoing and /upcoming

A small Cloudflare Worker that answers two commands from your Telegram chat:

- `/ongoing` lists IPOs open for subscription now, with the last date to apply.
- `/upcoming` lists IPOs opening later.

It reads the public `state/ipo_registry.json` written by the scheduled workflow. It does not run the scheduler and does not change any data. Replies show when the registry was last checked, so you can judge how fresh they are.

Only your chat ID gets replies. Other senders are ignored without a response.

## Test locally

```powershell
cd relay
npm test
```

## Deploy (you run these; do not paste tokens into chat)

1. Create a free Cloudflare account and note your `workers.dev` subdomain.
2. Log in: `npx wrangler login` (opens a browser).
3. Set three secrets. Each command asks you to paste the value:
   - `npx wrangler secret put TELEGRAM_BOT_TOKEN` (the bot token from BotFather)
   - `npx wrangler secret put WEBHOOK_SECRET` (a random string you create with `[guid]::NewGuid().ToString("N")`)
   - `npx wrangler secret put OWNER_CHAT_ID` (your numeric Telegram chat ID)
4. Deploy: `npx wrangler deploy`. It prints a URL like `https://ipo-telegram-relay.<subdomain>.workers.dev`.
5. Register the webhook. Set the three values as environment variables in your own PowerShell session first, then run:

```powershell
$url = "https://ipo-telegram-relay.<subdomain>.workers.dev"
$body = @{ url = $url; secret_token = $env:WEBHOOK_SECRET; allowed_updates = @("message") } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$($env:TELEGRAM_BOT_TOKEN)/setWebhook" -ContentType "application/json" -Body $body
```

6. Send `/ongoing` to your bot. You should get the open list within a few seconds.

## Security notes

- The repository is public. Keep tokens, webhook secret and chat ID out of files and commits. They live only as Cloudflare secrets.
- The webhook rejects any request without the matching secret header.
- Errors are logged by type only, never with message text.
