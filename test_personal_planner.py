import unittest
from unittest.mock import patch, Mock
from datetime import date,timedelta
import app
import personal_planner as p
from test_owner_builder import BuilderTests
from icloud_sync import ICloudSync, CloudError

class PersonalTests(unittest.TestCase):
    setUp=BuilderTests.setUp
    tearDown=BuilderTests.tearDown
    request=BuilderTests.request

    def test_private_capture_due_and_preferences(self):
        token=self.users[0][1]; other=self.users[1][1]
        body=dict(id='private-reminder-123',kind='reminder',title='Call tomorrow',due_at='2030-01-02T12:00')
        self.assertEqual(self.request('POST','/api/personal/items',body)[0],401)
        self.assertEqual(self.request('POST','/api/personal/items',body,token,origin='https://wrong.invalid')[0],403)
        self.assertEqual(self.request('POST','/api/personal/items',body,token)[0],200)
        self.assertEqual(self.request('POST','/api/personal/items',body,token)[0],200)
        data=self.request('GET','/api/bootstrap',token=token)[1]['personal']
        self.assertEqual(len(data['items']),1)
        for t in (other,self.owner_token):
            self.assertEqual(self.request('GET','/api/bootstrap',token=t)[1]['personal']['items'],[])
        self.request('PUT','/api/personal/items/private-reminder-123',{'done':True},other)
        self.assertEqual(self.request('GET','/api/bootstrap',token=token)[1]['personal']['items'][0]['done'],0)
        self.assertEqual(self.request('PUT','/api/personal/preferences',{'travel_modes':['bus'],'default_travel':'drive'},token)[0],400)
        self.assertEqual(self.request('PUT','/api/personal/preferences',{'travel_modes':['bus'],'default_travel':'bus','show_todos':False},token)[0],200)
        self.assertTrue(self.request('GET','/api/bootstrap',token=other)[1]['personal']['preferences']['show_todos'])

    def test_selected_icloud_calendar_adds_events_and_reminders_to_its_section(self):
        user, token = self.users[0]
        calendar_id = 'a' * 64
        database = app.BETA_STORE.database_for(user)
        with app.FixedDatabaseApp(database).db_connection() as c:
            c.execute("""INSERT INTO calendar_links
                (target_kind,target_key,calendar_url,calendar_name,import_enabled,export_enabled)
                VALUES('icloud_calendar',?,?,?,1,1)""",
                (calendar_id, 'https://caldav.icloud.com/test/appointments/', 'Appointments'))
        reminder = dict(id='calendar-reminder-123',kind='reminder',title='Dentist',
                        due_at='2030-01-02T12:00',calendar_id=calendar_id)
        status, _ = self.request('POST','/api/personal/items',reminder,token)
        self.assertEqual(status,200)
        with app.FixedDatabaseApp(database).db_connection() as c:
            item=c.execute('SELECT calendar_id,calendar_event_id FROM personal_items WHERE id=?',(reminder['id'],)).fetchone()
            event=c.execute('SELECT section_id,title,start_at FROM organiser_events WHERE id=?',(item['calendar_event_id'],)).fetchone()
            self.assertEqual(item['calendar_id'],calendar_id)
            self.assertEqual(event['title'],'Dentist')
            section_id=event['section_id']
        status, response = self.request('POST',f'/api/sections/{section_id}/events',
            {'title':'Eye test','start_at':'2030-01-03T09:00','end_at':'2030-01-03T09:30','calendar_id':calendar_id},token)
        self.assertEqual(status,201,response)
        self.assertEqual(response['section_id'],section_id)
        with app.FixedDatabaseApp(database).db_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM organiser_events WHERE section_id=?',(section_id,)).fetchone()[0],2)
        status, _ = self.request('DELETE','/api/personal/items/'+reminder['id'],{},token)
        self.assertEqual(status,200)
        with app.FixedDatabaseApp(database).db_connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM organiser_events WHERE title=?',('Dentist',)).fetchone()[0],0)

    def test_overnight_and_buffer(self):
        day=date.today()+timedelta(days=15)
        with app.db_connection() as c:
            section=c.execute("INSERT INTO organiser_sections(name) VALUES('Personal')").lastrowid
            c.execute("INSERT INTO organiser_events(section_id,title,start_at,end_at,location) VALUES(?,?,?,?,?)",(section,'Night work',(day-timedelta(days=1)).isoformat()+'T22:00',day.isoformat()+'T09:00','Home'))
            source=c.execute("INSERT INTO calendar_sources(name,source_kind) VALUES('Personal','ics')").lastrowid
            c.execute('INSERT INTO calendar_events(source_id,event_uid,start_at,end_at,title) VALUES(?,?,?,?,?)',(source,'test-event',day.isoformat()+'T12:00',day.isoformat()+'T13:00','Lunch'))
            r=p.availability(c,dict(date=day.isoformat(),start='08:00',end='15:00',duration=60,buffer=30))
            slots=[s['start_at'][11:] for s in r['slots']]
            self.assertNotIn('09:00',slots); self.assertIn('09:30',slots)
            self.assertNotIn('11:00',slots); self.assertIn('13:30',slots)

    def test_calendar_creation_retries_reuse_name(self):
        manager=ICloudSync(app)
        fake=Mock(); fake.discover.side_effect=[[],[{'id':'new-id','name':'Appointments'}]]
        fake.create_calendar.return_value={'id':'new-id','name':'Appointments'}
        manager.client=fake
        self.assertEqual(manager.create_calendar('Appointments')['created_calendar']['id'],'new-id')
        manager.create_calendar('Appointments')
        fake.create_calendar.assert_called_once_with('Appointments')
        with self.assertRaises(CloudError):manager.create_calendar('')

    def test_calendar_events_block_availability_and_all_day_is_busy(self):
        day=date.today()+timedelta(days=15)
        with app.db_connection() as c:
            query=dict(date=day.isoformat(),start='08:00',end='19:00',duration=60)
            self.assertTrue(any(s['start_at'].endswith('08:00') for s in p.availability(c,query)['periods']))
            sid=c.execute("INSERT INTO organiser_sections(name) VALUES('Personal')").lastrowid
            c.execute('INSERT INTO organiser_events(section_id,title,start_at,end_at,all_day) VALUES(?,?,?,?,1)',(sid,'All day',day.isoformat()+'T00:00',(day+timedelta(days=1)).isoformat()+'T00:00'))
            self.assertEqual(p.availability(c,query)['periods'],[])

    def test_weather_location_and_no_home_address_sent(self):
        with app.db_connection() as c:
            p.save_preferences(c,{'weather_town':'London'})
            with patch.object(p,'fetch_json',side_effect=[{'results':[{'name':'London','latitude':51.5,'longitude':-.1}]},{'current':{'temperature_2m':20},'hourly':{'time':['2030-01-01T12:00'],'temperature_2m':[20],'weather_code':[1],'precipitation_probability':[10]},'daily':{'time':['2030-01-01'],'temperature_2m_min':[15],'temperature_2m_max':[22],'precipitation_probability_max':[20]}}]) as fetch:
                result=p.weather(c)
                self.assertEqual(result['place'],'London')
                self.assertIn('name=London',fetch.call_args_list[0].args[0])
                self.assertNotIn('address',fetch.call_args_list[1].args[0])
                self.assertIn('wind_speed_10m', fetch.call_args_list[1].args[0])
                self.assertIn('weather_code', fetch.call_args_list[1].args[0])
                self.assertEqual(len(result['hourly']['time']), 1)
                self.assertEqual(result['daily']['temperature_2m_max'], [22])

    def test_bus_notes_and_unavailable_provider(self):
        with app.db_connection() as c:
            c.execute("UPDATE settings SET setting_value='Test home address' WHERE setting_key='user_address'")
            body=dict(destination='Test destination',mode='bus',arrival='2030-01-02T12:00',arrival_buffer=0)
            with patch.dict(p.os.environ,{},clear=True):
                with self.assertRaisesRegex(ValueError,'API key'):p.google_journey(c,body)
            response={'routes':[{'duration':'1800s','legs':[{'steps':[{'transitDetails':{'transitLine':{'nameShort':'42'},'headsign':'Town','stopDetails':{'departureStop':{'name':'Home stop'},'departureTime':'2030-01-02T11:35:00Z','arrivalStop':{'name':'Town stop'},'arrivalTime':'2030-01-02T11:55:00Z'}}}]}]}]}
            with patch.dict(p.os.environ,{'ALIGN_GOOGLE_ROUTES_KEY':'fake'}),patch.object(p,'fetch_json',return_value=response) as fetch:
                r=p.google_journey(c,body)
                self.assertIn('Bus 42',r['notes']);self.assertIn('11:35',r['notes'])
                self.assertEqual(fetch.call_args.args[1]['transitPreferences']['allowedTravelModes'],['BUS'])
                self.assertEqual(r['minutes'],30)

    def test_leave_home_includes_walk_and_boarding_buffer(self):
        from datetime import datetime
        route={'duration':'2700s','legs':[{'steps':[
            {'travelMode':'WALK','staticDuration':'600s'},
            {'transitDetails':{'transitLine':{'nameShort':'42','vehicle':{'name':{'text':'Bus'}}},'stopDetails':{'departureTime':'2030-01-02T11:10:00Z','departureStop':{'name':'Nearby stop'},'arrivalTime':'2030-01-02T11:30:00Z','arrivalStop':{'name':'Town station'}}}},
            {'travelMode':'WALK','staticDuration':'300s'}]}]}
        plan=p.route_plan(route,'transit',datetime(2030,1,2,12,tzinfo=p.ZONE),5,10)
        self.assertEqual(plan['leave_at'],'2030-01-02T10:55+00:00')
        self.assertEqual(plan['arrival_at'],'2030-01-02T11:35+00:00')
        self.assertEqual(plan['walk_to_first_stop_minutes'],10)
        self.assertIn('Bus 42',plan['notes']);self.assertIn('Nearby stop 11:10',plan['notes'])
        self.assertIsNone(p.route_plan(route,'transit',datetime(2030,1,2,11,30,tzinfo=p.ZONE),5,0))

    def test_train_and_mixed_transit_requests(self):
        with app.db_connection() as c:
            c.execute("UPDATE settings SET setting_value='Test home' WHERE setting_key='user_address'")
            response={'routes':[{'duration':'1800s','legs':[]}]}
            for mode,allowed in [('train',['TRAIN']),('transit',['BUS','RAIL'])]:
                with patch.dict(p.os.environ,{'ALIGN_GOOGLE_ROUTES_KEY':'fake'}),patch.object(p,'fetch_json',return_value=response) as fetch:
                    result=p.google_journey(c,dict(destination='Test place',arrival='2030-01-02T12:00',mode=mode,arrival_buffer=10))
                    sent=fetch.call_args.args[1]
                    self.assertEqual(sent['transitPreferences']['allowedTravelModes'],allowed)
                    self.assertEqual(sent['arrivalTime'],'2030-01-02T11:50:00Z')
                    self.assertTrue(sent['computeAlternativeRoutes'])
                    self.assertEqual(len(result['journeys']),1)

    def test_weather_adjustment_shifts_leave_time_and_falls_back(self):
        with app.db_connection() as c:
            result = {'leave_at': '2030-01-02T10:00+00:00', 'notes': 'fixed', 'journeys': [
                {'leave_at': '2030-01-02T10:00+00:00'}]}
            forecast = {'checked_at': '2030-01-02T09:00:00+00:00',
                        'hourly': {'time': ['2030-01-02T12:00'], 'precipitation_probability': [90], 'weather_code': [63]},
                        'current': {}, 'daily': {}}
            with patch.object(p, 'weather', return_value=forecast):
                adjusted = p.apply_weather_adjustment(c, {'arrival': '2030-01-02T12:00'}, result)
            self.assertEqual(adjusted['weather_adjustment']['extra_minutes'], 10)
            self.assertEqual(adjusted['leave_at'], '2030-01-02T09:50+00:00')
            self.assertEqual(adjusted['journeys'][0]['leave_at'], '2030-01-02T09:50+00:00')
            with patch.object(p, 'weather', side_effect=ValueError('unavailable')):
                fallback = p.apply_weather_adjustment(c, {'arrival': '2030-01-02T12:00'}, result)
            self.assertEqual(fallback['weather_adjustment']['status'], 'unavailable')
            self.assertEqual(fallback['leave_at'], result['leave_at'])

    def test_here_drive_uses_traffic_and_weather_without_exposing_key(self):
        with app.db_connection() as c:
            c.execute("UPDATE settings SET setting_value='Test home address' WHERE setting_key='user_address'")
            p.save_preferences(c, {'weather_town': 'Liverpool'})
            responses = [
                {'items': [{'position': {'lat': 53.4, 'lng': -3.0}, 'scoring': {'queryScore': 1}, 'resultType': 'houseNumber'}]},
                {'items': [{'position': {'lat': 53.5, 'lng': -3.1}, 'scoring': {'queryScore': 1}, 'resultType': 'houseNumber'}]},
                {'routes': [{'sections': [{'summary': {'duration': 3600, 'baseDuration': 3000}}]}]},
                {'results': [{'name': 'Liverpool', 'latitude': 53.4, 'longitude': -3.0}]},
                {'current': {}, 'hourly': {'time': ['2030-01-02T12:00'], 'precipitation_probability': [90], 'weather_code': [63]}, 'daily': {}, 'checked_at': '2030-01-02T09:00:00+00:00'},
            ]
            body = {'destination': 'Test destination', 'mode': 'drive', 'arrival': '2030-01-02T12:00',
                    'departure_buffer': 5, 'arrival_buffer': 10}
            with patch.dict(p.os.environ, {'ALIGN_JOURNEY_PROVIDER': 'here', 'ALIGN_HERE_ROUTING_KEY': 'secret'}, clear=True), \
                 patch.object(p, 'fetch_json', side_effect=responses) as fetch:
                result = p.here_journey(c, body)
            self.assertEqual(result['provider'], 'HERE')
            self.assertEqual(result['traffic_adjustment']['extra_minutes'], 10)
            self.assertEqual(result['weather_adjustment']['extra_minutes'], 10)
            self.assertNotIn('secret', str(result))

if __name__=='__main__':unittest.main()
