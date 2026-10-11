"""Simulated CalDAV tests: never contacts Apple or uses real credentials."""
import copy
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from datetime import datetime, timezone
from icalendar import Event
import app
from icloud_sync import ICloudSync, CloudError, digest, busy_event, apple_url, AppleClient
from test_support import IsolatedAppServer

class FakeApple:
    def __init__(self, username, password):
        self.calendars = {'https://caldav.icloud.com/test/calendar/':None}
        self.objects = {}; self.calls = []; self.rev = 0; self.read_events = []
        self.fail_after_put = False
    def discover(self): return [{'id':digest(url),'name':'Test Calendar'} for url in self.calendars]
    def close(self): pass
    def events(self,*args): return copy.deepcopy(self.read_events)
    def get(self,url): return self.objects.get(url)
    def put(self,url,payload,etag=None):
        current = self.objects.get(url)
        if (current and current[1]!=etag) or (not current and etag): raise CloudError('ETag conflict')
        self.rev+=1; tag='"'+str(self.rev)+'"'; self.objects[url]=(payload,tag)
        self.calls.append(('PUT',url))
        if self.fail_after_put: self.fail_after_put=False; raise OSError('Lost response')
        return tag
    def delete(self,url,etag):
        if self.objects[url][1]!=etag: raise CloudError('ETag conflict')
        del self.objects[url]; self.calls.append(('DELETE',url))

class ICloudTests(unittest.TestCase):
    setUpBase=IsolatedAppServer.setUp
    tearDown=IsolatedAppServer.tearDown
    request=IsolatedAppServer.request
    json_request=IsolatedAppServer.json_request
    def setUp(self):
        self.setUpBase()
        self.syncer=ICloudSync(app,FakeApple)
        self.syncer.discover('test@example.invalid','fake-test-password')
        self.fake=self.syncer.client
        self.url=next(iter(self.fake.calendars))
        with app.db_connection() as c:
            c.execute('UPDATE icloud_config SET account_hash=?,target_url=?,read_urls=? WHERE id=1',(self.syncer.account,self.url,'["'+self.url+'"]'))
            self.section_id=c.execute("INSERT INTO organiser_sections(name) VALUES('Personal')").lastrowid
            c.execute("INSERT INTO calendar_links(target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled) VALUES('organiser_section',?,?, 'Personal',1,1)",(str(self.section_id),self.url))
        self.syncer.enabled=True
    def add_event(self, notes='Original Align note'):
        result=self.json_request('POST',f'/api/sections/{self.section_id}/events',{
            'title':'Personal appointment','start_at':'2026-11-07T09:00','end_at':'2026-11-07T10:00',
            'location':'Town Centre','notes':notes,
        })
        return result['id']
    def update_event(self, event_id, **changes):
        value={'title':'Personal appointment','start_at':'2026-11-07T09:00','end_at':'2026-11-07T10:00',
               'location':'Town Centre','notes':'Original Align note',**changes}
        self.json_request('PUT',f'/api/organiser-events/{event_id}',value)
    def test_create_retry_update_delete_only_owned_events(self):
        event_id=self.add_event()
        unrelated=self.url+'unrelated.ics'; self.fake.objects[unrelated]=(b'not ours','"1"')
        self.fake.fail_after_put=True; self.syncer.sync()
        self.assertEqual(len(self.fake.calls),1)
        self.syncer.sync(); self.assertEqual(len(self.fake.calls),1)
        self.update_event(event_id,notes='Changed in Align')
        self.syncer.sync(); self.assertEqual(len(self.fake.calls),2)
        self.json_request('DELETE',f'/api/organiser-events/{event_id}')
        self.syncer.sync(); self.assertEqual(self.fake.calls[-1][0],'DELETE')
        self.assertEqual(list(self.fake.objects),[unrelated])
    def test_event_journey_syncs_travel_block_and_cleans_up(self):
        notes='[Align travel]\nLeave home: 07 Nov 08:10\nBus from home · approximately 35 minutes travelling\n[/Align travel]'
        event_id=self.add_event(notes=notes)
        self.syncer.sync()
        bodies=[raw for raw,_ in self.fake.objects.values()]
        self.assertEqual(len(bodies),2)
        shift=next(x for x in bodies if b'Travel to' not in x); block=next(x for x in bodies if b'Travel to' in x)
        self.assertIn(b'X-APPLE-TRAVEL-DURATION;VALUE=DURATION:PT35M',shift)
        self.assertIn(b'TRIGGER:-PT50M',shift)
        self.assertIn(b'Leave at 08:10 for "', shift)
        self.assertIn(b'- Leave: 08:10', shift)
        self.assertIn(b'TRANSP:TRANSPARENT',block)
        self.assertIn(b'BEGIN:VALARM', block)
        self.assertIn(b'Leave at 08:10 for "', block)
        before=len(self.fake.calls); self.syncer.sync(); self.assertEqual(len(self.fake.calls),before)
        self.update_event(event_id,notes='No journey')
        self.syncer.sync()
        self.assertEqual(len(self.fake.objects),1)
        self.assertNotIn(b'X-APPLE-TRAVEL-DURATION',next(iter(self.fake.objects.values()))[0])
    def test_icloud_edit_pulls_back_into_align_two_way(self):
        event_id=self.add_event(); self.syncer.sync()
        url=next(iter(self.fake.objects)); raw,_=self.fake.objects[url]
        edited = raw.replace(b'DESCRIPTION:', b'DESCRIPTION:Edited in iCloud\\n')
        self.fake.objects[url]=(edited,'"external"')
        self.syncer.sync()
        self.assertEqual(len(self.syncer.conflicts),0)
        self.assertIsNone(self.syncer.last_error)
        self.assertIn('Two-way sync', self.syncer.message)
        with app.db_connection() as c:
            notes = c.execute('SELECT notes FROM organiser_events WHERE id=?', (event_id,)).fetchone()[0]
        self.assertIn('Edited in iCloud', notes)
        # Concurrent Align + iCloud edits still conflict; other Section events keep syncing.
        with app.db_connection() as c:
            c.execute("UPDATE organiser_events SET notes=? WHERE id=?", ('Changed in Align', event_id))
        cloud_again = edited.replace(b'Edited in iCloud', b'Edited again in iCloud')
        self.fake.objects[url]=(cloud_again,'"external2"')
        before=copy.deepcopy(self.fake.objects)
        self.syncer.sync()
        self.assertEqual(len(self.syncer.conflicts),1,self.syncer.message+' '+repr(self.syncer.conflicts))
        self.assertIn('both Align and iCloud', self.syncer.conflicts[0]['message'])
        self.assertIn('need review', self.syncer.message)
        self.assertIn('continued syncing both ways', self.syncer.message)
        self.assertEqual(self.fake.objects[url], before[url])
        other_id = self.add_event(notes='Second appointment')
        self.syncer.sync()
        self.assertIn(f'event-{other_id}', ''.join(url for method,url in self.fake.calls if method == 'PUT'))
        self.assertEqual(self.fake.objects[url], before[url])
        self.json_request('DELETE',f'/api/organiser-events/{event_id}')
        preserved = copy.deepcopy(self.fake.objects)
        self.syncer.sync()
        # Conflicted cloud copy must not be deleted; the other synced event stays.
        self.assertEqual(self.fake.objects, preserved)
        self.assertEqual(self.fake.objects[url], before[url])
        self.assertTrue(any(f'event-{other_id}' in object_url for object_url in self.fake.objects))
    def test_read_clashes_and_disconnect_do_not_touch_remote(self):
        e=Event(); e.add('uid','external'); e.add('dtstart',datetime(2026,9,7,6,30,tzinfo=timezone.utc)); e.add('dtend',datetime(2026,9,7,10,30,tzinfo=timezone.utc)); e.add('summary','Busy')
        self.fake.read_events=[e]; self.syncer.sync()
        with app.db_connection() as c:
            self.assertEqual(app.imported_conflict(c,'2026-09-07','07:30','11:30'),'Busy')
        self.assertEqual(self.fake.calls,[])
        self.syncer.disconnect(); self.assertIsNone(self.syncer.client)
        with app.db_connection() as c: self.assertEqual(c.execute("SELECT COUNT(*) FROM calendar_sources WHERE source_kind='icloud'").fetchone()[0],0)
    def test_status_reports_attempt_errors_calendar_and_recovery(self):
        self.fake.events = Mock(side_effect=CloudError('Calendar is temporarily unavailable.'))
        self.syncer.sync()
        failed = self.syncer.status(True)
        self.assertIsNotNone(failed['last_attempt'])
        self.assertEqual(failed['last_error'], 'Calendar is temporarily unavailable.')
        self.assertEqual(failed['retry_in_seconds'], 60)
        self.assertEqual(failed['calendars'][0]['status'], 'error')
        self.assertEqual(failed['calendars'][0]['error'], failed['last_error'])

        self.fake.events = lambda *args: []
        self.syncer.sync()
        recovered = self.syncer.status(True)
        self.assertIsNone(recovered['last_error'])
        self.assertIsNone(recovered['retry_in_seconds'])
        self.assertEqual(recovered['calendars'][0]['status'], 'ok')
        self.assertEqual(recovered['calendars'][0]['event_count'], 0)
    def test_uid_filter_transparency_and_url_guard(self):
        e=Event();e.add('uid','owned-123');e.add('dtstart',datetime(2026,9,7,8,tzinfo=timezone.utc));e.add('dtend',datetime(2026,9,7,9,tzinfo=timezone.utc))
        self.assertIsNone(busy_event(e,'owned-'))
        e['UID']='other';e.add('transp','TRANSPARENT');self.assertIsNone(busy_event(e,'owned-'))
        for url in ['http://caldav.icloud.com/','https://icloud.com.evil.test/','https://user:password@icloud.com/','https://127.0.0.1/']:
            with self.assertRaises(CloudError): apple_url(url)
    def test_private_routes_reject_remote_origin(self):
        status,_,_=self.request('POST','/api/icloud/connect',{'username':'test@example.invalid','password':'fake'},headers={'Origin':'https://evil.invalid'})
        self.assertEqual(status,403)
        self.assertEqual(self.request('GET','/api/icloud/manage',headers={'Host':'192.168.0.28:8001'})[0],403)
    def test_redirects_never_forward_credentials_outside_apple(self):
        session=SimpleNamespace(request=Mock(side_effect=[SimpleNamespace(status_code=302,headers={'Location':'https://evil.invalid/'})]))
        dav=SimpleNamespace(session=session)
        with patch('caldav.DAVClient',return_value=dav):
            client=AppleClient('test@example.invalid','fake')
        with self.assertRaises(CloudError):
            client.client.session.request('GET','https://caldav.icloud.com/')
        # Only the original Apple host was contacted by the simulated transport.
        session2=SimpleNamespace(request=Mock(side_effect=[SimpleNamespace(status_code=307,headers={'Location':'https://p01-caldav.icloud.com/test/'}),SimpleNamespace(status_code=200,headers={})]))
        transport=session2.request
        with patch('caldav.DAVClient',return_value=SimpleNamespace(session=session2)):
            client=AppleClient('test@example.invalid','fake')
        self.assertEqual(client.client.session.request('GET','https://caldav.icloud.com/').status_code,200)
        self.assertEqual(transport.call_count,2)
        self.assertTrue(all(call.kwargs['allow_redirects'] is False for call in transport.call_args_list))

if __name__=='__main__': unittest.main()
