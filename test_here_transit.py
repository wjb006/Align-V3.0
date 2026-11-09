from datetime import datetime
from unittest.mock import Mock, patch
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
    assert params['pedestrian[maxDistance]'] == ['2000']
    assert len(result) == 1
    assert result[0]['legs'][0]['service_number'] == '42'
    assert result[0]['legs'][0]['platform'] == ''


def test_documented_pedestrian_sections_are_preserved():
    walking = section('pedestrian', '2030-07-02T10:00:00Z', '2030-07-02T10:10:00Z')
    walking['type'] = 'pedestrian'
    del walking['transport']
    route = {'sections': [walking, section()]}
    with patch.dict(here.os.environ, {'ALIGN_HERE_TRANSIT_ENABLED': '1', 'ALIGN_HERE_ROUTING_KEY': 'test'}), \
         patch.object(here, 'request_json', return_value={'routes': [route]}), patch('here_quota.reserve'):
        result = here.HERETransitProvider().plan((53, -3), (53, -2), datetime.fromisoformat('2030-07-02T12:00:00+01:00'), ['walk', 'bus'])
        without_walk = here.HERETransitProvider().plan((53, -3), (53, -2), datetime.fromisoformat('2030-07-02T12:00:00+01:00'), ['bus'])
    assert [leg['mode'] for leg in result[0]['legs']] == ['walk', 'bus']
    assert without_walk == []


def test_documented_walking_sections_reach_personal_journey():
    walking = section('pedestrian', '2030-07-02T10:00:00Z', '2030-07-02T10:10:00Z')
    walking['type'] = 'pedestrian'
    del walking['transport']
    with patch.dict(personal.os.environ, {'ALIGN_JOURNEY_PROVIDER': 'here', 'ALIGN_HERE_TRANSIT_ENABLED': '1',
                                          'ALIGN_HERE_ROUTING_KEY': 'test'}), \
         patch.object(personal, 'preferences', return_value=personal.DEFAULTS), \
         patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')), \
         patch.object(here, 'request_json', return_value={'routes': [{'sections': [walking, section()]}]}), \
         patch('here_quota.reserve'), patch.object(personal, 'weather_risk', return_value=(0, {})):
        result = personal.journey(Connection(), fixtures.PersonalOTPTests().body())
    assert result['provider'] == 'HERE'
    assert [step['mode'] for step in result['steps']] == ['walk', 'bus']
    assert result['steps'][1]['service'] == '42'
    assert result['scheduled'] is True


def test_arrive_by_prefers_fastest_even_if_it_has_more_transfers():
    def leg(mode, start, end, service=''):
        return {'mode': mode, 'start': f'2030-07-02T{start}:00+01:00',
                'end': f'2030-07-02T{end}:00+01:00', 'service': service,
                'from': 'Stop', 'to': 'Stop'}
    direct = {'legs': [leg('walk', '10:00', '10:05'),
                       leg('bus', '10:05', '10:25', '1'),
                       leg('walk', '10:25', '10:30')]}
    transfer = {'legs': [leg('walk', '10:10', '10:15'),
                         leg('bus', '10:15', '10:25', '2'),
                         leg('bus', '10:27', '10:32', '3'),
                         leg('walk', '10:32', '10:35')]}
    provider = Mock()
    provider.plan.return_value = [direct, transfer]
    with patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')):
        result = otp.plan(Connection(), fixtures.PersonalOTPTests().body(),
                          personal.DEFAULTS, provider, 'HERE')
    assert [step['service'] for step in result['steps'] if step['mode'] == 'bus'] == ['2', '3']
    assert [step['service'] for step in result['journeys'][1]['steps'] if step['mode'] == 'bus'] == ['1']


def test_here_fastest_direct_route_keeps_final_walk():
    def walk(start, end):
        return {'type': 'pedestrian',
                'departure': {'time': f'2030-07-02T{start}:00+01:00', 'place': {'name': 'Start'}},
                'arrival': {'time': f'2030-07-02T{end}:00+01:00', 'place': {'name': 'End'}}}
    def bus(start, end, number):
        return {'type': 'transit', 'transport': {'mode': 'bus', 'name': number},
                'departure': {'time': f'2030-07-02T{start}:00+01:00', 'place': {'name': 'Stop'}},
                'arrival': {'time': f'2030-07-02T{end}:00+01:00', 'place': {'name': 'Stop'}}}
    direct = {'sections': [walk('10:00', '10:04'), bus('10:04', '10:20', '10'),
                           walk('10:20', '10:23')]}
    transfer = {'sections': [walk('10:05', '10:09'), bus('10:09', '10:18', '20'),
                             bus('10:20', '10:28', '30'), walk('10:28', '10:31')]}
    with patch.dict(personal.os.environ, {'ALIGN_JOURNEY_PROVIDER': 'here', 'ALIGN_HERE_TRANSIT_ENABLED': '1',
                                          'ALIGN_HERE_ROUTING_KEY': 'test'}), \
         patch.object(personal, 'preferences', return_value=personal.DEFAULTS), \
         patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')), \
         patch.object(here, 'request_json', return_value={'routes': [direct, transfer]}), \
         patch('here_quota.reserve'), patch.object(personal, 'weather_risk', return_value=(0, {})):
        result = personal.journey(Connection(), fixtures.PersonalOTPTests().body())
    assert [step['service'] for step in result['steps'] if step['mode'] == 'bus'] == ['10']
    assert [step['mode'] for step in result['steps']] == ['walk', 'bus', 'walk']
    assert result['arrival_at'].endswith('10:23+01:00')
    assert [step['service'] for step in result['journeys'][1]['steps'] if step['mode'] == 'bus'] == ['20', '30']


def test_fastest_arrive_by_filters_late_routes_and_breaks_ties_by_latest_departure():
    def candidate(start, end, service):
        return {'legs': [{'mode': 'bus', 'start': f'2030-07-02T{start}+01:00',
                          'end': f'2030-07-02T{end}+01:00', 'service': service,
                          'from': 'Start', 'to': 'Destination'}]}
    routes = [
        candidate('11:59:30', '12:00:01', 'late'),
        candidate('10:00:00', '10:30:59', 'slower'),
        candidate('10:30:00', '11:00:01', 'earlier'),
        candidate('11:29:59', '12:00:00', 'latest'),
        candidate('11:00:00', '11:30:30', 'rounded-up'),
    ]
    provider = Mock()
    provider.plan.return_value = routes
    with patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')):
        result = otp.plan(Connection(), {**fixtures.PersonalOTPTests().body(), 'arrival_buffer': 0},
                          personal.DEFAULTS, provider, 'HERE')
    assert [journey['steps'][0]['service'] for journey in result['journeys']] == [
        'latest', 'earlier', 'rounded-up', 'slower']
    assert provider.plan.call_args.args[2].isoformat() == '2030-07-02T12:00:00+01:00'


def test_no_fastest_route_is_fabricated_when_provider_has_no_feasible_journey():
    provider = Mock()
    provider.plan.return_value = [{'legs': [{'mode': 'bus',
        'start': '2030-07-02T11:59:00+01:00', 'end': '2030-07-02T12:01:00+01:00'}]}]
    with patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')):
        with pytest.raises(ValueError, match='No scheduled journey'):
            otp.plan(Connection(), {**fixtures.PersonalOTPTests().body(), 'arrival_buffer': 0},
                     personal.DEFAULTS, provider, 'HERE')
        provider.plan.return_value = []
        with pytest.raises(ValueError, match='No scheduled journey'):
            otp.plan(Connection(), fixtures.PersonalOTPTests().body(), personal.DEFAULTS, provider, 'HERE')


def test_depart_after_still_prefers_earliest_arrival():
    provider = Mock()
    provider.plan.return_value = [
        {'legs': [{'mode': 'bus', 'start': '2030-07-02T10:00:00+01:00',
                   'end': '2030-07-02T10:40:00+01:00', 'service': 'early'}]},
        {'legs': [{'mode': 'bus', 'start': '2030-07-02T10:50:00+01:00',
                   'end': '2030-07-02T11:00:00+01:00', 'service': 'fast'}]},
    ]
    body = {**fixtures.PersonalOTPTests().body(), 'departure': '2030-07-02T10:00',
            'departure_buffer': 0, 'arrival_buffer': 0}
    with patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')):
        result = otp.plan(Connection(), body, personal.DEFAULTS, provider, 'HERE')
    assert result['steps'][0]['service'] == 'early'


def test_depart_after_with_deadline_selects_fastest_before_limiting_results():
    provider = Mock()
    provider.plan.return_value = [
        {'legs': [{'mode': 'bus', 'start': f'2030-07-02T10:{i:02d}:00+01:00',
                   'end': f'2030-07-02T11:{i:02d}:00+01:00', 'service': str(i)}]}
        for i in range(5)
    ] + [{'legs': [{'mode': 'bus', 'start': '2030-07-02T11:30:00+01:00',
                     'end': '2030-07-02T12:00:00+01:00', 'service': 'fast'}]},
         {'legs': [{'mode': 'bus', 'start': '2030-07-02T11:59:00+01:00',
                     'end': '2030-07-02T12:01:00+01:00', 'service': 'late'}]}]
    body = {**fixtures.PersonalOTPTests().body(), 'departure': '2030-07-02T10:00',
            'deadline': '2030-07-02T12:00', 'departure_buffer': 0}
    with patch.object(otp, 'resolve_place', return_value=((53., -3.), 'postcode centre')):
        result = otp.plan(Connection(), body, personal.DEFAULTS, provider, 'HERE')
    assert result['steps'][0]['service'] == 'fast'
    assert len(result['journeys']) == otp.MAX_JOURNEYS


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
