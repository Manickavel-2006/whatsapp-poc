# WhatsApp Cloud API POC

A standalone proof-of-concept for Meta's WhatsApp Cloud API, built with FastAPI. It verifies
Meta's webhook handshake, receives and validates incoming webhook events (messages and status
updates), replies "Hi, this is a test" to any incoming text message, and exposes a manual
endpoint to send a template message. There's no AI or agent logic here — it's purely to prove
the messaging plumbing (webhook in, API call out) works end to end.

## Install and run

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in the values, see below
uvicorn main:app --reload
```

The app listens on `http://localhost:8000` by default.

## Expose it with ngrok

Meta needs a public HTTPS URL to call your webhook. In a separate terminal:

```bash
ngrok http 8000
```

Copy the `https://...ngrok-free.app` URL ngrok gives you. In the Meta App Dashboard, under
**WhatsApp > Configuration > Webhook**, set the callback URL to:

```
https://<your-ngrok-subdomain>.ngrok-free.app/webhook
```

Set the verify token to the same value you put in `WHATSAPP_VERIFY_TOKEN`.

Note: ngrok issues a new random URL every time you restart it (on the free tier), so you'll
need to update the webhook URL in the Meta dashboard each time you restart ngrok.

## Environment variables

All of these come from the Meta App Dashboard, on the **WhatsApp > API Setup** page (and
**App Settings > Basic** for the app secret):

| Variable | Where to get it |
|---|---|
| `WHATSAPP_ACCESS_TOKEN` | API Setup page — temporary token (24h) by default, or generate a permanent one via a system user under Business Settings |
| `WHATSAPP_PHONE_NUMBER_ID` | API Setup page, under "From" / the test phone number |
| `WHATSAPP_VERIFY_TOKEN` | You make this up yourself; enter the same value when configuring the webhook |
| `WHATSAPP_APP_SECRET` | App Settings > Basic, next to "App Secret" (click "Show") |

## Testing

1. **Incoming message flow**: from the WhatsApp account you added as a test recipient, send a
   text message to the test business number. You should receive "Hi, this is a test" back, and
   see the payload logged in the console.
2. **Template send flow**: with the server running, open `http://localhost:8000/docs` (or use
   curl) and call `POST /send-template` with a body like:

   ```json
   { "to": "15551234567" }
   ```

   This sends the `hello_world` template to that number (must be in international format, no
   `+` or leading zeros, and must be a number Meta allows your app to message — e.g. a
   registered test recipient while in development mode).

## Sample payloads

Every webhook call that passes signature verification is appended as one JSON line to
`payloads.jsonl` in this directory. As you test with real messages — text, images, replies,
and delivery/read status updates — this file will accumulate real sample payloads for each
shape, useful for building out a fuller integration later.
