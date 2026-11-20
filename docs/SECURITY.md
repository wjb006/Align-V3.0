# Account security

## Two-step sign-in

Migration `migrations/postgres/159_account_security.postgres.sql` adds `totp_secret`, `totp_enabled`, and `beta_login_challenges` in `align_auth`. Migration `160_password_change_challenge.postgres.sql` must then add the challenge `purpose` column. Both migrations are additive and must be applied explicitly; the running app does not apply them. The TOTP login path reads `purpose`, so migration 160 is required before enabling this flow, not just for the separate breached-password change path.

Until migrations 159 and 160 are applied and the service is restarted, sign-in stays email and password and Management Studio is unchanged.

After both migrations are applied and the service is restarted:

1. The owner signs in, then opens a signed-in session and calls `POST /api/beta/totp/start`. The response contains the secret and an `otpauth://` URI once. Store it in an authenticator.
2. `POST /api/beta/totp/confirm` with the 6-digit code turns it on and signs every session out.
3. The next sign-in asks for the code. The password alone does not create a session.
4. Management Studio stays blocked for the owner until two-step sign-in is on. Testers can turn it on; it is not required for them.
5. The sign-in page shows the code field after the password is accepted (`/login?step=totp`).

`ALIGN_OWNER_TOTP=optional` disables the studio block. Do not set that on the hosted service. Tests set it so existing suites can sign in as the owner.

## Login limiting

Eight wrong passwords for the same email and client within 15 minutes return HTTP 429. The limit is stored in `beta_rate_events`, so a process restart does not clear it. The older in-memory delay still applies as well.

## Breach check

Setting or changing a password checks the SHA-1 range API at `https://api.pwnedpasswords.com/range/`. Only the first five characters of the hash are sent. A listed password is rejected. If the service cannot be reached, the password is not saved.

Signing in with a password that is already on that list does not open the app. Align asks for a new password first. If the breach list cannot be reached during sign-in, the existing password is still accepted so an outage does not lock the account.

Apply `migrations/postgres/160_password_change_challenge.postgres.sql` after migration 159 so hosted sign-in can store that password-change step. The rollback file drops the column. The running app does not apply either file.

`ALIGN_BREACH_CHECK=0` skips the lookup. Leave it unset on the hosted service.

## Cookies

`align_beta` is `HttpOnly`, `SameSite=Lax`, and `Secure` when `ALIGN_PUBLIC_URL` is HTTPS or the request arrived over HTTPS. The five-minute `align_totp` cookie that holds the unfinished second step uses the same flags.
