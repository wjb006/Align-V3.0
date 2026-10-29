import copy
import gc
import http.client
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

import app
import owner_builder as builder
import appearance_settings
import studio_deploy
from beta_support import BetaStore


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original = app.DATABASE, app.BETA_MODE, app.BETA_STORE
        app.DATABASE = self.root / 'align.sqlite3'
        app.initialise_database_at(app.DATABASE)
        app.BETA_MODE = True
        app.BETA_STORE = BetaStore(self.root, app.DATABASE, app.initialise_database_at)
        owner, code = app.BETA_STORE.ensure_owner('owner@example.com')
        app.BETA_STORE.accept_terms(owner)
        self.owner_token = app.BETA_STORE.login('owner@example.com', code)[1]
        self.users = []
        for n in range(2):
            invite, _ = app.BETA_STORE.create_invite(f'tester{n}@example.com', f'Tester {n}', app.initialise_database_at, owner['user_id'], f'test-{n}')
            user, token = app.BETA_STORE.complete_invite(f'tester{n}@example.com', invite['invite_code'], 'TestPassword2026')
            app.BETA_STORE.accept_terms(user)
            self.users.append((user, token))
        class QuietHandler(app.AlignHandler):
            def log_message(self, *args): pass
        self.server = app.AlignServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        app.DATABASE, app.BETA_MODE, app.BETA_STORE = self.original
        gc.collect()
        self.temp.cleanup()

    def request(self, method, path, body=None, token=None, origin=None, host=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Content-Type': 'application/json', 'Origin': origin or f'http://127.0.0.1:{self.port}'}
        if token: headers['Cookie'] = 'align_beta=' + token
        if host: headers['Host'] = host
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        try: data = json.loads(raw)
        except ValueError: data = raw.decode()
        return response.status, data

    def fixture(self):
        current = builder.config(app.DATABASE)
        doc = copy.deepcopy(current['draft'])
        doc['layouts'].append({'id':'contacts','title':'Contacts','description':'My contacts','view':'table','fields':[
            {'id':'name','type':'text','label':'Name','required':True,'help':'','options':[]},
            {'id':'phone','type':'tel','label':'Phone','required':False,'help':'','options':[]}]})
        doc['menus'].append({'id':'contacts_menu','parent_id':'','title':'Contacts','description':'','destination':'layout','layout_id':'contacts','active':True,'icon':'○','colour':'#365CE6','content':''})
        return current, doc

    def publish(self):
        current, doc = self.fixture()
        status, result = self.request('POST','/api/builder/publish',{'revision':current['revision'],'document':doc},self.owner_token)
        self.assertEqual(status,200,result)
        return result

    def test_publish_history_and_restore(self):
        current, doc = self.fixture()
        doc['appearance']['colors']['accent'] = '#112233'
        status, result = self.request('POST','/api/builder/publish',{'revision':current['revision'],'document':doc},self.owner_token)
        self.assertEqual(status,200,result)
        self.assertEqual(self.request('GET','/api/builder/history',token=self.users[0][1])[0],403)
        status, hist = self.request('GET','/api/builder/history',token=self.owner_token)
        self.assertEqual(status,200)
        self.assertEqual(hist['history'][0]['revision'],result['published_revision'])
        current = builder.config(app.DATABASE)
        doc = copy.deepcopy(current['draft']); doc['appearance']['colors']['accent'] = '#445566'
        self.assertEqual(self.request('POST','/api/builder/publish',{'revision':current['revision'],'document':doc},self.owner_token)[0],200)
        status, restored = self.request('POST','/api/builder/restore',{'index':1},self.owner_token)
        self.assertEqual(status,200,restored)
        self.assertEqual(restored['draft']['appearance']['colors']['accent'],'#112233')
        self.assertEqual(restored['published']['appearance']['colors']['accent'],'#445566')
        self.assertEqual(self.request('POST','/api/builder/restore',{'index':99},self.owner_token)[0],404)
        self.assertEqual(self.request('POST','/api/builder/restore',{'index':'x'},self.owner_token)[0],400)

    def test_owner_only_config_and_page(self):
        for token in (None, self.users[0][1]):
            for method, path in [('GET','/api/builder/config'),('PUT','/api/builder/config'),('POST','/api/builder/publish'),('GET','/owner-builder.html'),('GET','/management-studio.html')]:
                self.assertEqual(self.request(method,path,{},token)[0],403)
        self.assertEqual(self.request('GET','/api/builder/config',token=self.owner_token)[0],200)
        self.assertEqual(self.request('GET','/owner-builder.html',token=self.owner_token)[0],200)

    def test_studio_integrations_status_is_owner_only_and_redacted(self):
        for token in (None, self.users[0][1]):
            self.assertEqual(self.request('GET','/api/studio/status',token=token)[0],403)
        status, body = self.request('GET','/api/studio/status',token=self.owner_token)
        self.assertEqual(status,200,body)
        self.assertTrue(all(isinstance(value, bool) for value in body['integrations'].values()))
        self.assertIn(body['icloud'], ('Configured','Not configured','Status unavailable'))
        self.assertEqual(body['here_quota']['limit'],1000)
        status, page = self.request('GET','/management-studio.html',token=self.owner_token)
        self.assertEqual(status,200)
        self.assertIn('Management Studio', page)
        status, page = self.request('GET','/management-studio',token=self.owner_token)
        self.assertEqual(status,200)
        self.assertIn('Align · Management Studio',page)
        self.assertIn('id="management-phone"',page)
        self.assertIn('id="builder-content"',page)
        self.assertNotIn('id="builder-sidebar"',page)
        self.assertEqual(self.request('PUT','/api/builder/config',{},self.owner_token,'https://untrusted.example')[0],403)

    def test_local_release_endpoint_is_owner_local_and_dispatches_only_after_request(self):
        self.assertEqual(self.request('GET', '/api/studio/deploy-info', token=self.owner_token)[0], 403)
        self.assertEqual(self.request('POST', '/api/studio/deploy', {}, self.owner_token)[0], 403)

        original_mode, original_password = app.BETA_MODE, app.ADMIN_PASSWORD
        app.BETA_MODE = False
        app.ADMIN_PASSWORD = ''
        try:
            with patch.object(studio_deploy, 'availability', return_value={
                'available': True, 'reason': 'GitHub is connected.'
            }), patch.object(studio_deploy, 'dispatch_release', return_value={
                'ok': True, 'ref': 'main', 'target': 'production',
                'workflow_url': studio_deploy.WORKFLOW_URL, 'summary': 'Release checks queued.'
            }) as dispatch:
                status, info = self.request('GET', '/api/studio/deploy-info')
                self.assertEqual(status, 200, info)
                self.assertEqual(info['default_ref'], studio_deploy.DEFAULT_REF)
                self.assertEqual(self.request(
                    'POST', '/api/studio/deploy', {'ref': 'main', 'target': 'production'},
                    origin='https://untrusted.example',
                )[0], 403)
                self.assertEqual(self.request(
                    'POST', '/api/studio/deploy', {'ref': 'main', 'target': 'production'},
                    origin='http://rebind.example', host='rebind.example',
                )[0], 403)
                status, result = self.request(
                    'POST', '/api/studio/deploy', {'ref': 'main', 'target': 'production'},
                )
                self.assertEqual(status, 202, result)
                dispatch.assert_called_once_with('main', 'production')
        finally:
            app.BETA_MODE, app.ADMIN_PASSWORD = original_mode, original_password

    def test_appearance_values_and_permissions_are_validated(self):
        with self.assertRaisesRegex(ValueError, 'valid six-digit hex'):
            appearance_settings.validate_appearance({'colors': {'accent': 'red'}})
        with self.assertRaisesRegex(ValueError, 'event style'):
            appearance_settings.validate_appearance({'events': {'style': 'glow'}})
        with self.assertRaisesRegex(ValueError, 'event style'):
            appearance_settings.validate_appearance({'events': {'style': []}})
        with self.assertRaisesRegex(ValueError, 'enabled or disabled'):
            appearance_settings.validate_permissions({'colors': 'yes'})
        defaults = appearance_settings.validate_appearance({
            'colors': {'accent': '#AABBCC', 'surface': '#FAFAFA'}
        })
        self.assertEqual(defaults['colors']['accent'], '#aabbcc')
        self.assertEqual(defaults['colors']['canvas'], '#061326')
        self.assertEqual(defaults['type']['theme'], 'dark')
        upgraded = appearance_settings.validate_appearance(
            appearance_settings.PREVIOUS_STOCK_APPEARANCE
        )
        self.assertEqual(upgraded['colors']['canvas'], '#061326')
        self.assertEqual(upgraded['type']['theme'], 'dark')
        self.assertEqual(
            appearance_settings.validate_user_overrides(
                {'colors': {'accent': '#abcdef'}},
                {'colors': True},
            ),
            {'colors': {'accent': '#abcdef'}},
        )

    def test_personal_appearance_is_private_permission_limited_and_revocable(self):
        owner_status, _ = self.request('GET', '/api/user-appearance', token=self.owner_token)
        self.assertEqual(owner_status, 200)
        user, token = self.users[0]
        status, result = self.request(
            'PUT', '/api/user-appearance',
            {'appearance': {'colors': {'accent': '#abcdef'}}}, token,
        )
        self.assertEqual(status, 400)
        self.assertIn('not enabled', result['error'])

        current, document = self.fixture()
        document['appearance']['colors'].update(accent='#123456', surface='#eeeeee')
        document['appearance_permissions'] = {
            'colors': True, 'banners': False, 'events': False, 'type': False,
        }
        saved = self.request(
            'POST', '/api/builder/publish',
            {'revision': current['revision'], 'document': document},
            self.owner_token,
        )
        self.assertEqual(saved[0], 200, saved[1])

        status, result = self.request('GET', '/api/user-appearance', token=token)
        self.assertEqual(status, 200, result)
        self.assertEqual(result['appearance']['colors']['accent'], '#123456')
        self.assertEqual(result['appearance']['colors']['surface'], '#eeeeee')
        status, result = self.request(
            'PUT', '/api/user-appearance',
            {'appearance': {'colors': {'accent': '#abcdef'}}}, token,
        )
        self.assertEqual(status, 200, result)
        self.assertEqual(result['appearance']['colors']['accent'], '#abcdef')
        self.assertEqual(result['appearance']['colors']['surface'], '#eeeeee')
        self.assertEqual(
            self.request(
                'PUT', '/api/user-appearance',
                {'appearance': {'events': {'accent': '#111111'}}}, token,
            )[0],
            400,
        )
        self.assertEqual(self.request('PUT', '/api/user-appearance', [], token)[0], 400)
        self.assertEqual(self.request('PUT', '/api/user-appearance', {'reset': 'yes'}, token)[0], 400)

        other_status, other = self.request('GET', '/api/user-appearance', token=self.users[1][1])
        self.assertEqual(other_status, 200, other)
        self.assertEqual(other['appearance']['colors']['accent'], '#123456')
        self.assertEqual(other['personal_appearance'], {})

        document['appearance_permissions']['colors'] = False
        latest = builder.config(app.DATABASE)
        revoked = self.request(
            'POST', '/api/builder/publish',
            {'revision': latest['revision'], 'document': document},
            self.owner_token,
        )
        self.assertEqual(revoked[0], 200, revoked[1])
        status, result = self.request('GET', '/api/user-appearance', token=token)
        self.assertEqual(status, 200, result)
        self.assertEqual(result['appearance']['colors']['accent'], '#123456')
        with builder.connect(app.BETA_STORE.database_for(user)) as c:
            self.assertEqual(
                builder.bootstrap(app.DATABASE, c)['appearance']['colors']['accent'],
                '#123456',
            )

    def test_draft_publish_existing_users_and_conflict(self):
        current, doc = self.fixture()
        status, draft = self.request('PUT','/api/builder/config',{'revision':current['revision'],'document':doc},self.owner_token)
        self.assertEqual(status,200,draft)
        self.assertEqual([layout['id'] for layout in builder.config(app.DATABASE)['published']['layouts']], ['work'])
        self.assertEqual(self.request('PUT','/api/builder/config',{'revision':current['revision'],'document':doc},self.owner_token)[0],409)
        self.assertEqual(self.request('POST','/api/builder/publish',{'revision':draft['revision'],'document':doc},self.owner_token)[0],200)
        for user, token in self.users:
            with builder.connect(app.BETA_STORE.database_for(user)) as c:
                self.assertIn('contacts', [layout['id'] for layout in builder.bootstrap(app.DATABASE,c)['document']['layouts']])

    def test_cycles_and_missing_layout_rejected(self):
        current, doc = self.fixture()
        doc['menus'] = [dict(id='one',parent_id='two',title='One',destination='submenu'),dict(id='two',parent_id='one',title='Two',destination='submenu')]
        with self.assertRaisesRegex(builder.BuilderError,'loop'): builder.validate(doc)
        current, doc = self.fixture()
        doc['menus'][-1]['layout_id']='missing'
        with self.assertRaises(builder.BuilderError): builder.validate(doc)

    def test_database_flowchart_connections_are_preserved_and_cycles_rejected(self):
        _, doc = self.fixture()
        layout = next(item for item in doc['layouts'] if item['id'] == 'contacts')
        layout['database_flow'] = {'edges': [
            {'from': '__flow_start__', 'to': 'name'},
            {'from': 'name', 'to': 'phone'},
            {'from': 'name', 'to': '__flow_finish__'},
            {'from': 'phone', 'to': '__flow_finish__'},
        ]}
        clean = builder.validate(doc)
        saved = next(item for item in clean['layouts'] if item['id'] == 'contacts')
        self.assertEqual(saved['database_flow'], layout['database_flow'])
        layout['database_flow']['edges'].append({'from': 'phone', 'to': 'name'})
        with self.assertRaisesRegex(builder.BuilderError, 'loop'):
            builder.validate(doc)
    def test_private_record_crud_validation_archive_restore(self):
        self.publish()
        token = self.users[0][1]
        path = '/api/builder/records/contacts'
        body = {'id':'record_test','values':{'name':'My contact','phone':'0123456789'}}
        self.assertEqual(self.request('POST',path,body)[0],401)
        self.assertEqual(self.request('POST',path,{'id':'missing_name','values':{}},token)[0],400)
        self.assertEqual(self.request('POST',path,body,token)[0],200)
        self.assertEqual(self.request('POST',path,body,token)[0],200) # retry creates only one record
        self.assertEqual(len(self.request('GET',path,token=token)[1]['records']),1)

    def test_optional_work_database_and_field_associations_are_private(self):
        current = builder.config(app.DATABASE)
        doc = copy.deepcopy(current['draft'])
        work_layout = next(item for item in doc['layouts'] if item['id'] == 'work')
        work_layout.update({'title':'Work','description':'Work details','view':'table','optional':True,
            'work_associations':{'location':'location','area':'area','date':'date','start_time':'start','end_time':'end'},
            'fields':[{'id':'name','type':'text','label':'Name','required':True,'help':'','options':[]},
                      {'id':'location','type':'select','label':'Work Location','required':True,'help':'','options':['Main site']},
                      {'id':'area','type':'text','label':'Shift Area','required':False,'help':'','options':[]},
                      {'id':'date','type':'date','label':'Work date','required':True,'help':'','options':[]},
                      {'id':'start','type':'text','label':'Start time','required':False,'help':'','options':[]},
                      {'id':'end','type':'text','label':'End time','required':False,'help':'','options':[]}]})
        doc['menus'].append({'id':'work_menu','parent_id':'','title':'Work','description':'','destination':'layout','layout_id':'work','active':True,'icon':'◷','colour':'#365CE6','content':''})
        status, result = self.request('POST','/api/builder/publish',{'revision':current['revision'],'document':doc},self.owner_token)
        self.assertEqual(status,200,result)
        token = self.users[0][1]
        definitions = self.request('GET','/api/sections/definitions',token=token)[1]['sections']
        work = next(item for item in definitions if item['key']=='work')
        self.assertTrue(work['optional']); self.assertFalse(work['enabled'])
        self.assertEqual(work['work_associations']['location'],'location')
        self.assertEqual(self.request('GET','/api/builder/records/work',token=token)[0],403)
        self.assertEqual(self.request('POST','/api/builder/records/work/enable',{},token)[0],200)
        enabled = self.request('GET','/api/sections/definitions',token=token)[1]['sections']
        self.assertTrue(next(item for item in enabled if item['key']=='work')['enabled'])
        body={'id':'work_record','values':{'name':'Main shift','location':'Main site','area':'Ward','date':'2026-10-12','start':'08:00','end':'16:00'}}
        self.assertEqual(self.request('POST','/api/builder/records/work',body,token)[0],200)
        self.assertEqual(self.request('GET','/api/builder/records/work',token=self.users[1][1])[0],403)
        self.assertEqual(self.request('GET','/api/builder/records/work',token=token)[1]['records'][0]['values']['location'],'Main site')

    def test_work_database_is_available_by_default_and_optional(self):
        published = builder.published_layouts(app.DATABASE)
        work = next(item for item in published if item['id'] == 'work')
        self.assertTrue(work['optional'])
        self.assertEqual(work['work_associations'], {
            'location':'work_location','area':'shift_area','date':'work_date',
            'start_time':'start_time','end_time':'end_time',
        })
        token = self.users[0][1]
        definitions = self.request('GET','/api/sections/definitions',token=token)[1]['sections']
        self.assertFalse(next(item for item in definitions if item['key']=='work')['enabled'])

    def test_personal_setup_private_and_no_work_required(self):
        token = self.users[0][1]
        self.assertEqual(self.request('PUT','/api/builder/profile',{'values':{'user_name':'','user_phone':'0123'}},token)[0],400)
        self.assertEqual(self.request('PUT','/api/builder/profile',{'values':{'user_name':'Test Person','user_phone':'0123','user_address':'Test address'}},token)[0],200)
        with builder.connect(app.BETA_STORE.database_for(self.users[0][0])) as c:
            self.assertEqual(builder.profile(c)['user_phone'],'0123')
            self.assertTrue(app.get_settings(c)['onboarding_completed'])
        with builder.connect(app.BETA_STORE.database_for(self.users[1][0])) as c:
            self.assertNotEqual(builder.profile(c).get('user_phone'),'0123')

    def test_removed_fields_preserve_values_and_published_types(self):
        current = self.publish()
        token = self.users[0][1]
        path = '/api/builder/records/contacts'
        self.request('POST',path,{'id':'record_keep','values':{'name':'Keep','phone':'123'}},token)
        doc = copy.deepcopy(current['published'])
        contacts = next(layout for layout in doc['layouts'] if layout['id']=='contacts')
        contacts['fields'][0]['type']='number'
        self.assertEqual(self.request('POST','/api/builder/publish',{'revision':current['revision'],'document':doc},self.owner_token)[0],400)
        doc = copy.deepcopy(current['published']);next(layout for layout in doc['layouts'] if layout['id']=='contacts')['fields'].pop()
        self.assertEqual(self.request('POST','/api/builder/publish',{'revision':current['revision'],'document':doc},self.owner_token)[0],200)
        self.request('PUT',path+'/record_keep',{'revision':1,'values':{'name':'Updated'}},token)
        self.assertEqual(self.request('GET',path,token=token)[1]['records'][0]['values']['phone'],'123')


if __name__ == '__main__': unittest.main()
