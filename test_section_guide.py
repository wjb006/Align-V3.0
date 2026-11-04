"""Guided section setup, saved places and event defaults."""
import sqlite3
import unittest
from datetime import timedelta
from pathlib import Path

import icloud_sync
import migration_runner
import travel_reminders
from icalendar import Calendar
from test_support import IsolatedAppServer


class SectionGuideTests(IsolatedAppServer, unittest.TestCase):
    def test_section_defaults_places_labels_and_reminders(self):
        created = self.json_request('POST', '/api/sections', {
            'name': 'Appointments',
            'icon': '📅',
            'colour': '#0878F9',
            'description': 'GP visits and hospitals',
            'guide': {
                'travel_minutes': 45,
                'travel_mode': 'bus',
                'travel_info': 'Bus from home',
                'leave_alert_minutes': 60,
                'reminder_minutes': 30,
                'places': [
                    {'name': 'GP', 'location': '1 High Street, Liverpool', 'is_default': True},
                    {'name': '', 'location': 'Royal Hospital'},
                ],
            },
        })
        section = self.json_request('GET', f"/api/sections/{created['id']}")
        self.assertEqual(section['name'], 'Appointments')
        self.assertEqual(section['guide']['travel_minutes'], 45)
        self.assertEqual(section['guide']['travel_mode'], 'bus')
        self.assertEqual(section['guide']['leave_alert_minutes'], 60)
        self.assertEqual(len(section['places']), 2)
        self.assertEqual(section['places'][0]['name'], 'GP')
        self.assertEqual(section['guide']['place_id'], section['places'][0]['id'])

        event = self.json_request('POST', f"/api/sections/{created['id']}/events", {
            'title': 'GP visit',
            'start_at': f'{self.day}T09:00',
            'end_at': f'{self.day}T09:30',
            'location': '1 High Street, Liverpool',
            'notes': 'Bring letters',
            'travel_info': '45 minutes · Bus\nBus from home',
            'leave_alert_minutes': 60,
            'reminder_minutes': 30,
            'event_type': 'Appointment',
            'label_name': 'Health',
            'save_place': True,
            'place_name': 'GP',
        })
        section = self.json_request('GET', f"/api/sections/{created['id']}")
        saved = next(item for item in section['events'] if item['title'] == 'GP visit')
        self.assertEqual(saved['event_type'], 'Appointment')
        self.assertEqual(saved['label_name'], 'Health')
        self.assertIn('Bring letters', saved['notes'])
        self.assertIn('[Align travel-info]', saved['notes'])
        self.assertIn('[Align travel reminder: 60 minutes before]', saved['notes'])
        self.assertIn('[Align event reminder: 30 minutes before]', saved['notes'])
        self.assertEqual(travel_reminders.minutes(saved['notes']), 60)
        self.assertEqual(travel_reminders.event_minutes(saved['notes']), 30)
        raw, _ = icloud_sync.organiser_event(saved, 'guide-test')
        alarms = Calendar.from_ical(raw).walk('VALARM')
        self.assertEqual(sorted(alarm.decoded('TRIGGER') for alarm in alarms), [timedelta(minutes=-60), timedelta(minutes=-30)])
        self.assertEqual(sum(1 for place in section['places'] if place['name'] == 'GP'), 1)

        again = self.json_request('POST', f"/api/sections/{created['id']}/events", {
            'title': 'Repeat visit',
            'start_at': f'{self.day}T11:00',
            'end_at': f'{self.day}T11:30',
            'location': '1 High Street, Liverpool',
            'event_type': 'Appointment',
            'label_name': 'Health',
            'save_place': True,
            'place_name': 'GP',
            'leave_alert_minutes': 60,
            'reminder_minutes': 15,
        })
        self.assertNotEqual(again['id'], event['id'])
        section = self.json_request('GET', f"/api/sections/{created['id']}")
        self.assertEqual(sum(1 for place in section['places'] if place['location'] == '1 High Street, Liverpool'), 1)
        catalog = self.json_request('GET', '/api/section-guide')
        self.assertTrue(any(label['name'] == 'Health' for label in catalog['labels']))
        self.assertTrue(any(place['location'] == 'Royal Hospital' for place in catalog['places']))

        updated = self.json_request('PUT', f"/api/sections/{created['id']}", {
            'name': 'Appointments',
            'icon': '🏥',
            'colour': '#16D9F2',
            'guide': {
                'travel_minutes': 20,
                'travel_mode': 'transit',
                'travel_info': 'Walk',
                'leave_alert_minutes': 30,
                'reminder_minutes': 10,
                'places': [{'id': section['places'][1]['id'], 'name': '', 'location': 'Royal Hospital', 'is_default': True}],
            },
        })
        self.assertEqual(updated['id'], created['id'])
        section = self.json_request('GET', f"/api/sections/{created['id']}")
        self.assertEqual(section['guide']['travel_minutes'], 20)
        self.assertEqual(len(section['places']), 1)
        self.assertEqual(section['places'][0]['location'], 'Royal Hospital')

    def test_rejects_a_place_without_a_location_and_keeps_old_events(self):
        status, _, body = self.request('POST', '/api/sections', {
            'name': 'Bad',
            'guide': {'places': [{'name': 'GP', 'location': ''}]},
        })
        self.assertEqual(status, 400, body)
        self.assertIn(b'location', body.lower())
        created = self.json_request('POST', '/api/sections', {'name': 'Notes only'})
        event = self.json_request('POST', f"/api/sections/{created['id']}/events", {
            'title': 'Plain',
            'start_at': f'{self.day}T09:00',
            'end_at': f'{self.day}T10:00',
            'notes': 'Keep this [Align travel reminder: 45 minutes before]',
        })
        section = self.json_request('GET', f"/api/sections/{created['id']}")
        saved = section['events'][0]
        self.assertEqual(saved['id'], event['id'])
        self.assertIn('[Align travel reminder: 45 minutes before]', saved['notes'])
        self.assertNotIn('event_type', saved)

    def test_fresh_and_legacy_databases_gain_the_tables_once(self):
        with sqlite3.connect(self.original_database if False else Path(self.temp.name) / 'test.sqlite3') as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'saved_places', 'planner_labels', 'section_defaults', 'organiser_event_details'} <= names)
        legacy = Path(self.temp.name) / 'legacy.sqlite3'
        schema = Path('schema.sql').read_text(encoding='utf-8')
        with sqlite3.connect(legacy) as connection:
            connection.executescript(schema)
        first = migration_runner.ensure_section_guide_schema(legacy)
        second = migration_runner.ensure_section_guide_schema(legacy)
        self.assertEqual(first['status'], 'applied')
        self.assertEqual(second['status'], 'skipped')
        text = Path('schema_v3.sqlite.sql').read_text(encoding='utf-8')
        fresh = Path('migrations/postgres/fresh_v3_schema.sql').read_text(encoding='utf-8')
        self.assertIn('saved_places', text)
        self.assertIn('158_section_guides', text)
        self.assertIn('organiser_event_details', fresh)
        self.assertIn('158_section_guides', fresh)


if __name__ == '__main__':
    unittest.main()
