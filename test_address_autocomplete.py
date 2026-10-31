import os
import unittest
from unittest.mock import patch

import app


class AddressAutocompleteTests(unittest.TestCase):
    def setUp(self):
        app.ADDRESS_CACHE.clear()

    def tearDown(self):
        app.ADDRESS_CACHE.clear()

    def test_uses_here_autosuggest_for_live_address_queries(self):
        payload = {
            "items": [
                {
                    "title": "10 Downing Street",
                    "address": {"label": "10 Downing Street, London SW1A 2AA", "postalCode": "SW1A 2AA", "countryCode": "GBR"},
                    "position": {"lat": 51.5034, "lng": -0.1276},
                },
                {"title": "Incomplete query", "resultType": "query"},
            ]
        }
        with patch.dict(os.environ, {"ALIGN_HERE_ROUTING_KEY": "test-key"}), patch.object(
            app.personal_planner, "here_fetch", return_value=payload
        ) as fetch:
            results = app.find_addresses("10 Downing Street")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["label"], "10 Downing Street, London SW1A 2AA")
        self.assertEqual(results[0]["postcode"], "SW1A 2AA")
        self.assertIn("autosuggest.search.hereapi.com/v1/autosuggest", fetch.call_args.args[0])

    def test_postcode_prefix_works_without_here_key(self):
        payload = {"result": [{"postcode": "L1 1AA", "admin_district": "Liverpool", "country": "England", "latitude": 53.4, "longitude": -2.9}]}
        with patch.dict(os.environ, {}, clear=True), patch.object(
            app.personal_planner, "fetch_json", return_value=payload
        ) as fetch:
            results = app.find_addresses("L1")
        self.assertEqual(results[0]["label"], "L1 1AA, Liverpool, England")
        self.assertIn("api.postcodes.io/postcodes?", fetch.call_args.args[0])

    def test_full_address_uses_photon_when_here_key_is_not_configured(self):
        payload = {
            "features": [{
                "properties": {
                    "housenumber": "10", "street": "Downing Street", "postcode": "SW1A 2AA",
                    "city": "London", "country": "United Kingdom", "countrycode": "gb",
                },
                "geometry": {"coordinates": [-0.1276, 51.5034]},
            }]
        }
        with patch.dict(os.environ, {}, clear=True), patch.object(
            app.personal_planner, "fetch_json", return_value=payload
        ) as fetch:
            results = app.find_addresses("10 Downing Street")
        self.assertEqual(results[0]["label"], "10 Downing Street, SW1A 2AA, London")
        self.assertEqual((results[0]["latitude"], results[0]["longitude"]), (51.5034, -0.1276))
        self.assertIn("photon.komoot.io/api?", fetch.call_args.args[0])


    def test_falls_back_to_nominatim_when_photon_is_unavailable(self):
        nominatim = [{
            "place_id": 123,
            "lat": "53.389",
            "lon": "-3.014",
            "name": "Arrowe Park Hospital",
            "address": {
                "house_number": "Arrowe Park",
                "road": "Arrowe Park Road",
                "postcode": "CH49 5PE",
                "town": "Upton",
            },
        }]
        with patch.dict(os.environ, {}, clear=True), patch.object(
            app.personal_planner, "fetch_json",
            side_effect=[ValueError("Photon unavailable"), nominatim],
        ) as fetch:
            results = app.find_addresses("Arrowe Park Road")
        self.assertEqual(results[0]["label"], "Arrowe Park Arrowe Park Road, CH49 5PE, Upton")
        self.assertEqual(results[0]["provider"], "OpenStreetMap Nominatim")
        self.assertEqual(results[0]["latitude"], 53.389)
        self.assertIn("nominatim.openstreetmap.org/search?", fetch.call_args.args[0])

    def test_postcode_provider_failure_falls_through_to_address_provider(self):
        photon = {"features": [{
            "properties": {
                "housenumber": "12", "street": "Example Street", "postcode": "CH43 2XX",
                "city": "Prenton", "country": "United Kingdom", "countrycode": "gb",
            },
            "geometry": {"coordinates": [-3.02, 53.39]},
        }]}
        with patch.dict(os.environ, {}, clear=True), patch.object(
            app.personal_planner, "fetch_json",
            side_effect=[ValueError("Postcodes.io unavailable"), photon],
        ) as fetch:
            results = app.find_addresses("CH43")
        self.assertEqual(results[0]["postcode"], "CH43 2XX")
        self.assertEqual(results[0]["provider"], "OpenStreetMap")
        self.assertEqual(fetch.call_count, 2)



if __name__ == "__main__":
    unittest.main()
