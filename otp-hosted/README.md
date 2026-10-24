# Hosted OpenTripPlanner service

This folder is the isolated Render Docker service context for the Align V3.0 OTP backend. It must not be deployed as the Align web app.

## Required before production

- A persistent disk mounted at `/var/opentripplanner`.
- A Render plan with enough memory for building and serving the Merseyside graph (plan for at least 4 GB RAM; graph build can require more).
- Current Merseyside OSM data, North West bus/Metro GTFS, and National Rail GTFS. Validate licensing and feed freshness before each graph build.
- Build the graph once and retain `graph.obj` on the persistent disk; do not rebuild on each restart.
- After deployment, configure the Align service's `ALIGN_OTP_URL` to `https://<service-host>/otp/gtfs/v1` and enable transport only after a successful GraphQL test.

The Render service creation connector does not expose persistent-disk configuration. A production deployment cannot be marked complete until a persistent disk is attached in the Render dashboard and the graph is built successfully. This scaffold intentionally does not enable OTP in Align automatically.