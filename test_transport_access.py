"""NaPTAN proximity and live-delay parsing. No network and no invented routes."""
import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import here_transit
from transport_access import (
    access_cap_metres,
    area_codes,
    parse_bods_delay,
    parse_darwin_delay,
    prefer_closer_boarding,
    service_delay,
)
from transport_providers import OTPProvider, StatusHook


LIVERPOOL = (53.4, -2.98)


def test_merseyside_point_selects_published_area():
    assert area_codes(LIVERPOOL)[0] == '280'


def test_long_walk_is_dropped_when_a_closer_stop_exists():
    stops = [{'mode': 'bus', 'metres': 120, 'id': '2800A', 'name': 'Near'}]
    long_walk = {'legs': [
        {'mode': 'walk', 'minutes': 20, 'from': 'Home', 'to': 'Far stop'},
        {'mode': 'bus', 'service': '441', 'from': 'Far stop', 'to': 'Hospital'},
    ]}
    short_walk = {'legs': [
        {'mode': 'walk', 'minutes': 2, 'from': 'Home', 'to': 'Near'},
        {'mode': 'bus', 'service': '418', 'from': 'Near', 'to': 'Hospital'},
    ]}
    kept, dropped = prefer_closer_boarding([long_walk, short_walk], stops, ['walk', 'bus'])
    assert dropped == 1
    assert kept == [short_walk]
    assert access_cap_metres(stops, ['walk', 'bus']) == 300


def test_without_stop_data_the_provider_journey_is_kept():
    journey = {'legs': [{'mode': 'walk', 'minutes': 20}, {'mode': 'bus', 'service': '441'}]}
    kept, dropped = prefer_closer_boarding([journey], [], ['walk', 'bus'])
    assert dropped == 0
    assert kept == [journey]
    assert access_cap_metres([], ['bus']) is None


def test_here_uses_stop_distance_instead_of_a_fixed_walk(monkeypatch):
    with TemporaryDirectory() as folder:
        path = Path(folder) / 'stops.csv'
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=['ATCOCode', 'CommonName', 'Latitude', 'Longitude', 'StopType', 'Status'])
            writer.writeheader()
            writer.writerow({'ATCOCode': '28000001', 'CommonName': 'Near', 'Latitude': '53.4004', 'Longitude': '-2.9802', 'StopType': 'BCT', 'Status': 'active'})
        monkeypatch.setenv('ALIGN_NAPTAN_CSV', str(path))
        monkeypatch.setenv('ALIGN_HERE_TRANSIT_ENABLED', '1')
        monkeypatch.setenv('ALIGN_HERE_ROUTING_KEY', 'test')
        with patch.object(here_transit, 'request_json', return_value={'routes': []}) as fetch, patch('here_quota.reserve'):
            here_transit.HERETransitProvider().plan(LIVERPOOL, (53.41, -2.97), datetime(2030, 7, 2, 12, tzinfo=timezone.utc), ['walk', 'bus'])
        distance = parse_qs(urlparse(fetch.call_args.args[0]).query)['pedestrian[maxDistance]'][0]
        assert int(distance) < 500


def test_otp_refuses_to_call_loopback_when_unconfigured():
    with patch.dict(os.environ, {'ALIGN_OTP_URL': ''}, clear=False):
        try:
            OTPProvider().plan((53, -3), (53.1, -3), datetime(2030, 7, 2, 12, tzinfo=timezone.utc), ['walk', 'bus'])
        except Exception as error:
            assert type(error).__name__ == 'ProviderUnavailable'
        else:
            raise AssertionError('OTP should not plan without ALIGN_OTP_URL')


def test_bods_delay_uses_the_matched_stop_only():
    payload = '''<Siri><ServiceDelivery><VehicleMonitoringDelivery><VehicleActivity>
      <MonitoredVehicleJourney>
        <PublishedLineName>441</PublishedLineName>
        <MonitoredCall>
          <StopPointName>Arrowe Park Hospital</StopPointName>
          <AimedDepartureTime>2030-07-02T09:00:00Z</AimedDepartureTime>
          <ExpectedDepartureTime>2030-07-02T09:06:00Z</ExpectedDepartureTime>
        </MonitoredCall>
      </MonitoredVehicleJourney>
    </VehicleActivity></VehicleMonitoringDelivery></ServiceDelivery></Siri>'''
    assert parse_bods_delay(payload, '441', 'Arrowe Park Hospital') == 6
    assert parse_bods_delay(payload, '418', 'Arrowe Park Hospital') is None
    assert parse_bods_delay(payload, '441', 'Other Stop') is None


def test_darwin_delay_uses_the_scheduled_time():
    payload = '''<Board><service><std>09:10</std><etd>09:14</etd><operator>Merseyrail</operator>
      <destination><location><locationName>Liverpool Central</locationName></location></destination></service></Board>'''
    when = datetime(2030, 7, 2, 9, 10, tzinfo=timezone.utc)
    assert parse_darwin_delay(payload, 'Merseyrail', 'Liverpool Central', when) == 4


def test_missing_bods_key_does_not_invent_a_delay(monkeypatch):
    monkeypatch.delenv('ALIGN_BODS_API_KEY', raising=False)
    monkeypatch.delenv('ALIGN_BODS_LIVE_URL', raising=False)
    assert service_delay({'mode': 'bus', 'service': '441', 'from': 'Near'}) is None
    assert StatusHook('bods').refresh([{'mode': 'bus', 'service': '441', 'from': 'Near', 'to': 'Hospital', 'start': '2030-07-02T09:00:00+00:00', 'end': '2030-07-02T09:20:00+00:00'}]) is None
