# Align Build 150 — OTP1 update

OpenTripPlanner is now the default event journey provider. No Google API key is needed for bus/train planning. Bills formulas, automatic weather, uploaded journey icons and phone-friendly Owner editing are included.

Start the local app with Start Align Merseyside.bat. For phone beta access, start OTP with Start Align OTP.bat, then use the existing Start Align Public Beta.bat launcher. The beta URL can change when its quick tunnel restarts. Keep this computer running while using this local setup; the ZIP does not deploy a cloud server.

Travel defaults to your saved home address. Put a full UK postcode in Personal details and in event destinations, or use an exact local station name. A postcode centre is approximate; choose phone location for a more precise origin. Only the postcode is sent to Postcodes.io, not the complete address. OTP finds routes through nearby stops with walking legs. Live bus/train delay feeds are not configured; results are scheduled times. Driving is available through Apple Maps.

Owner editing: sign in at /beta-login, then open /owner-builder. Owner controls: /beta-admin. Owner sessions, existing user records and credentials are not included in this update archive. For Bills: Owner → Database layouts → Add Bills template; review and publish. All results/records remain private to each account.

Easy edits: bill_calculations.py (rounding and formula examples), static/journey-breakdown.js (uploaded icon mapping), personal_otp.py (OTP mode mapping and result limit). Formulas themselves are edited in Owner layouts using [Amount] - [Paid], etc.

Installation on an existing Align copy:
1. Extract the update ZIP to a separate folder.
2. Close Align and OTP before installing. Do not delete your existing app folder.
3. Run Install-Update.ps1. It verifies package hashes and backs up replaced files before copying the update into C:\Align\Align_App.
4. Start OTP and Align again, then refresh the phone app to load asset revision 150-otp1.

This is an update, not a standalone runtime installation. Existing Python environment, OTP JAR, graph and feeds are required. Restored Java bin files are included for the existing Temurin 25.0.4.1 runtime. No database, account, password, token, certificate, feed, graph or virtual environment is distributed.

Validation: the existing Build 150 verifier and regression suite are used without changing their acceptance criteria. This is not a Build 144 source merge or certification. Live local OTP queries returned bus, train and mixed itineraries between public test locations in Birkenhead/Liverpool. Timetables will need periodic refresh as feeds expire.
