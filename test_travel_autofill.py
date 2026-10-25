import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, Mock
import transport_places
import transport_service

class TravelAutofillTests(unittest.TestCase):
    @patch('personal_planner.here_point')
    @patch('personal_planner.fetch_json')
    def test_typing_never_discloses_address(self, fetch, here):
        self.assertEqual(transport_places.lookup({'query':'12 Example Avenue','local_only':True})['places'], [])
        fetch.assert_not_called()
        here.assert_not_called()

    @patch.dict(os.environ, {'ALIGN_JOURNEY_PROVIDER':'here','ALIGN_HERE_ROUTING_KEY':'test'})
    @patch('personal_planner.here_fetch', return_value={'items':[{'title':'Example Avenue, Liverpool','position':{'lat':53.4,'lng':-3.0},'resultType':'street','scoring':{'queryScore':1}}]})
    def test_explicit_address_lookup(self, here):
        result=transport_places.lookup({'query':'12 Example Avenue','consent':True})
        self.assertEqual(result['places'][0]['point'],[53.4,-3.0])
        self.assertEqual(result['places'][0]['name'],'Example Avenue, Liverpool')
        here.assert_called_once()

    @patch.dict(os.environ, {'ALIGN_JOURNEY_PROVIDER':'otp'}, clear=True)
    @patch('personal_planner.fetch_json', return_value={'features':[{'properties':{'street':'Example Avenue','postcode':'L1 1AA','city':'Liverpool','country':'United Kingdom','countrycode':'gb'},'geometry':{'coordinates':[-3.0,53.4]}}]})
    def test_explicit_address_lookup_uses_photon_without_here(self, fetch):
        result=transport_places.lookup({'query':'12 Example Avenue','consent':True})
        self.assertEqual(result['places'][0]['point'],[53.4,-3.0])
        self.assertIn('photon.komoot.io/api?',fetch.call_args.args[0])

    @patch('personal_planner.fetch_json', side_effect=[{'result':['L1 1AA']},{'result':{'postcode':'L1 1AA','latitude':53.4,'longitude':-3.0}}])
    def test_postcode_suggestions_use_postcodes_io_with_consent(self, fetch):
        result=transport_places.lookup({'query':'L1','consent':True})
        self.assertEqual(result['places'][0]['name'],'L1 1AA')
        self.assertIn('api.postcodes.io/postcodes/L1/autocomplete?',fetch.call_args_list[0].args[0])
        self.assertIn('api.postcodes.io/postcodes/L1%201AA',fetch.call_args_list[1].args[0])

    @patch.dict(os.environ, {'ALIGN_JOURNEY_PROVIDER':'here','ALIGN_HERE_ROUTING_KEY':'test'})
    @patch('personal_planner.here_point', return_value={'lat':53.4,'lng':-3.0})
    @patch('transport_service.preferences', return_value={'arrival_buffer':10,'home':None,'modes':['walk','bus']})
    @patch('transport_service.event', return_value=(datetime.now(timezone.utc)+timedelta(days=5),'Destination'))
    def test_manual_addresses_resolve_only_after_consent(self, event, prefs, here):
        body={'event_key':'shift:1','origin_address':'Home address','destination_address':'Event address'}
        with self.assertRaises(ValueError): transport_service.plan(Mock(),body,Mock())
        here.assert_not_called()
        provider=Mock();provider.plan.return_value=[]
        transport_service.plan(Mock(),dict(body,location_consent=True),provider)
        self.assertEqual(here.call_count,2)
        self.assertEqual(provider.plan.call_args.args[:2],((53.4,-3.0),(53.4,-3.0)))
