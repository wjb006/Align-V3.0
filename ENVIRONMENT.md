# Environment settings

Set deployment secrets in the service environment. `.env.example` lists setting names only; never add values there or commit a local `.env` file.

| Setting | Purpose |
|---|---|
| `PORT` | Port supplied by the hosting platform. |
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
