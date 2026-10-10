# Phone notifications

Opt-in Web Push for the hosted beta. Uses existing account-scoped `settings`
storage, preserving SQLite and the hosted adapter without schema migrations.
Includes personal reminders and pending work alerts only. Calendar/category
reminders must create explicit due reminders before they can use this sender.

## Server configuration

Set `ALIGN_PUSH_PRIVATE_KEY` (base64 DER P-256 private key),
`ALIGN_PUSH_PUBLIC_KEY` (base64url uncompressed P-256 public key), and
`ALIGN_PUSH_CRON_SECRET` (random 32-byte or stronger token) on the beta service.
Keep keys stable across deployments. Never commit them or place them in URLs.
The push library uses HTTPS with redirects disabled and allows only known
Apple, Google and Mozilla push endpoints.

## Free scheduler

On cron-job.org, create **Align reminder delivery**, once per minute, HTTPS POST
to `https://beta.getalign.co.uk/api/phone-push/dispatch` with custom header
`Authorization: Bearer <ALIGN_PUSH_CRON_SECRET>`. Empty body. Do not save
response bodies. Do not place Align login details or reminder data in the job.
Keep disabled until the endpoint is deployed and manually tested. Check job
history after enabling. HTTP 401 means bad credentials, 503 means incomplete
configuration or delivery failure. The endpoint responds with counts only.

Single Render instance/process is required: process-local locking prevents
overlapping runs. For multiple workers, replace with database leases first.
Each run has an 18-second work budget plus the last provider timeout (4s).
Overdue reminders are retried for 24 hours, but only when due after the device
opted in. Accepted sends have durable per-device receipts; a crash between
provider acceptance and saving may resend, using the same notification tag.
404/410 subscriptions are removed. Other failures retry on the next run.
This beta-sized sender is not a high-volume queue; monitor backlog before
adding many accounts. Free hosting can sleep or hit limits; timing is not
guaranteed and this must not be the sole medication or critical reminder.

## Phone setup and verification

On iPhone (iOS 16.4+), add Align to the Home Screen from Safari, open that icon,
tap the bell, then **Enable on this device**. Accept permission and send a test.
The push provider accepting a test does not prove it appeared on the phone.
Create a personal reminder a few minutes ahead, close Align, and confirm arrival.
Check Focus settings and notification permissions if it does not appear.
Private generic text is used; no prescription/appointment titles are sent.
Disable on each device before sharing it. Signing out alone does not disable
push. Subscription renewal/key rotation requires re-enabling on the device.

## Checks

`python -m unittest test_phone_push`
`node --check static/phone-notifications.js`
`node --check static/service-worker.js`
