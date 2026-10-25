"""Restored shift planner route and persistence tests."""
import unittest
from datetime import date, timedelta

import app
from test_support import IsolatedAppServer


class ShiftPlannerApiTests(unittest.TestCase):
    setUp = IsolatedAppServer.setUp
    tearDown = IsolatedAppServer.tearDown
    request = IsolatedAppServer.request
    json_request = IsolatedAppServer.json_request

    def test_planner_read_routes_are_available(self):
        for path in ("/api/shifts", "/api/week?start=2026-10-12", "/api/month?month=2026-10",
                     "/api/annual-leave", "/api/alert-rules", "/api/alerts",
                     "/api/locations", "/api/user-locations", "/api/shift-types", "/api/templates"):
            with self.subTest(path=path):
                status, _, body = self.request("GET", path)
                self.assertEqual(status, 200, body)
                self.assertIsInstance(__import__("json").loads(body), dict)

    def test_create_shift_template_week_view_and_edit_delete(self):
        location = self.json_request("POST", "/api/locations", {"name":"Arrowe Park","address":"Wirral"})
        shift_type = self.json_request("POST", "/api/shift-types", {"name":"Clinic"})
        template = self.json_request("POST", "/api/templates", {
            "location_id":location["id"],"shift_type_id":shift_type["id"],"label":"AM clinic",
            "start_time":"08:30","end_time":"12:30","break_minutes":0,"applicable_days":["Monday","Tuesday"]
        })
        day=(date.today()+timedelta(days=14)).isoformat()
        shift = self.json_request("POST", "/api/shifts", {
            "work_date":day,"template_id":template["id"],"location_id":location["id"],
            "shift_type_id":shift_type["id"],"start_time":"08:30","end_time":"12:30","break_minutes":"0","notes":"Test"
        })
        self.assertEqual(shift["shifts"][0]["hours"],4)
        week=self.json_request("GET", "/api/week?start="+day, expected=200)
        self.assertTrue(any(item["work_date"]==day for item in week["shifts"]))
        self.assertTrue(week["templates"])
        item_id=shift["shifts"][0]["id"]
        self.json_request("PUT", f"/api/shifts/{item_id}", {
            "work_date":day,"location_id":location["id"],"shift_type_id":shift_type["id"],
            "start_time":"09:00","end_time":"13:30","break_minutes":"30","notes":"Updated"
        }, expected=200)
        with app.db_connection() as connection:
            saved=connection.execute("SELECT start_time,end_time,hours,notes FROM shifts WHERE id=?",(item_id,)).fetchone()
            self.assertEqual(tuple(saved),("09:00","13:30",4.0,"Updated"))
            self.assertTrue(connection.execute("SELECT 1 FROM alerts WHERE shift_id=?",(item_id,)).fetchone())
        self.json_request("DELETE",f"/api/shifts/{item_id}",expected=200)
        with app.db_connection() as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM shifts WHERE id=?",(item_id,)).fetchone())

    def test_shift_overlap_and_annual_leave_are_enforced(self):
        location=self.json_request("POST","/api/locations",{"name":"Clinic"})
        shift_type=self.json_request("POST","/api/shift-types",{"name":"Wards"})
        day=(date.today()+timedelta(days=18)).isoformat()
        payload={"work_date":day,"location_id":location["id"],"shift_type_id":shift_type["id"],
                 "start_time":"08:00","end_time":"12:00","break_minutes":0}
        self.json_request("POST","/api/shifts",payload)
        status,_,body=self.request("POST","/api/shifts",{**payload,"start_time":"11:00","end_time":"15:00"})
        self.assertEqual(status,400)
        self.assertIn("overlaps",body.decode().lower())
        leave_day=(date.today()+timedelta(days=25)).isoformat()
        self.json_request("POST","/api/annual-leave",{"start_date":leave_day,"end_date":leave_day,"notes":"Rest"})
        status,_,body=self.request("POST","/api/shifts",{**payload,"work_date":leave_day})
        self.assertEqual(status,400)
        self.assertIn("annual leave",body.decode().lower())
        leave=self.json_request("GET","/api/annual-leave?start="+leave_day+"&end="+leave_day,expected=200)
        self.assertEqual(len(leave["annual_leave"]),1)
        self.json_request("DELETE",f"/api/annual-leave/{leave['annual_leave'][0]['id']}",expected=200)

    def test_v3_storage_validator_does_not_depend_on_schedule_tables(self):
        from postgres_support import validate_v3_storage
        class RecordingConnection:
            def __init__(self): self.statements=[]
            def execute(self,statement):
                self.statements.append(statement)
                if any(table in statement for table in ("shifts","shift_templates","locations","shift_types","annual_leave","alert_rules","shift_batches")):
                    raise AssertionError("storage validator must stay schema-agnostic")
        connection=RecordingConnection()
        validate_v3_storage(connection)
        self.assertTrue(connection.statements)
        self.assertTrue(all("LIMIT 0" in statement for statement in connection.statements))

    def test_fresh_local_schema_includes_planner_and_organiser_tables(self):
        with app.db_connection() as connection:
            tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({'personal_items','organiser_events','assets','transport_preferences','transport_journey_cache',
                'locations','shift_types','location_shift_types','shift_templates','shifts','shift_batches',
                'annual_leave','alerts','alert_rules'} <= tables)

    def test_reinitializing_the_schema_keeps_shift_planner_data(self):
        with app.db_connection() as connection:
            connection.execute("INSERT INTO locations(name,address) VALUES('Legacy clinic','Legacy address')")
            location_id=connection.execute("SELECT id FROM locations WHERE name='Legacy clinic'").fetchone()[0]
            type_id=connection.execute("INSERT INTO shift_types(name) VALUES('Legacy AM')").lastrowid
            template_id=connection.execute("""INSERT INTO shift_templates(location_id,shift_type_id,label,sub_shift_type,start_time,end_time,applicable_days)
                VALUES(?,?,?,?,?,?,?)""",(location_id,type_id,'Keep this template','AM','08:30','12:30','["Monday"]')).lastrowid
            connection.execute("INSERT INTO shifts(work_date,template_id,location_id,shift_type_id,location_name,shift_type_name,colour,start_time,end_time,hours) VALUES(?,?,?,?,?,?,?,?,?,?)",
                ('2026-10-12',template_id,location_id,type_id,'Legacy clinic','Legacy AM','#365CE6','08:30','12:30',4))
            connection.execute("INSERT INTO annual_leave(leave_date,notes) VALUES('2026-10-13','Keep for recovery')")
        app.initialise_database()
        with app.db_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM shifts").fetchone()[0],1)
            self.assertEqual(connection.execute("SELECT notes FROM annual_leave").fetchone()[0],"Keep for recovery")
            self.assertEqual(connection.execute("SELECT label FROM shift_templates WHERE id=?",(template_id,)).fetchone()[0],"Keep this template")


if __name__ == "__main__":
    unittest.main()
