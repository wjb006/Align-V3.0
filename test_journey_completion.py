from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from icalendar import Event
import pytest
import unittest
import app
import personal_planner as personal
import personal_otp as otp
import transport_places
import transport_service
from icloud_sync import busy_event
import test_work_setup as setup_fixture
from test_personal_otp import Connection


def test_here_home_address_fallback():
    with patch.dict(personal.os.environ, {'ALIGN_HERE_ROUTING_KEY':'test'}), patch.object(personal,'here_point',return_value={'lat':53.4,'lng':-3}) as point:
        assert otp.resolve_journey_place('Example street, Birkenhead','HERE') == ((53.4,-3.0),'HERE address lookup')
        point.assert_called_once_with('test','Example street, Birkenhead')
        with pytest.raises(ValueError):
            otp.resolve_journey_place('Example street, Birkenhead','OpenTripPlanner')
        assert point.call_count == 1


def test_driving_notes_match_buffered_arrival():
    with patch.dict(personal.os.environ, {'ALIGN_HERE_ROUTING_KEY':'test'}), patch.object(personal,'preferences',return_value=personal.DEFAULTS), patch.object(personal,'here_point',return_value={'lat':53,'lng':-3}), patch.object(personal,'here_fetch',return_value={'routes':[{'sections':[{'summary':{'duration':1200,'baseDuration':1200}}]}]}), patch.object(personal,'weather_risk',return_value=(0,{})):
        result=personal.here_journey(Connection(),{'arrival':'2030-07-02T12:00','destination':'Liverpool'})
    assert 'Arrive: '+result['arrival_at'][11:16]+' · Event: 12:00' in result['notes']


class CalendarTravelTests(unittest.TestCase):
    setUp = setup_fixture.WorkSetupTests.setUp
    tearDown = setup_fixture.WorkSetupTests.tearDown
    json_request = setup_fixture.WorkSetupTests.json_request
    request = setup_fixture.WorkSetupTests.request
    def test_import_location_and_account_scoped_travel_key(self):
        with app.db_connection() as c:
            app.import_ics_calendar(c,'Test', 'BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:test-location\nDTSTART:20300702T120000\nDTEND:20300702T130000\nSUMMARY:Station visit\nLOCATION:Liverpool Lime Street\nEND:VEVENT\nEND:VCALENDAR')
            items=transport_places.items(c)['items']
            imported=next(i for i in items if i['title']=='Station visit')
            assert imported['destination']=='Liverpool Lime Street'
            assert transport_service.event(c,imported['key'])[1]=='Liverpool Lime Street'
            with pytest.raises(ValueError):
                transport_service.event(c,imported['key'][:-1]+'f' if not imported['key'].endswith('f') else imported['key'][:-1]+'0')
            c.execute("UPDATE calendar_events SET location='' WHERE title='Station visit'")
            assert not any(i['title']=='Station visit' for i in transport_places.items(c)['items'])


def test_icloud_retains_location():
    e=Event();e.add('uid','external-location');e.add('summary','Station visit')
    e.add('dtstart',datetime(2030,7,2,12,tzinfo=timezone.utc));e.add('dtend',datetime(2030,7,2,13,tzinfo=timezone.utc));e.add('location','Liverpool Lime Street')
    assert busy_event(e,'owned-')[-1]=='Liverpool Lime Street'

def test_station_aliases_do_not_use_geocoding():
    with patch.object(personal,'here_fetch') as fetch:
        point=personal.here_point('test','Liverpool Lime Street railway station, Liverpool')
        assert point=={'lat':53.407306637,'lng':-2.977725997}
        assert otp.resolve_place('Liverpool Lime Street station, Liverpool')[0] == (point['lat'],point['lng'])
        fetch.assert_not_called()


def test_uncertain_geocode_is_rejected():
    for item in [
        {'position':{'lat':53,'lng':-3},'scoring':{'queryScore':0.4},'resultType':'street'},
        {'position':{'lat':53,'lng':-3},'scoring':{'queryScore':1},'resultType':'locality'}]:
        with patch.object(personal,'here_fetch',return_value={'items':[item]}):
            with pytest.raises(ValueError,match='uncertain'):
                personal.here_point('test','An ambiguous destination')
