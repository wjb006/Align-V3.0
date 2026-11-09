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
        self.assertEqual(results[0]["label"], "Arrowe Park Hospital, Arrowe Park Arrowe Park Road, CH49 5PE, Upton")
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

    def test_here_deduplicates_nearby_labels_but_retains_distinct_places_and_cache(self):
        def item(label, lat, lng, identifier):
            return {"address": {"label": label}, "position": {"lat": lat, "lng": lng}, "id": identifier}

        payload = {"items": [
            item("Example Hospital, Example Road", 53.4, -3.0, "first"),
            item(" example  hospital, example road ", 53.4001, -3.0, "duplicate"),
            item("Example Clinic, Example Road", 53.4001, -3.0, "clinic"),
            item("Example Hospital, Example Road", 53.41, -3.0, "other"),
        ]}
        with patch.dict(os.environ, {"ALIGN_HERE_ROUTING_KEY": "test-key"}), patch.object(
            app.personal_planner, "here_fetch", return_value=payload
        ) as fetch:
            results = app.find_addresses("Example Hospital")
            cached = app.find_addresses("Example Hospital")
        self.assertEqual([item["place_id"] for item in results], ["first", "clinic", "other"])
        self.assertEqual(results[0]["latitude"], 53.4)
        self.assertEqual(cached, results)
        fetch.assert_called_once()

    def test_here_distinguishes_named_places_sharing_an_address(self):
        address = {"label": "Example Road, Example"}
        items = [{"title": name, "resultType": "place", "address": address,
                  "position": {"lat": 53.4, "lng": -3.0}, "id": name}
                 for name in ("Example Hospital", "Example Pharmacy")]
        with patch.dict(os.environ, {"ALIGN_HERE_ROUTING_KEY": "test-key"}), patch.object(
            app.personal_planner, "here_fetch", return_value={"items": items}
        ):
            results = app.find_addresses("Example")
        self.assertEqual([item["label"] for item in results], [
            "Example Hospital, Example Road, Example", "Example Pharmacy, Example Road, Example"
        ])

    def test_here_place_name_is_not_confused_with_part_of_a_street(self):
        address = {"label": "10 Park Road, London"}
        items = [
            {"title": "Park", "resultType": "place", "address": address,
             "position": {"lat": 51.5, "lng": -0.1}, "id": "place"},
            {"title": "10 Park Road", "resultType": "houseNumber", "address": address,
             "position": {"lat": 51.5, "lng": -0.1}, "id": "address"},
            {"title": "Park", "resultType": "place", "address": {"label": "Park, 10 Park Road, London"},
             "position": {"lat": 51.5, "lng": -0.1}, "id": "duplicate"},
        ]
        with patch.dict(os.environ, {"ALIGN_HERE_ROUTING_KEY": "test-key"}), patch.object(
            app.personal_planner, "here_fetch", return_value={"items": items}
        ):
            results = app.find_addresses("Park")
        self.assertEqual([(item["place_id"], item["label"]) for item in results], [
            ("place", "Park, 10 Park Road, London"), ("address", "10 Park Road, London")
        ])

    def test_photon_preserves_named_places_and_deduplicates_identical_nearby_results(self):
        def feature(name, lat, osm_id):
            return {"properties": {"name": name, "street": "Example Road", "postcode": "CH1 1AA",
                                   "city": "Example", "countrycode": "gb", "osm_id": osm_id},
                    "geometry": {"coordinates": [-3.0, lat]}}
        payload = {"features": [
            feature("Example Hospital", 53.4, 1),
            feature("Example Hospital", 53.4001, 2),
            feature("Example Pharmacy", 53.4001, 3),
        ]}
        with patch.dict(os.environ, {}, clear=True), patch.object(app.personal_planner, "fetch_json", return_value=payload):
            results = app.find_addresses("Example Hospital")
        self.assertEqual([item["label"] for item in results], [
            "Example Hospital, Example Road, CH1 1AA, Example",
            "Example Pharmacy, Example Road, CH1 1AA, Example",
        ])
        self.assertEqual([item["place_id"] for item in results], ["1", "3"])

    def test_nominatim_duplicate_results_are_removed(self):
        address = {"road": "Example Road", "postcode": "CH1 1AA", "town": "Example"}
        items = [{"name": "Example Hospital", "address": address, "place_id": num,
                  "lat": lat, "lon": "-3.0"} for num, lat in [(1, "53.4"), (2, "53.4001")]]
        with patch.dict(os.environ, {}, clear=True), patch.object(
            app.personal_planner, "fetch_json", side_effect=[ValueError("offline"), items]
        ):
            results = app.find_addresses("Example Hospital")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["place_id"], "1")

    def test_missing_coordinates_do_not_collapse_ambiguous_results(self):
        results = [{"label": "Example", "latitude": "", "longitude": ""},
                   {"label": "Example", "latitude": "", "longitude": ""}]
        self.assertEqual(app.deduplicate(results), results)



if __name__ == "__main__":
    unittest.main()
