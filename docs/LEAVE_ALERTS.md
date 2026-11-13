# Leave-now alerts

Each account opts in separately. The setting is stored in that account's database, so one tester cannot change or receive another tester's alert.

Align notifies the phone when the saved journey says it is time to leave.

- The leave time is the first saved journey step, minus the allowance written in the journey notes.
- If `ALIGN_BODS_LIVE_URL` and `ALIGN_BODS_TOKEN`, or `ALIGN_DARWIN_LIVE_URL` and `ALIGN_DARWIN_TOKEN`, are set, a matched delay moves the alert later by the number of minutes that feed reports. No delay is added when the feed is missing or does not match.
- The account's weather settings can add the rain or storm buffer already used by journey planning. That moves the alert earlier.
- The lock-screen text is `Time to leave for {event}.` It does not include the address. Other reminders stay generic.

On iPhone, notifications work from the installed Home Screen app on iOS 16.4 or later. Open Align from that icon, then Phone notifications, and turn on **Tell me when to leave**. An ordinary Safari tab cannot subscribe.

## Keys Will sets on the hosted service

Generate a VAPID key pair locally and store it in Render. Do not commit the private key.

```bash
python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.private_pem().decode())"
```

| Variable | Purpose |
|---|---|
| `ALIGN_PUSH_PUBLIC_KEY` | URL-safe base64 uncompressed VAPID public key. The phone uses this to subscribe. |
| `ALIGN_PUSH_PRIVATE_KEY` | VAPID private key. Server only. |
| `ALIGN_PUSH_CRON_SECRET` | Bearer token for `POST /api/phone-push/dispatch`. |

`pywebpush` accepts the private key in the form already used by `phone_push.send`. A URL-safe base64 PKCS8 key also works for the test helper in `test_phone_push.py`.

Bus and rail delay keys are listed in `TRANSPORT_SETUP.md`. This alert uses whatever those feeds return. It does not call them with a home address.

## Scheduler

`deploy/render-leave-alerts-cron.yaml` is a prepared Render cron. It is not part of the live blueprint, so applying this branch does not create the job. Will can add it after choosing to run the scheduler:

- Schedule: `* * * * *`
- Command: `curl -fsS -X POST -H "Authorization: Bearer $ALIGN_PUSH_CRON_SECRET" "$ALIGN_PUBLIC_URL/api/phone-push/dispatch"`
- Env: `ALIGN_PUSH_CRON_SECRET`, `ALIGN_PUBLIC_URL=https://www.getalign.co.uk`

The running web service also needs the three push variables above. Until they are set, the phone page says the server setup is not finished and no alert is sent.
