import unittest
from datetime import date, timedelta
from icalendar import Calendar
import app, icloud_sync, personal_planner, travel_reminders
from test_support import IsolatedAppServer
class ReminderTests(unittest.TestCase):
    def test_range_and_existing_rules(self):
        self.assertIsNone(travel_reminders.minutes('[Align travel reminder: 20000 minutes before]'))
        self.assertEqual(travel_reminders.minutes('[Align travel reminder: 10080 minutes before]'), 10080)
        self.assertIsNone(travel_reminders.minutes('ordinary notes'))
        rules=travel_reminders.rules('[Align travel reminder: 45 minutes before]', [{'title':'Time to Leave','minutes_before':60},{'title':'Tomorrow','minutes_before':1440}])
        self.assertEqual([r['minutes_before'] for r in rules],[1440,45])
    def test_calendar_alarm_and_all_day(self):
        event={'title':'Appointment','start_at':'2026-10-25T10:00','end_at':'2026-10-25T11:00','notes':'[Align travel reminder: 45 minutes before]','all_day':False}
        raw,_=icloud_sync.organiser_event(event,'test')
        alarms=Calendar.from_ical(raw).walk('VALARM')
        self.assertEqual(len(alarms),1)
        self.assertEqual(alarms[0].decoded('TRIGGER'),timedelta(minutes=-45))
        event['all_day']=True
        raw,_=icloud_sync.organiser_event(event,'test')
        self.assertEqual(Calendar.from_ical(raw).walk('VALARM'),[])
class WeekEventsTests(unittest.TestCase):
    setUp=IsolatedAppServer.setUp
    tearDown=IsolatedAppServer.tearDown
    def test_week_events_are_scoped_to_dates_and_account(self):
        with app.db_connection() as c:
            section=c.execute("INSERT INTO organiser_sections(name) VALUES('Personal')").lastrowid
            for title,start,end in [('Overnight','2026-09-06T23:00','2026-09-07T02:00'),('Appointment','2026-09-09T10:00','2026-09-09T11:00'),('Outside','2026-09-14T10:00','2026-09-14T11:00')]:
                c.execute('INSERT INTO organiser_events(section_id,title,start_at,end_at) VALUES(?,?,?,?)',(section,title,start,end))
            titles=set()
            first=date.fromisoformat('2026-09-07')
            for offset in range(7):
                titles.update(event['title'] for event in personal_planner.events(c,first+timedelta(days=offset)))
            self.assertEqual(titles,{'Overnight','Appointment'})
