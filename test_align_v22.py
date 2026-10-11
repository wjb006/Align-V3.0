"""Align V2.2 helpers: home area content and event colour metadata."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

import app
import owner_builder
import personal_planner


class HomeAreaContentTests(unittest.TestCase):
    def test_defaults_exclude_shift_summary_and_preserve_content(self):
        class Connection:
            def execute(self, *args, **kwargs):
                return []

        doc = owner_builder.defaults(Connection())
        ids = {section['id']: section for section in doc['home_sections']}
        self.assertNotIn('stats', ids)
        self.assertTrue(ids['today']['content']['show_schedule'])
        self.assertTrue(ids['upcoming']['content']['group_by_day'])

    def test_validate_preserves_area_content_toggles(self):
        sections = owner_builder.validate_home_sections([
            {
                'id': 'today',
                'title': 'Today',
                'visible': True,
                'sort_order': 10,
                'content': {'show_weather': False, 'show_schedule': True, 'show_quick_add': False},
            },
            {
                'id': 'upcoming',
                'title': 'Upcoming Events',
                'visible': True,
                'sort_order': 30,
                'content': {'group_by_day': False},
            },
        ])
        today = next(section for section in sections if section['id'] == 'today')
        upcoming = next(section for section in sections if section['id'] == 'upcoming')
        self.assertFalse(today['content']['show_weather'])
        self.assertTrue(today['content']['show_schedule'])
        self.assertFalse(upcoming['content']['group_by_day'])


class PersonalEventColourTests(unittest.TestCase):
    def test_events_include_section_colour(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'align.sqlite3'
            app.initialise_database_at(database)
            with app.db_connection() as connection:
                # Point the shared DATABASE at this temp file for the connection helper.
                pass
            original = app.DATABASE
            app.DATABASE = database
            try:
                with app.db_connection() as connection:
                    connection.execute(
                        "INSERT INTO organiser_sections(name,description,icon,colour,calendar_url,calendar_name,import_enabled,export_enabled,active,sort_order) "
                        "VALUES('Dental','','•','#aa3344','','',1,1,1,10)"
                    )
                    section_id = connection.execute('SELECT id FROM organiser_sections').fetchone()['id']
                    day = date.today().isoformat()
                    connection.execute(
                        "INSERT INTO organiser_events(section_id,title,start_at,end_at,all_day,location,notes) VALUES(?,?,?,?,0,'Clinic','')",
                        (section_id, 'Check-up', f'{day}T10:00', f'{day}T11:00'),
                    )
                    connection.commit()
                    rows = personal_planner.events(connection, date.today())
                event = next(row for row in rows if row['title'] == 'Check-up')
                self.assertEqual(event['section_colour'], '#aa3344')
                self.assertEqual(event['category_name'], 'Dental')
            finally:
                app.DATABASE = original


if __name__ == '__main__':
    unittest.main()
