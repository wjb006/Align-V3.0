# Environment settings

Set deployment secrets in the service environment. `.env.example` lists setting names only; never add values there or commit a local `.env` file.

| Setting | Purpose |
|---|---|
| `PORT` | Port supplied by the hosting platform. |
| `ALIGN_PUBLIC_URL` | Canonical public HTTPS address used in account email links, for example `https://getalign.co.uk`. |
| `ALIGN_PORT` | Local server port. |
| `ALIGN_HOSTING_MODE` | Selects persistent hosted mode or a disposable preview. |
| `ALIGN_BETA_MODE` | Legacy configuration name for Align's account-scoped hosted mode. The user-facing product is Align in both local and hosted use. |
| `ALIGN_DATABASE_BACKEND` | Selects SQLite or PostgreSQL. |
| `DATABASE_URL` | Connection string for this Align installation's own Neon database. |
| `ALIGN_PREVIEW_PASSWORD` | Initial Owner password during hosted bootstrap. |
| `ALIGN_ADMIN_PASSWORD` | Local network administration password. |
| `ALIGN_ADMIN_PORT` | Local PC-only administration port. |
| `ALIGN_SSL_CERT`, `ALIGN_SSL_KEY` | Local HTTPS certificate and private key paths. |
| `ALIGN_PUBLISH_URL`, `ALIGN_PUBLISH_KEY` | Optional Owner Studio publish target and authentication key. |
| `ALIGN_TEST_POSTGRES_URL` | CI-only PostgreSQL integration database. |
| `ALIGN_CREDENTIAL_KEY` | Persistent key for encrypted saved credentials. |
| `ALIGN_TRANSPORT_ENABLED` | Enables journey planning when a supported provider is configured. |
| `ALIGN_JOURNEY_PROVIDER` | Journey provider selection. |
| `ALIGN_HERE_ROUTING_KEY`, `ALIGN_HERE_TRANSIT_ENABLED` | HERE routing and transit configuration. |
| `ALIGN_GOOGLE_ROUTES_KEY` | Optional Google Routes credential. |
| `ALIGN_OTP_URL` | OpenTripPlanner base URL. |
| `ALIGN_NAPTAN_CSV` | NaPTAN stops data path. |
| `ALIGN_BODS_LIVE_URL`, `ALIGN_BODS_TOKEN` | Bus Open Data Service endpoint and token. |
| `ALIGN_DARWIN_LIVE_URL`, `ALIGN_DARWIN_TOKEN` | Darwin rail endpoint and token. |

Local databases, credential files, `.env` files, built executables and the OTP JDK runtime are excluded from Git. Get the OTP runtime from a trusted JDK 21 distribution and keep the generated `dist` executables as release artifacts.

## Outlook email delivery

Align Management Studio → **Owner settings & integrations** contains the Outlook setup and test-message flow. Register an app in Microsoft Entra, enable its public-client/device-code flow, add Microsoft Graph delegated `Mail.Send` and `User.Read`, then enter the Application (client) ID, Outlook sender address, and matching account type in Studio. Save, connect the mailbox using Microsoft's device sign-in, check the connection, and send a test email before inviting users.

Align sends through Microsoft Graph as the connected Outlook mailbox; it does not store a mailbox password or app client secret. The encrypted token cache uses `ALIGN_CREDENTIAL_KEY`. Hosted deployments must keep that key persistent across restarts. Invitations send the one-time account setup code, forgot-password requests send recovery codes, and successful password or login-email changes send security notices. Normal sign-in remains email and password.
