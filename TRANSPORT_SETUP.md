# Build 149 Transport setup

Transport is disabled unless the server process has `ALIGN_TRANSPORT_ENABLED=1`.
The browser never receives provider URLs or credentials.

The normal `.\align.ps1 start` launcher inherits these environment variables
from the PowerShell session. If `ALIGN_OTP_URL` is set but
`ALIGN_TRANSPORT_ENABLED` is not, it enables transport for that server run.
It never writes provider URLs or tokens to the state file or logs. HERE driving
journeys are separate from this scheduled-transit service and use the
server-only `ALIGN_JOURNEY_PROVIDER=here` and `ALIGN_HERE_ROUTING_KEY`
settings in the personal planner.

For a no-copy/paste Merseyside start, double-click **Start Align Merseyside.bat**
in the Align folder. It starts the local OTP server from the prepared graph,
sets the local GraphQL URL, and then starts Align on port 8010. To stop either
the portable Java or Docker OTP server, double-click **Stop Align OTP.bat**.

The lower-level **Start Align Transport.bat** launcher also defaults to the
same local URL and is useful when the OTP server is already running.

For a local OTP server, the supplied setup uses a portable Java runtime, so
Docker Desktop and copy/paste are not required. The prepared data lives in
`C:\Align\otp-data`: a Merseyside OSM extract, the North West bus/metro feed,
and the National Rail feed. To rebuild it after a timetable refresh, double-click
**Build Align OTP Graph.bat**. After the graph build completes, double-click
**Start Align OTP.bat**, or use the one-click Merseyside launcher above. Align
uses:

```text
http://127.0.0.1:8080/otp/gtfs/v1
```

The rail archive is kept in its original form as
`C:\Align\otp-data\gb-nationalrail.gtfs.zip.orig`; the active copy is sanitized
only to remove a duplicate calendar record that OTP rejects during graph build.
The street graph is Merseyside-only. The rail feed is broader because National
Rail is supplied as a GB feed, while routing is constrained by the Merseyside
street graph and local stops.

## Minimum scheduled journey setup

The one-click launcher sets these values automatically:

```powershell
$env:ALIGN_TRANSPORT_ENABLED = '1'
$env:ALIGN_OTP_URL = 'http://127.0.0.1:8080/otp/gtfs/v1'
python app.py
```

The URL can be a hosted OTP service instead. The OpenTripPlanner graph must
contain the bus and rail timetable feeds,
OpenStreetMap walking data, and an arrive-by capable GraphQL plan endpoint.
If `ALIGN_OTP_URL` is absent or unreachable, Align returns a saved cached
journey (when one exists) and labels it scheduled-only.

## Nearby stop and station discovery

Set `ALIGN_NAPTAN_CSV` to a local NaPTAN CSV export. The adapter reads
`ATCOCode`, `CommonName`, `Latitude`, `Longitude`, and `StopType`, returning up
to five bus stops within 800 m and three rail/metro stations within 2.5 km.

```powershell

```

## Optional live status

Live status is server-side only and requires a small bridge that returns the
normalized leg contract used by `transport_service.py`:

```powershell
$env:ALIGN_BODS_LIVE_URL = 'https://your-bridge.example/bods'
$env:ALIGN_BODS_TOKEN = 'store-this-outside-the-repository'
$env:ALIGN_DARWIN_LIVE_URL = 'https://your-bridge.example/darwin'
$env:ALIGN_DARWIN_TOKEN = 'store-this-outside-the-repository'
```

The BODS bridge should accept `services` and return `legs` with matching
`service`, `from`, `to`, and `start` values plus any of
`expected_start`, `expected_end`, `cancelled`, `platform`, and `disruption`.
The Darwin bridge uses the same contract after translating licensed Darwin
identifiers. No Darwin token is bundled with Align; obtain licensed access
before enabling that bridge.

## First-run check

1. Start Align with the variables above.
2. Sign in to your Align account.
3. Open the **Transport** tab.
4. Enter a saved item as `shift:<id>` or `event:<id>`, origin and destination
   coordinates, and tick the location-consent box.
5. Confirm `/api/transport/status` reports `enabled: true` and
   `routing_configured: true`.

Current locations are request-scoped. They are not written to SQLite. Only
normalized journeys are cached in the account database, with endpoint names
replaced by `Start` and `Destination`.


## Hosted HERE transit

Set ALIGN_JOURNEY_PROVIDER=here to retain HERE driving and select HERE transit for bus/train. Transit remains disabled until ALIGN_HERE_TRANSIT_ENABLED=1 is explicitly configured after verifying account access and a no-charge quota. Reuse the server-side ALIGN_HERE_ROUTING_KEY; never put it in browser code. No Google or loopback OTP fallback is used for HERE transit.

The adapter calls https://transit.router.hereapi.com/v8/routes with arrivalTime and allowed bus/rail modes. Full UK postcodes or known Merseyside stop names are required for address resolution; postcode centres are approximate. Phone coordinates can supply the origin. Results include walking, waits, service names and rail platforms when supplied. Live-delay guarantees and fares are not provided.

Before enabling: verify the actual account plan and enforce its no-charge limit at the provider; test a public-stop journey on the hosted site. The activation flag is not a usage or billing cap. Until those steps pass, hosted HERE transit is not release-verified.

Align additionally reserves at most 1,000 transit requests across a rolling 32-day window in the shared Neon auth schema. Reservations commit before upstream requests and remain counted on failures. Database outages fail closed. This limit covers Align only: other use of the HERE account can still consume the 5,000/month provider allowance. The account observed on 25 Sep 2026 is Base Plan Self Serve v6.0, not the legacy Limited Plan.

Driving selection: set ALIGN_JOURNEY_PROVIDER=here. Hosted HERE driving and address lookups reserve from the same 1,000-call allowance before each request (a driving calculation can consume three calls). The verified account has 30,000 free monthly driving transactions and 30,000 geocoding transactions. No paid plan change is required.
