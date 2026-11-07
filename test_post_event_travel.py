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

    def test_event_lookup_and_travel_work_without_legacy_schedule_tables(self):
        # A fresh V3 schema deliberately has no shifts or locations tables.
        self.event('2030-10-01T09:00', '2030-10-01T10:00')
        items = post.events(self.c)
        self.assertTrue(any(item['kind'] == 'event' for item in items))
        with self.assertRaisesRegex(ValueError, 'Event no longer exists'):
            post.handle(self.c, {'kind': 'shift', 'id': 1})

    def test_shift_post_travel_uses_next_calendar_item_or_home(self):
        self.c.execute("CREATE TABLE locations(id INTEGER PRIMARY KEY,address TEXT)")
        self.c.execute("CREATE TABLE shifts(id INTEGER PRIMARY KEY,work_date TEXT,start_time TEXT,end_time TEXT,location_id INTEGER,location_name TEXT,shift_type_name TEXT)")
        self.c.execute("INSERT INTO locations(id,address) VALUES(1,'Arrowe Park Road, Wirral')")
        self.c.execute("INSERT INTO shifts VALUES(1,'2030-10-01','08:30','12:30',1,'Arrowe Park','Clinic')")
        self.event('2030-10-01T13:00','2030-10-01T14:00',location='Clatterbridge Road, Wirral',title='PM Clinic')
        item=next(row for row in post.events(self.c) if row['kind']=='shift')
        self.assertEqual(item['location'],'Arrowe Park Road, Wirral')
        event,route=post.target(self.c,'shift',1)
        self.assertEqual(route['destination'],'Clatterbridge Road, Wirral')
        self.assertEqual(route['destination_name'],'PM Clinic')
        result=post.handle(self.c,{'kind':'shift','id':1,'enabled':True,'mode':'bus'})
        self.assertTrue(result['enabled'])
        decorated=post.decorate(self.c,[{'id':1,'work_date':'2030-10-01','start_time':'08:30','end_time':'12:30'}],kind='shift')
        self.assertTrue(decorated[0]['post_travel']['enabled'])

    def test_post_shift_travel_skips_following_shift_at_same_location(self):
        self.c.execute("CREATE TABLE locations(id INTEGER PRIMARY KEY,address TEXT)")
        self.c.execute("""CREATE TABLE shifts(id INTEGER PRIMARY KEY,work_date TEXT,start_time TEXT,end_time TEXT,location_id INTEGER,location_name TEXT,shift_type_name TEXT)""")
        self.c.execute("INSERT INTO locations(id,address) VALUES(1,'Arrowe Park Road, Wirral')")
        self.c.execute("INSERT INTO shifts VALUES(1,'2030-10-01','08:00','12:00',1,'Arrowe Park','Wards')")
        self.c.execute("INSERT INTO shifts VALUES(2,'2030-10-01','12:30','16:30',1,'Arrowe Park','Clinic')")
        self.event('2030-10-01T17:15','2030-10-01T18:00',location='Arrowe Park Medical Centre, Wirral',title='GP Appointment')
        _, route=post.target(self.c,'shift',1)
        self.assertEqual(route['destination'],'Arrowe Park Medical Centre, Wirral')
        self.assertEqual(route['destination_name'],'GP Appointment')

    def test_dashboard_includes_first_class_shifts_and_post_shift_travel(self):
        self.c.execute("CREATE TABLE locations(id INTEGER PRIMARY KEY,address TEXT)")
        self.c.execute("""CREATE TABLE shifts(
            id INTEGER PRIMARY KEY,work_date TEXT,start_time TEXT,end_time TEXT,
            location_id INTEGER,location_name TEXT,shift_type_name TEXT,
            notes TEXT,hours REAL,colour TEXT
        )""")
        self.c.execute("INSERT INTO locations(id,address) VALUES(1,'Arrowe Park Road, Wirral')")
        self.c.execute("INSERT INTO shifts VALUES(1,'2030-10-01','08:30','12:30',1,'Arrowe Park','Clinic','',4,'#365CE6')")
        post.handle(self.c, {'kind':'shift','id':1,'enabled':True,'mode':'bus'})
        dashboard = app.dashboard(self.c)
        shift = next(item for item in dashboard['upcoming_events'] if item.get('origin') == 'Shift')
        self.assertEqual(shift['title'], 'Arrowe Park · Clinic')
        self.assertEqual(shift['location'], 'Arrowe Park Road, Wirral')
        self.assertEqual(shift['start_at'], '2030-10-01T08:30')
        self.assertTrue(shift['post_travel']['enabled'])

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
