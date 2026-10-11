"""Beta sign-in, owner administration, and beta page routing.

Route dispatch lives here so AlignHandler can keep the shared request gates.
Names used by tests stay on app and are read from the passed app module.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs

from beta_support import BetaError


def handle_get(handler, app, parsed) -> bool:
    self = handler
    APP_VERSION = app.APP_VERSION
    BETA_MODE = app.BETA_MODE
    BUILD_VERSION = app.BUILD_VERSION
    beta_mailer = app.beta_mailer
    beta_store = app.beta_store
    if BETA_MODE and parsed.path == '/api/beta/status':
        try: public_key=beta_store().public_key()
        except ValueError: public_key=''
        self.send_json(200,{'beta':True,'build_version':BUILD_VERSION,'app_version':APP_VERSION,'terms_version':__import__('beta_support').TERMS_VERSION,'privacy_version':__import__('beta_support').PRIVACY_VERSION,'credential_public_key':public_key})
        return True
    if BETA_MODE and parsed.path == '/api/beta/me':
        self.send_json(200,self.beta_me_payload(self.beta_user())); return True
    if BETA_MODE and parsed.path == '/api/beta/admin':
        if not self.require_admin(): return True
        self.send_json(200,{'users':beta_store().list_users(),'feedback':beta_store().feedback(),'email_settings':beta_store().email_settings_public(),'audit':beta_store().audit_events(50)}); return True
    if BETA_MODE and parsed.path == '/api/beta/owner/email-settings':
        if not self.require_admin(): return True
        self.send_json(200,beta_store().email_settings_public()); return True
    if BETA_MODE and parsed.path.startswith('/api/beta/owner/email-oauth/status'):
        if not self.require_admin(): return True
        flow_id=parse_qs(parsed.query).get('flow_id',[''])[0]
        self.send_json(200,beta_mailer().flow_status(flow_id)); return True
    return False


def handle_form(handler, app, path) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    beta_store = app.beta_store
    # v1.3 keeps the proven Safari-safe browser-navigation handoff for
    # login, invite completion and password reset. Cookies are committed
    # before the 303 redirect is followed.
    if BETA_MODE and path in {'/beta-login-submit','/beta-invite-complete','/beta-reset-submit'}:
        if not self.beta_same_origin(): return True
        length=int(self.headers.get('Content-Length','0') or '0')
        if length>64_000: raise BetaError('Authentication request is too large.')
        form=parse_qs(self.rfile.read(length).decode('utf-8','replace'))
        if path=='/beta-login-submit':
            email=(form.get('email') or [''])[0]
            credential=(form.get('password') or form.get('code') or [''])[0]
            row,token=beta_store().login(email,credential,self.client_address[0])
            if not row:
                self.send_response(303); self.send_header('Location','/login?error=invalid'); self.send_header('Cache-Control','no-store'); self.end_headers(); return True
            target='/terms' if not beta_store().terms_current(row) else ('/welcome' if not row['welcome_seen_at'] else '/')
            self.send_response(303); self.send_header('Location',target); self.send_header('Cache-Control','no-store'); self.send_beta_cookie(token); self.end_headers(); return True
        if path=='/beta-invite-complete':
            email=(form.get('email') or [''])[0]; code=(form.get('invite_code') or [''])[0]
            password=(form.get('password') or [''])[0]; confirm=(form.get('confirm_password') or [''])[0]
            if password!=confirm:
                self.send_response(303); self.send_header('Location','/invite?error=match'); self.send_header('Cache-Control','no-store'); self.end_headers(); return True
            try:
                row,token=beta_store().complete_invite(email,code,password,self.client_address[0])
            except BetaError as error:
                label='password' if error.code=='invalid_password' else 'invite'
                self.send_response(303); self.send_header('Location',f'/invite?error={label}'); self.send_header('Cache-Control','no-store'); self.end_headers(); return True
            self.send_response(303); self.send_header('Location','/terms'); self.send_header('Cache-Control','no-store'); self.send_beta_cookie(token); self.end_headers(); return True
        if path=='/beta-reset-submit':
            code=(form.get('reset_code') or [''])[0]; password=(form.get('password') or [''])[0]; confirm=(form.get('confirm_password') or [''])[0]
            if password!=confirm:
                self.send_response(303); self.send_header('Location','/reset?error=match'); self.send_header('Cache-Control','no-store'); self.end_headers(); return True
            try:
                beta_store().reset_password(code,password,self.client_address[0])
            except BetaError as error:
                label='password' if error.code=='invalid_password' else ('throttled' if error.status==429 else 'code')
                self.send_response(303); self.send_header('Location',f'/reset?error={label}'); self.send_header('Cache-Control','no-store'); self.end_headers(); return True
            self.send_response(303); self.send_header('Location','/login?reset=success'); self.send_header('Cache-Control','no-store'); self.send_beta_cookie('',True); self.end_headers(); return True
    return False


def handle_post(handler, app, path, payload) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    BUILD_VERSION = app.BUILD_VERSION
    apply_owner_template_to_database = app.apply_owner_template_to_database
    beta_mailer = app.beta_mailer
    beta_store = app.beta_store
    if BETA_MODE and path == '/api/beta/login':
        if not self.beta_same_origin(): return True
        row,token=beta_store().login(payload.get('email'),payload.get('password',payload.get('code')),self.client_address[0])
        if not row:
            self.send_json(401,{'error':'sign_in_failed','message':"We couldn't sign you in with those details."}); return True
        body=json.dumps(self.beta_me_payload(row)).encode('utf-8')
        self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_beta_cookie(token); self.end_headers(); self.wfile.write(body); return True
    if BETA_MODE and path == '/api/beta/invites/redeem':
        if not self.beta_same_origin(): return True
        invite=beta_store().validate_invite(payload.get('email'),payload.get('invite_code'))
        if not invite: raise BetaError('That invite is unavailable.','invite_unavailable',400)
        self.send_json(200,{'valid':True,'invite_id':invite['invite_id'],'next_step':'create_password'}); return True
    if BETA_MODE and path == '/api/beta/invites/complete':
        if not self.beta_same_origin(): return True
        row,token=beta_store().complete_invite(payload.get('email'),payload.get('invite_code'),payload.get('password'),self.client_address[0])
        body=json.dumps({'account_created':True,'tester_id':row['user_id'],'next_step':'terms','session_created':True}).encode('utf-8')
        self.send_response(201); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_beta_cookie(token); self.end_headers(); self.wfile.write(body); return True
    if BETA_MODE and path == '/api/beta/password/forgot':
        if not self.beta_same_origin(): return True
        row,code,reset_id=beta_store().request_password_reset(payload.get('identifier'),self.client_address[0])
        if row and code:
            try:
                delivery=beta_mailer().send_reset(row['email'],code,self.beta_base_url(),state_callback=lambda st,attempt,err: beta_store().update_reset_delivery(reset_id,st,attempt,err))
            except BetaError as mail_error:
                delivery={'status':'failed','attempts':0,'safe_message':str(mail_error)}
            beta_store().update_reset_delivery(reset_id,delivery['status'],delivery.get('attempts',0),delivery.get('safe_message',''))
            beta_store().audit('password_reset_email_'+('sent' if delivery['status']=='sent' else 'failed'),'success' if delivery['status']=='sent' else 'failed',row['user_id'],reset_id=reset_id,reason='email_'+delivery['status'])
        self.send_json(202,{'accepted':True,'message':'If an Align account matches those details, password reset instructions have been created.'}); return True
    if BETA_MODE and path == '/api/beta/password/reset':
        if not self.beta_same_origin(): return True
        self.send_json(200,beta_store().reset_password(payload.get('reset_code'),payload.get('password'),self.client_address[0])); return True
    if BETA_MODE and path == '/api/beta/logout':
        row=self.beta_user(); beta_store().logout(row, self.beta_cookie_token())
        body=b'{"ok":true}'; self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_beta_cookie('',True); self.end_headers(); self.wfile.write(body); return True
    if BETA_MODE and path == '/api/beta/accept':
        row=self.require_beta_user(True)
        if not row or not self.beta_same_origin(): return True
        row=beta_store().accept_terms(row); self.send_json(200,self.beta_me_payload(row)); return True
    if BETA_MODE and path == '/api/beta/welcome':
        row=self.require_beta_user()
        if not row or not self.beta_same_origin(): return True
        beta_store().mark_welcome(row); self.send_json(200,{'ok':True}); return True
    if BETA_MODE and path == '/api/beta/feedback':
        row=self.require_beta_user()
        if not row or not self.beta_same_origin(): return True
        beta_store().add_feedback(row,payload.get('type'),payload.get('message'),BUILD_VERSION,payload.get('screen',''))
        self.send_json(201,{'ok':True}); return True

    # Owner invite-email lifecycle. Invite validity and email delivery are
    # intentionally separate: a failed message does not invalidate a code.
    if BETA_MODE and path == '/api/beta/owner/invites/email':
        if not self.require_admin() or not self.beta_same_origin(): return True
        owner=self.beta_user(); idem=self.headers.get('Idempotency-Key','')[:200]
        result,status=beta_store().create_invite(payload.get('tester_email'),payload.get('tester_name'),apply_owner_template_to_database,owner['user_id'],idem)
        if result.get('replayed'):
            self.send_json(status,result); return True
        try:
            delivery=beta_mailer().send_invite(result['user']['email'],result['user'].get('display_name'),result['invite_code'],self.beta_base_url()+'/invite',result['expires_at'],state_callback=lambda st,attempt,err: beta_store().update_invite_delivery(result['invite_id'],st,attempt,err))
        except BetaError as mail_error:
            delivery={'status':'failed','attempts':0,'safe_message':str(mail_error)}
        beta_store().update_invite_delivery(result['invite_id'],delivery['status'],delivery.get('attempts',0),delivery.get('safe_message',''))
        result['delivery']=delivery
        final_status=201 if delivery['status']=='sent' else 207
        beta_store().finalize_idempotency(owner['user_id'],idem,'invite_create',{'email':str(payload.get('tester_email') or '').strip().casefold(),'display_name':str(payload.get('tester_name') or '').strip()},result,final_status,result['invite_id'])
        beta_store().audit('invite_email_'+('sent' if delivery['status']=='sent' else 'failed'),'success' if delivery['status']=='sent' else 'failed',result['user']['user_id'],invite_id=result['invite_id'],reason='email_'+delivery['status'])
        self.send_json(final_status,result); return True
    m=re.fullmatch(r'/api/beta/owner/invites/([^/]+)/replace-and-email',path) if BETA_MODE else None
    if m:
        if not self.require_admin() or not self.beta_same_origin(): return True
        owner=self.beta_user(); idem=self.headers.get('Idempotency-Key','')[:200]
        result,status=beta_store().replace_invite(m.group(1),owner['user_id'],idem)
        if result.get('replayed'):
            self.send_json(status,result); return True
        try:
            delivery=beta_mailer().send_invite(result['email'],result.get('display_name'),result['invite_code'],self.beta_base_url()+'/invite',result['expires_at'],state_callback=lambda st,attempt,err: beta_store().update_invite_delivery(result['invite_id'],st,attempt,err))
        except BetaError as mail_error:
            delivery={'status':'failed','attempts':0,'safe_message':str(mail_error)}
        beta_store().update_invite_delivery(result['invite_id'],delivery['status'],delivery.get('attempts',0),delivery.get('safe_message',''))
        result['delivery']=delivery
        final_status=201 if delivery['status']=='sent' else 207
        beta_store().finalize_idempotency(owner['user_id'],idem,'invite_replace',{'invite_id':m.group(1)},result,final_status,result['invite_id'])
        self.send_json(final_status,result); return True
    m=re.fullmatch(r'/api/beta/owner/invites/([^/]+)/revoke',path) if BETA_MODE else None
    if m:
        if not self.require_admin() or not self.beta_same_origin(): return True
        self.send_json(200,beta_store().revoke_invite(m.group(1),self.beta_user()['user_id'])); return True

    # Outlook OAuth2/SMTP owner settings. Outlook.com requires Modern Auth.
    if BETA_MODE and path == '/api/beta/owner/email-oauth/start':
        if not self.require_admin() or not self.beta_same_origin(): return True
        self.send_json(200,beta_mailer().start_device_connection(self.beta_user()['user_id'])); return True
    if BETA_MODE and path == '/api/beta/owner/email-settings/check':
        if not self.require_admin() or not self.beta_same_origin(): return True
        self.send_json(200,beta_mailer().check_connection()); return True
    if BETA_MODE and path == '/api/beta/owner/email-settings/test':
        if not self.require_admin() or not self.beta_same_origin(): return True
        recipient=str(payload.get('recipient_email','')).strip().casefold()
        if '@' not in recipient: raise BetaError('Enter a valid test recipient email address.')
        delivery=beta_mailer().send_test(recipient)
        if delivery['status']!='sent': raise BetaError(delivery.get('safe_message','Email could not be sent.'),'email_delivery_failed',502)
        self.send_json(200,{'sent':True,'recipient_email':recipient,'sent_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}); return True

    # Compatibility endpoints retained for the existing Owner page/tools.
    if BETA_MODE and path == '/api/beta/admin/users':
        if not self.require_admin() or not self.beta_same_origin(): return True
        owner=self.beta_user(); result,status=beta_store().create_invite(payload.get('email'),payload.get('name',''),apply_owner_template_to_database,owner['user_id'],self.headers.get('Idempotency-Key','')[:200])
        self.send_json(status,result); return True
    if BETA_MODE and re.fullmatch(r'/api/beta/admin/users/[^/]+/(active|invite)',path):
        if not self.require_admin() or not self.beta_same_origin(): return True
        match=re.fullmatch(r'/api/beta/admin/users/([^/]+)/(active|invite)',path); uid,action=match.groups()
        if action=='active': result={'user':beta_store().set_active(uid,bool(payload.get('active',True)))}
        else:
            code=beta_store().reset_invite(uid); result={'access_code':code}
        self.send_json(200,result); return True
    return False


def handle_put(handler, app, path, payload) -> bool:
    self = handler
    BETA_MODE = app.BETA_MODE
    beta_store = app.beta_store
    if BETA_MODE and path == '/api/beta/owner/email-settings':
        if not self.require_admin() or not self.beta_same_origin(): return True
        self.send_json(200,beta_store().save_email_settings(payload)); return True
    if BETA_MODE and path == '/api/beta/owner/login-email':
        if not self.require_admin() or not self.beta_same_origin(): return True
        self.send_json(200,beta_store().change_owner_email(self.beta_user(), payload.get('current_password'), payload.get('new_email'))); return True
    return False


def handle_delete(handler, app, path) -> bool:
    self = handler
    BETA_ICLOUD_LOCK = app.BETA_ICLOUD_LOCK
    BETA_ICLOUD_MANAGERS = app.BETA_ICLOUD_MANAGERS
    BETA_MODE = app.BETA_MODE
    beta_store = app.beta_store
    if BETA_MODE and re.fullmatch(r'/api/beta/admin/users/[^/]+',path):
        if not self.require_admin() or not self.beta_same_origin(): return True
        uid=path.rsplit('/',1)[1]
        with BETA_ICLOUD_LOCK:
            manager=BETA_ICLOUD_MANAGERS.pop(uid,None)
            if manager:
                try: manager.disconnect()
                except Exception: pass
        beta_store().delete_user(uid); self.send_json(200,{'ok':True}); return True
    return False


def apply_pages(handler, app, parsed) -> None:
    self = handler
    BETA_MODE = app.BETA_MODE
    beta_store = app.beta_store
    if BETA_MODE and parsed.path in {'/beta-login','/beta-login.html'}:
        self.path='/beta-login.html'
    elif BETA_MODE and parsed.path in {'/beta-invite','/beta-invite.html'}:
        self.path='/beta-invite.html'
    elif BETA_MODE and parsed.path in {'/beta-forgot','/beta-forgot.html'}:
        self.path='/beta-forgot.html'
    elif BETA_MODE and parsed.path in {'/beta-reset','/beta-reset.html'}:
        self.path='/beta-reset.html'
    elif BETA_MODE and parsed.path in {'/beta-terms','/beta-terms.html'}:
        self.path='/beta-terms.html'
    elif BETA_MODE and parsed.path in {'/beta-welcome','/beta-welcome.html'}:
        self.path='/beta-welcome.html'
    elif BETA_MODE and parsed.path in {'/beta-admin','/beta-admin.html'}:
        if not self.is_admin(): self.path='/beta-login.html'
        else: self.path='/management-studio.html'
    elif BETA_MODE and parsed.path in {'/','/index.html'}:
        row=self.beta_user()
        if not row: self.path='/beta-login.html'
        elif not beta_store().terms_current(row): self.path='/beta-terms.html'
        elif not row['welcome_seen_at']: self.path='/beta-welcome.html'
        else: self.path='/index.html'
    elif BETA_MODE and parsed.path in {'/admin','/admin.html'}:
        self.path='/management-studio.html' if self.is_admin() else '/beta-login.html'
    elif parsed.path == "/admin" or parsed.path == "/admin.html": self.path = "/admin.html"
    elif parsed.path == "/" or parsed.path == "/index.html": self.path = "/index.html"
