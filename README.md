# Masala Junction reservations

This site collects table requests and lets an authenticated café administrator approve them. Approval changes the request to `confirmed` and automatically attempts to send an email confirmation.

## First-time configuration

Copy `.env.example` to `.env` for local development, then replace the placeholder values. The server now reads `.env` automatically when it starts. Do not commit real passwords, Gmail app passwords, or session secrets to the project.

Required:

- `MJ_ADMIN_PASSWORD` — password for the reservation dashboard.

Recommended for deployment:

- `MJ_SESSION_SECRET` — a long random secret, so session cookies survive server restarts.
- `MJ_COOKIE_SECURE=true` — use when the website is served over HTTPS.

To enable automatic email confirmation, configure:

- `MJ_GMAIL_ADDRESS`
- `MJ_GMAIL_APP_PASSWORD` — create this in the Gmail account after enabling 2-Step Verification.
- `MJ_GMAIL_FROM_NAME` (optional; defaults to `Masala Junction`)

For Gmail, use an App Password, not your normal Gmail password. In the Gmail account:

1. Turn on 2-Step Verification.
2. Create an App Password for Mail.
3. Paste that generated password into `MJ_GMAIL_APP_PASSWORD`.

## Run locally

Create a local `.env` file first, for example:

```env
MJ_ADMIN_PASSWORD=choose-a-long-unique-password
MJ_SESSION_SECRET=choose-a-long-random-secret
MJ_COOKIE_SECURE=false
MJ_GMAIL_ADDRESS=your-gmail-address@gmail.com
MJ_GMAIL_APP_PASSWORD=your-16-character-app-password
MJ_GMAIL_FROM_NAME=Masala Junction
```

Then start the server:

```powershell
py server.py
```

Open `http://localhost:8000` for the public site. Visit `http://localhost:8000/admin` to sign in and review reservations.

## Confirmation flow

1. A visitor requests a table. The request is saved as `pending`.
2. An administrator signs in and changes its status to `confirmed`.
3. The site attempts email delivery immediately and reports the outcome in the dashboard.
4. The administrator can use **Resend email** for a confirmed reservation.

If a service is not configured, the dashboard clearly says so and no message is sent through that service.

## Deployment note

This server currently listens on `localhost`, which is appropriate for local use. Put it behind an HTTPS-capable web server or hosting setup for public deployment, set `MJ_COOKIE_SECURE=true`, and keep all values from `.env.example` in that host's secret/environment-variable settings.
