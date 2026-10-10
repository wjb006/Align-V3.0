import tempfile
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import app
import personal_otp
import personal_planner
import post_event_travel as post
from sqlite_support import connect
import test_personal_otp as otp_tests
import test_owner_builder as builder_tests


class EventChangesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'test.sqlite3'
        app.initialise_database_at(self.path)
        self.c = connect(self.path)
        self.c.row_factory = sqlite3.Row
        self.section = self.c.execute("INSERT INTO organiser_sections(name) VALUES('Tests')").lastrowid
        self.c.execute("INSERT INTO settings(setting_key,setting_value) VALUES('user_address','Home CH41 6AZ') ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value")

    def tearDown(self):
        self.c.close();self.temp.cleanup()

    def event(self,start,end,location='Event L1 1JD',title='Test'):
        return self.c.execute('INSERT INTO organiser_events(section_id,title,start_at,end_at,location) VALUES(?,?,?,?,?)',(self.section,title,start,end,location)).lastrowid

    def test_upcoming_excludes_finished_keeps_current_future_and_history(self):
        now=datetime.now(post.ZONE)
        fmt=lambda dt:dt.isoformat(timespec='seconds')
        past=self.event(fmt(now-timedelta(hours=2)),fmt(now-timedelta(minutes=1)))
        current=self.event(fmt(now-timedelta(minutes=20)),fmt(now+timedelta(minutes=20)))
        future=self.event(fmt(now+timedelta(hours=2)),fmt(now+timedelta(hours=3)))
        ids=[e['id'] for e in app.dashboard(self.c)['upcoming_events']]
        self.assertNotIn(past,ids);self.assertIn(current,ids);self.assertIn(future,ids)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM organiser_events').fetchone()[0],3)
        self.assertEqual(post.event_end(dict(work_date='2030-10-01',start_time='22:00',end_time='06:00')).day,2)

    def test_import_creates_one_category_and_preserves_locations(self):
        ics='BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:example\nDTSTART:20301001T090000\nDTEND:20301001T100000\nSUMMARY:Example\nLOCATION:Test L1 1JD\nEND:VEVENT\nEND:VCALENDAR'
        source,count=app.import_ics_calendar(self.c,'My calendar',ics)
        self.assertEqual(count,1)
        section=self.c.execute('SELECT section_id FROM calendar_sources WHERE id=?',(source,)).fetchone()[0]
        self.assertEqual(app.organiser_section(self.c,section)['events'][0]['location'],'Test L1 1JD')
        app.ensure_import_categories(self.c)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM organiser_sections WHERE calendar_name='My calendar'").fetchone()[0],1)

    def test_next_location_within_hour_else_home_and_invalidation(self):
        ident=self.event('2030-10-01T09:00','2030-10-01T10:00')
        self.event('2030-10-01T10:10','2030-10-01T10:15',location='')
        following=self.event('2030-10-01T11:00','2030-10-01T12:00',location='Next CH41 6AZ',title='Next')
        self.assertEqual(post.target(self.c,'event',ident)[1]['destination_name'],'Next')
        journey={'leave_at':'2030-10-01T10:00','arrival_at':'2030-10-01T10:30','notes':'Test journey'}
        with patch.object(post,'plan',return_value=journey):
            result=post.handle(self.c,dict(kind='event',id=ident,enabled=True,mode='bus',plan=True))
        self.assertTrue(result['enabled']);self.assertEqual(result['journey'],journey)
        self.c.execute("UPDATE organiser_events SET start_at='2030-10-01T11:01' WHERE id=?",(following,))
        result=post.handle(self.c,dict(kind='event',id=ident))
        self.assertEqual(result['destination_name'],'Home');self.assertIsNone(result['journey'])
        with patch.object(post,'plan',side_effect=ValueError('Provider unavailable')):
            result=post.handle(self.c,dict(kind='event',id=ident,plan=True))
        self.assertTrue(result['enabled']);self.assertEqual(result['error'],'Provider unavailable')
        self.assertFalse(post.handle(self.c,dict(kind='event',id=ident,enabled=False))['enabled'])

    def test_depart_after_uses_event_origin_and_excludes_early_route(self):
        body=dict(mode='transit',arrival='2030-07-02T10:55',departure='2030-07-02T10:55',origin='Event CH41 6AZ',destination='Home L1 1JD',departure_buffer=0,arrival_buffer=0)
        with patch.object(personal_otp,'resolve_place',return_value=((53.,-3.),'postcode')) as resolve,patch.object(personal_otp.OTPProvider,'plan',return_value=otp_tests.PersonalOTPTests().routes()) as provider:
            result=personal_otp.plan(otp_tests.Connection(),body,personal_planner.DEFAULTS)
            self.assertEqual(resolve.call_args_list[0].args[0],'Event CH41 6AZ')
            self.assertTrue(provider.call_args.kwargs['depart_after'])
            self.assertGreaterEqual(post.instant(result['leave_at']),post.instant(body['departure']))
            body['departure']='2030-07-02T11:01'
            with self.assertRaises(ValueError):personal_otp.plan(otp_tests.Connection(),body,personal_planner.DEFAULTS)


class PostTravelAPITests(unittest.TestCase):
    setUp=builder_tests.BuilderTests.setUp
    tearDown=builder_tests.BuilderTests.tearDown
    request=builder_tests.BuilderTests.request
    def test_option_is_private_and_survives_event_save(self):
        token=self.users[0][1]
        status,section=self.request('POST','/api/sections',{'name':'Appointments'},token)
        self.assertEqual(status,201,section)
        body=dict(title='Test event',start_at='2030-10-01T09:00',end_at='2030-10-01T10:00',location='Example L1 1JD',show_post_travel=True,post_travel_mode='bus')
        status,event=self.request('POST',f"/api/sections/{section['id']}/events",body,token)
        self.assertEqual(status,201,event)
        path='/api/personal/post-event-travel'
        status,result=self.request('POST',path,dict(kind='event',id=event['id']),token)
        self.assertEqual(status,200,result);self.assertTrue(result['enabled']);self.assertEqual(result['mode'],'bus')
        self.assertEqual(self.request('POST',path,dict(kind='event',id=event['id']),self.users[1][1])[0],400)
        self.assertEqual(self.request('POST',path,dict(kind='event',id=event['id']))[0],401)
        body['show_post_travel']=False
        self.assertEqual(self.request('PUT',f"/api/organiser-events/{event['id']}",body,token)[0],200)
        self.assertFalse(self.request('POST',path,dict(kind='event',id=event['id']),token)[1]['enabled'])


if __name__=='__main__':unittest.main()
