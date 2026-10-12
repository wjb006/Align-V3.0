import sqlite3,unittest
from unittest.mock import patch
import travel_refresh as travel


class RelatedTravelTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.executescript('''CREATE TABLE settings(setting_key TEXT PRIMARY KEY,setting_value TEXT);
        CREATE TABLE organiser_events(id INTEGER PRIMARY KEY,start_at TEXT,notes TEXT,location TEXT,all_day INTEGER);
        CREATE TABLE transport_journey_cache(event_key TEXT);
        INSERT INTO settings VALUES('user_address','Home');
        INSERT INTO organiser_events VALUES(1,'2099-09-28T09:00','', 'Old Clatterbridge',0);''')
        self.notes='Keep this ordinary note\n[Align travel]\nOld route\n[/Align travel]'
        self.c.execute('UPDATE organiser_events SET notes=? WHERE id=1',(self.notes,))
    def tearDown(self):self.c.close()
    def establish(self):
        with patch('personal_planner.journey',return_value={'notes':'New route','steps':[]}):travel.refresh_one(self.c)
    def test_location_change_invalidates_notes_and_cache(self):
        self.establish()
        self.c.execute("INSERT INTO transport_journey_cache VALUES('event:1')")
        self.c.execute("UPDATE organiser_events SET location='Correct Clatterbridge' WHERE id=1")
        self.assertEqual(travel.synchronize(self.c),1)
        notes=self.c.execute('SELECT notes FROM organiser_events WHERE id=1').fetchone()[0]
        self.assertIn('Keep this ordinary note',notes)
        self.assertIn(travel.PENDING,notes)
        self.assertNotIn('New route',notes)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM transport_journey_cache').fetchone()[0],0)
        with patch('personal_planner.journey',return_value={'notes':'Correct route'}) as route:
            travel.refresh_one(self.c)
            self.assertEqual(route.call_args.args[1]['destination'],'Correct Clatterbridge')
        self.assertIn('Correct route',self.c.execute('SELECT notes FROM organiser_events WHERE id=1').fetchone()[0])
        self.assertEqual(travel.synchronize(self.c),0)
    def test_home_and_time_changes_refresh_but_unchanged_does_not(self):
        self.establish()
        with patch('personal_planner.journey') as route:
            travel.refresh_one(self.c);route.assert_not_called()
        self.c.execute("UPDATE settings SET setting_value='New home' WHERE setting_key='user_address'")
        self.assertEqual(travel.synchronize(self.c),1)
        self.establish()
        self.c.execute("UPDATE organiser_events SET start_at='2099-09-28T10:00' WHERE id=1")
        self.assertEqual(travel.synchronize(self.c),1)
    def test_provider_failure_keeps_pending_and_throttles_retry(self):
        with patch('personal_planner.journey',side_effect=ValueError('Unavailable')) as route:
            result=travel.refresh_one(self.c)
            self.assertEqual(result,{'remaining':1,'ready':0})
            travel.refresh_one(self.c);self.assertEqual(route.call_count,1)
        self.assertNotIn('Old route',self.c.execute('SELECT notes FROM organiser_events WHERE id=1').fetchone()[0])
    def test_linked_future_event_address_changes_only(self):
        self.c.executemany('INSERT INTO organiser_events VALUES(?,?,?,?,0)',[(2,'2099-09-28T09:00',self.notes,'Old Clatterbridge'),(3,'2000-01-01T09:00',self.notes,'Old Clatterbridge'),(4,'2099-09-28T09:00','Manual','Elsewhere')])
        travel.location_changed(self.c,'Old Clatterbridge','Correct Clatterbridge')
        self.assertEqual([r[0] for r in self.c.execute('SELECT location FROM organiser_events WHERE id>1 ORDER BY id')],['Correct Clatterbridge','Old Clatterbridge','Elsewhere'])
    def test_manual_only_notes_not_routed(self):
        self.c.execute("UPDATE organiser_events SET notes='Manual only' WHERE id=1")
        with patch('personal_planner.journey') as route:
            travel.refresh_one(self.c);route.assert_not_called()
        self.assertEqual(self.c.execute('SELECT notes FROM organiser_events WHERE id=1').fetchone()[0],'Manual only')


if __name__=='__main__':
    unittest.main()
