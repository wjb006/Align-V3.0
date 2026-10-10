"""Microsoft Graph mail delivery for Align v1.3 using Microsoft OAuth2.

No mailbox password or client secret is stored. The Owner supplies a Microsoft
public-client Application (Client) ID. MSAL's encrypted token cache is kept by
BetaStore. Mail is sent with delegated Microsoft Graph Mail.Send using
POST https://graph.microsoft.com/v1.0/me/sendMail.
"""
from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.request

from beta_support import BetaError
from display_dates import format_display_datetime

# MSAL already requests the standard OpenID/offline_access scopes it requires.
# Keep application scopes on one resource (Microsoft Graph).
GRAPH_SCOPES = ["Mail.Send", "User.Read"]
GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me?$select=displayName,mail,userPrincipalName"
GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"


class BetaMailer:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.flows = {}

    def _msal(self):
        try:
            import msal
            return msal
        except ImportError:
            raise BetaError(
                'Run Install Beta Support.bat to install Microsoft OAuth support.',
                'beta_support_missing', 503
            ) from None

    def _app_and_cache(self):
        settings = self.store.get_email_settings_internal()
        if not settings['sender_email'] or not settings['oauth_client_id']:
            raise BetaError('Outlook email settings have not been configured.', 'email_not_configured', 409)
        msal = self._msal()
        cache = msal.SerializableTokenCache()
        saved = self.store.load_email_token_cache()
        if saved:
            cache.deserialize(saved)
        authority = f"https://login.microsoftonline.com/{settings['oauth_authority'] or 'consumers'}"
        app = msal.PublicClientApplication(
            settings['oauth_client_id'], authority=authority, token_cache=cache
        )
        return app, cache, settings

    def start_device_connection(self, owner_user_id):
        app, cache, settings = self._app_and_cache()
        # Mail.Send is the least-privileged delegated permission for /me/sendMail.
        # User.Read lets Align confirm which Microsoft account was connected.
        # MSAL adds standard OIDC/offline_access scopes automatically.
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if 'user_code' not in flow:
            detail = str(flow.get('error_description') or flow.get('error') or '')[:220]
            self.store.set_email_status('authentication_failed', detail or 'Microsoft did not create a device sign-in request.')
            raise BetaError(
                'Microsoft could not start Outlook sign-in. Check the Client ID, public-client setting and Graph permissions.',
                'email_connection_failed', 502
            )
        flow_id = 'oauth_' + __import__('secrets').token_hex(12)
        state = {
            'status': 'waiting',
            'user_code': flow['user_code'],
            # MSAL normally supplies verification_uri, but some Microsoft
            # endpoints only return the code/message. Keep the link usable.
            'verification_uri': flow.get('verification_uri') or flow.get('verification_uri_complete') or 'https://microsoft.com/devicelogin',
            'message': flow.get('message', ''),
            'expires_in': int(flow.get('expires_in', 900)),
            'created_at': int(time.time()),
            'owner_user_id': owner_user_id,
        }
        with self.lock:
            self.flows[flow_id] = state
        threading.Thread(
            target=self._finish_flow, args=(flow_id, app, cache, flow), daemon=True
        ).start()
        return {
            'flow_id': flow_id,
            'status': 'waiting',
            'user_code': state['user_code'],
            'verification_uri': state['verification_uri'],
            'message': state['message'],
            'expires_in': state['expires_in'],
        }

    def _finish_flow(self, flow_id, app, cache, flow):
        try:
            result = app.acquire_token_by_device_flow(flow)
            if result and result.get('access_token'):
                if cache.has_state_changed:
                    self.store.set_email_token_cache(cache.serialize())
                # Connection is only fully confirmed when Graph /me succeeds,
                # but this records successful Microsoft consent immediately.
                self.store.set_email_status('connected', '')
                update = {'status': 'connected', 'message': 'Microsoft account connected.'}
            else:
                error = (result or {}).get('error_description') or (result or {}).get('error') or 'Microsoft sign-in was not completed.'
                self.store.set_email_status('authentication_failed', str(error)[:250])
                update = {'status': 'failed', 'message': 'Microsoft sign-in was not completed.'}
        except Exception:
            self.store.set_email_status('connection_failed', 'Microsoft sign-in failed.')
            update = {'status': 'failed', 'message': 'Microsoft sign-in failed.'}
        with self.lock:
            if flow_id in self.flows:
                self.flows[flow_id].update(update)

    def flow_status(self, flow_id):
        with self.lock:
            state = dict(self.flows.get(flow_id) or {})
        if not state:
            raise BetaError('Outlook connection request not found.', 'email_connection_not_found', 404)
        if state.get('status') == 'waiting' and int(time.time()) > state['created_at'] + state['expires_in']:
            state['status'] = 'expired'
            state['message'] = 'Microsoft sign-in request expired. Start again.'
        return {k: v for k, v in state.items() if k not in {'owner_user_id', 'created_at'}}

    def _access_token(self):
        app, cache, settings = self._app_and_cache()
        accounts = app.get_accounts(username=settings['sender_email']) or app.get_accounts()
        if not accounts:
            self.store.set_email_status('authentication_failed', 'Microsoft connection needs to be renewed.')
            raise BetaError('Connect the Outlook sender account first.', 'email_not_connected', 409)

        account = accounts[0]
        connected_username = str(account.get('username') or '').strip().casefold()
        configured_sender = str(settings['sender_email'] or '').strip().casefold()
        if connected_username and configured_sender and connected_username != configured_sender:
            self.store.set_email_status('authentication_failed', 'Connected Microsoft account does not match the configured sender email.')
            raise BetaError(
                'The connected Microsoft account does not match the configured sender email. Disconnect/reconnect using the dedicated Align Outlook account.',
                'email_account_mismatch', 409
            )

        result = app.acquire_token_silent(GRAPH_SCOPES, account=account)
        if not result or not result.get('access_token'):
            self.store.set_email_status('authentication_failed', 'Microsoft connection needs to be renewed for Graph Mail.Send.')
            raise BetaError(
                'Microsoft permission needs to be renewed. Connect Outlook again and approve Mail.Send.',
                'email_not_connected', 409
            )
        if cache.has_state_changed:
            self.store.set_email_token_cache(cache.serialize())
        return result['access_token'], settings

    def _graph_request(self, method, url, token, payload=None, timeout=20):
        data = None
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                body = json.loads(raw.decode('utf-8')) if raw else None
                return int(response.status), body, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                body = json.loads(raw.decode('utf-8')) if raw else None
            except Exception:
                body = None
            return int(exc.code), body, dict(exc.headers.items()) if exc.headers else {}

    def check_connection(self):
        token, settings = self._access_token()
        try:
            status, body, _ = self._graph_request('GET', GRAPH_ME_URL, token, timeout=20)
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            self.store.set_email_status('connection_failed', 'Could not connect to Microsoft Graph.')
            raise BetaError('Align could not connect to Microsoft Graph.', 'email_connection_failed', 502) from exc

        if status == 200 and isinstance(body, dict):
            account_email = str(body.get('mail') or body.get('userPrincipalName') or '').strip().casefold()
            configured = str(settings['sender_email'] or '').strip().casefold()
            if account_email and configured and account_email != configured:
                self.store.set_email_status('authentication_failed', 'Connected Microsoft account does not match the configured sender email.')
                raise BetaError(
                    'The connected Microsoft account does not match the configured sender email.',
                    'email_account_mismatch', 409
                )
            self.store.set_email_status('connected', '')
            return {
                'checked': True,
                'status': 'connected',
                'message': 'Microsoft Graph connection successful.',
                'account': body.get('mail') or body.get('userPrincipalName'),
            }

        if status in (401, 403):
            self.store.set_email_status('authentication_failed', 'Microsoft Graph rejected the saved permission.')
            raise BetaError(
                'Microsoft rejected the saved connection. Reconnect Outlook and approve Mail.Send.',
                'email_authentication_failed', 502
            )
        self.store.set_email_status('connection_failed', f'Microsoft Graph returned HTTP {status}.')
        raise BetaError('Microsoft Graph connection check failed.', 'email_connection_failed', 502)

    @staticmethod
    def _graph_error_message(body):
        try:
            code = str((body or {}).get('error', {}).get('code') or '')
            if code:
                return code[:120]
        except Exception:
            pass
        return ''

    def send_email(self, to_email, subject, text_body, html_body=None, max_attempts=3, state_callback=None):
        attempts = 0
        delays = [0, 10, 30]
        last_error = ''
        for idx in range(max_attempts):
            attempts = idx + 1
            if delays[idx]:
                time.sleep(delays[idx])
            if state_callback:
                try:
                    state_callback('sending', attempts, '')
                except Exception:
                    pass

            try:
                token, settings = self._access_token()
                content = html_body if html_body else text_body
                content_type = 'HTML' if html_body else 'Text'
                payload = {
                    'message': {
                        'subject': subject,
                        'body': {'contentType': content_type, 'content': content},
                        'toRecipients': [
                            {'emailAddress': {'address': str(to_email).strip()}}
                        ],
                    },
                    'saveToSentItems': True,
                }
                status, body, headers = self._graph_request('POST', GRAPH_SEND_URL, token, payload, timeout=25)

                if status == 202:
                    self.store.set_email_status('connected', '')
                    if state_callback:
                        try:
                            state_callback('sent', attempts, '')
                        except Exception:
                            pass
                    return {
                        'status': 'sent',
                        'attempts': attempts,
                        'safe_message': 'Microsoft Graph accepted the message.',
                    }

                if status in (401, 403):
                    code = self._graph_error_message(body)
                    last_error = 'Microsoft rejected the saved mail permission.'
                    self.store.set_email_status('authentication_failed', code or last_error)
                    if state_callback:
                        try:
                            state_callback('failed', attempts, last_error)
                        except Exception:
                            pass
                    return {'status': 'failed', 'attempts': attempts, 'safe_message': 'Reconnect Outlook and approve Mail.Send.'}

                if status == 429:
                    last_error = 'Microsoft temporarily throttled outgoing mail.'
                    if idx < max_attempts - 1:
                        retry_after = headers.get('Retry-After') or headers.get('retry-after')
                        if retry_after:
                            try:
                                time.sleep(min(max(int(retry_after), 1), 60))
                            except Exception:
                                pass
                        if state_callback:
                            try:
                                state_callback('retry_wait', attempts, last_error)
                            except Exception:
                                pass
                        continue

                if 500 <= status <= 599:
                    last_error = 'Temporary Microsoft Graph mail failure.'
                    if idx < max_attempts - 1:
                        if state_callback:
                            try:
                                state_callback('retry_wait', attempts, last_error)
                            except Exception:
                                pass
                        continue

                # 4xx other than auth/throttle is treated as permanent for this send.
                code = self._graph_error_message(body)
                last_error = 'Microsoft rejected the message.'
                self.store.set_email_status('provider_rejected', code or last_error)
                if state_callback:
                    try:
                        state_callback('failed', attempts, last_error)
                    except Exception:
                        pass
                return {'status': 'failed', 'attempts': attempts, 'safe_message': last_error}

            except BetaError as exc:
                last_error = str(exc)
                if state_callback:
                    try:
                        state_callback('failed', attempts, last_error)
                    except Exception:
                        pass
                return {'status': 'failed', 'attempts': attempts, 'safe_message': last_error}
            except (http.client.RemoteDisconnected, socket.timeout, TimeoutError) as exc:
                # The POST may have reached Graph before the connection disappeared;
                # do not automatically duplicate a possibly accepted message.
                last_error = 'The connection ended before Microsoft confirmed the send.'
                if state_callback:
                    try:
                        state_callback('not_confirmed', attempts, last_error)
                    except Exception:
                        pass
                return {'status': 'not_confirmed', 'attempts': attempts, 'safe_message': last_error}
            except (urllib.error.URLError, ConnectionError, OSError):
                last_error = 'Temporary Microsoft Graph connection failure.'
                if idx < max_attempts - 1:
                    if state_callback:
                        try:
                            state_callback('retry_wait', attempts, last_error)
                        except Exception:
                            pass
                    continue

        final_error = last_error or 'Email could not be sent.'
        if state_callback:
            try:
                state_callback('failed', attempts, final_error)
            except Exception:
                pass
        return {'status': 'failed', 'attempts': attempts, 'safe_message': final_error}

    def send_test(self, recipient):
        return self.send_email(
            recipient,
            'Align — Email test successful',
            'Your Align Microsoft Graph email connection is working.\n\n'
            'This address can now be used for tester invitations, password resets and account notifications.'
        )

    def send_invite(self, to_email, name, code, beta_url, expires_at, state_callback=None):
        safe_name = (name or 'there').strip()
        text = (
            f"Hi {safe_name},\n\nYou've been invited to try Align.\n\n"
            f"Your one-time invite code:\n{code}\n\n"
            f"Open Align: {beta_url}\n\n"
            f"This invite can only be used once and expires at {format_display_datetime(expires_at)}.\n"
            "You'll create your own private password when you join.\n\n"
            "If you weren't expecting this invitation, you can ignore this email."
        )
        return self.send_email(
            to_email, "You're invited to Align", text, state_callback=state_callback
        )

    def send_reset(self, to_email, code, beta_url, state_callback=None):
        text = (
            "A password reset was requested for your Align account.\n\n"
            f"Your one-time reset code is:\n{code}\n\n"
            f"Open Align: {beta_url}/beta-reset\n\n"
            "This code expires in 30 minutes and can only be used once. "
            "If you did not request this, you can ignore this email."
        )
        return self.send_email(
            to_email, 'Align — Reset your password', text, state_callback=state_callback
        )
