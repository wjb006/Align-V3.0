# Align Management Studio build ethos

## Purpose
Management Studio is the local-first control hub for building, reviewing, maintaining, and safely managing Align. It is not a second production app or a second production database.

## Non-negotiable principles
1. **Preserve and reconnect, not replace and rebuild.** Keep existing user data, installed tools, feeds, routing integrations, credentials, and working configuration unless a separately approved migration requires a change.
2. **One online Align service and one production data store.** The hosted app must continue working when the user's PC is switched off. The local Studio must never become a production runtime dependency or create a competing production database.
3. **Local Studio, online app.** The Windows Studio is a local management/control hub. It can manage and publish to the hosted app only through explicit, authenticated, clearly labelled actions. Local drafts and production changes must not be confused.
4. **Protect data and credentials.** Back up before destructive or replacement operations; preserve local databases and settings; never expose secrets in UI, logs, bundles, or source control.
5. **Verify before claiming.** Distinguish implemented, automated-tested, locally-tested, and live-host-verified features. Do not call an installer, update, integration, or release complete until the relevant path has actually been tested.
6. **Safe updates and recovery.** Updates must target the intended branch, preserve user data and local configuration, detect conflicts, and provide actionable errors. Never silently overwrite local work or production settings.
7. **Calm, low-friction, accessible design.** Keep the Studio clear and consistent, with useful defaults, understandable labels, responsive layouts, keyboard access, and readable contrast.
8. **Real data, not decorative promises.** A control must be connected to its real data/action or clearly marked as a preview/not connected. Never report a service as healthy without a real check.

## Calendar view requirement
The Studio must include a dedicated **working calendar view**, separate from Calendar appearance/customisation settings. It must use the correct Align data source for the current context and provide:
- **Month** view.
- **Week** view.
- **Day** view.
- **Day / hourly time-grid** view, positioning timed events by their start and end times.
- Today and previous/next navigation.
- Clickable event details, plus create/edit flows where supported by the existing authorised event APIs.
- Clear timezone, all-day, and event-duration handling.
- Loading, empty, offline/error, and save-confirmation states.
- Explicit indication of whether the calendar is showing local Studio data or hosted Align data. Never silently mix the two.
- Responsive use on desktop and smaller screens, with keyboard-accessible controls.

The calendar view must show real persisted Align events, not sample events. It must not replace or remove the existing calendar appearance settings (colours, headings, and styling). Changes made in the Studio must be saved to the correct data store and must not publish to the website without an explicit publish action.

## Release gates
- Keep the original source and current working installation safe.
- Back up data before replacing files or applying migrations.
- Run focused calendar tests for month/week/day/hour layouts, date navigation, timed and all-day events, event editing, timezone boundaries, and empty/error states.
- Run the relevant Python and browser regression suites.
- Verify the installer/package and launch path on Windows before calling the desktop build ready.
- Verify hosted behaviour separately; a local pass is not proof of a production deployment.
- Do not alter production hosting, DNS, credentials, or database configuration without explicit approval.
