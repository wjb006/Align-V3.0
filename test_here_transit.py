from datetime import datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
import here_transit as here
import personal_otp as otp
import personal_planner as personal
from test_personal_otp import Connection
import test_personal_otp as fixtures


def section(mode='bus', start='2030-07-02T10:10:00Z', end='2030-07-02T10:30:00Z'):
    return {'transport': {'mode': mode, 'name': '42'},
            'departure': {'time': start, 'place': {'name': 'Stop'}, 'platform': '2'},
            'arrival': {'time': end, 'place': {'name': 'Destination'}}}


def test_disabled_makes_no_request():
    with patch.dict(here.os.environ, {'ALIGN_HERE_TRANSIT_ENABLED': '0'}), patch.object(here, 'request_json') as fetch:
        with pytest.raises(ValueError, match='verification'):
            here.HERETransitProvider().plan((53, -3), (53, -2), datetime.now(), ['walk', 'bus'])
        fetch.assert_not_called()


def test_arrival_request_and_strict_mode_conversion():
    routes = [{'sections': [section()]}, {'sections': [section('pedestrian')]},
              {'sections': [section('ferry')]}, {'sections': [section('bus', end='2030-07-02T10:00:00Z')]}]
    target = datetime.fromisoformat('2030-07-02T12:00:00+01:00')
    with patch.dict(here.os.environ, {'ALIGN_HERE_TRANSIT_ENABLED': '1', 'ALIGN_HERE_ROUTING_KEY': 'test'}), patch.object(here, 'request_json', return_value={'routes': routes}) as fetch, patch('here_quota.reserve'):
        result = here.HERETransitProvider().plan((53, -3), (53, -2), target, ['walk', 'bus'])
    params = parse_qs(urlparse(fetch.call_args.args[0]).query)
    assert params['arrivalTime'] == [target.isoformat()]
    assert params['modes'] == [','.join(here.BUS)]
    assert len(result) == 1
    assert result[0]['legs'][0]['service_number'] == '42'
    assert result[0]['legs'][0]['platform'] == ''


def test_here_transit_never_calls_google_or_local_otp():
    with patch.dict(personal.os.environ, {'ALIGN_JOURNEY_PROVIDER': 'here'}), patch.object(personal, 'preferences', return_value=personal.DEFAULTS), patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')), patch.object(here.HERETransitProvider, 'plan', return_value=fixtures.PersonalOTPTests().routes()), patch.object(personal, 'google_journey') as google, patch.object(otp.OTPProvider, 'plan') as local, patch.object(personal, 'weather_risk', return_value=(0, {})):
        result = personal.journey(Connection(), fixtures.PersonalOTPTests().body())
    google.assert_not_called()
    local.assert_not_called()
    assert result['provider'] == 'HERE'
    assert result['leave_at'] == '2030-07-02T10:55+01:00'
    assert [step['mode'] for step in result['steps']] == ['walk', 'wait', 'bus', 'walk']
    assert 'HERE' in result['notes']


def test_here_drive_keeps_existing_provider():
    with patch.dict(personal.os.environ, {'ALIGN_JOURNEY_PROVIDER': 'here'}), patch.object(personal, 'preferences', return_value=personal.DEFAULTS), patch.object(personal, 'here_journey', return_value={'provider': 'HERE'}) as drive:
        assert personal.journey(Connection(), {'mode': 'drive'}) == {'provider': 'HERE'}
    drive.assert_called_once()
