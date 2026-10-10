import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
import transport_service as travel
from transport_providers import ProviderUnavailable


def test_hosted_travel_uses_here_and_caches_without_coordinates():
    c = sqlite3.connect(':memory:')
    c.executescript(Path('migrations/149_transport.sql').read_text())
    c.execute('CREATE TABLE organiser_events(id INTEGER PRIMARY KEY,start_at TEXT,location TEXT,all_day INTEGER)')
    target = datetime.now(timezone.utc) + timedelta(days=1)
    c.execute('INSERT INTO organiser_events VALUES(1,?,?,0)', (target.isoformat(), 'Liverpool Lime Street'))
    route = {'provider':'HERE','attributions':['Timetable source'], 'legs':[{'mode':'rail','start':(target-timedelta(minutes=40)).isoformat(),'end':(target-timedelta(minutes=15)).isoformat(),'from':'Private origin','to':'Destination station'}]}
    body = {'event_key':'event:1','origin':[53,-3],'destination':[53,-2.9],'location_consent':True}
    with patch.dict(travel.os.environ, {'ALIGN_JOURNEY_PROVIDER':'here'}), patch('here_transit.HERETransitProvider.plan',return_value=[route]) as here, patch.object(travel.OTPProvider,'plan') as otp:
        result = travel.plan(c,body)
        assert result['state'] == 'on_time'
        assert result['journeys'][0]['provider'] == 'HERE'
        assert result['journeys'][0]['attributions'] == ['Timetable source']
        here.assert_called_once()
        otp.assert_not_called()
        saved = travel.cached(c,'event:1')
        assert saved['journeys'][0]['legs'][0]['from'] == 'Start'
        assert 'Private origin' not in c.execute('SELECT payload FROM transport_journey_cache').fetchone()[0]
        here.side_effect = ProviderUnavailable('offline')
        assert travel.plan(c,body)['cached'] is True
        with pytest.raises(ValueError,match='Confirm'):
            travel.plan(c,{**body,'location_consent':False})
    c.close()


def test_here_status_does_not_claim_otp_is_hosted_routing():
    with patch.dict(travel.os.environ, {'ALIGN_JOURNEY_PROVIDER':'here','ALIGN_HERE_ROUTING_KEY':'','ALIGN_HERE_TRANSIT_ENABLED':'1','ALIGN_OTP_URL':'http://localhost:8080'}):
        assert travel.routing_status() == {'provider':'HERE','routing_configured':False}
