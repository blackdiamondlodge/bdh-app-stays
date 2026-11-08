from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from bdh_sdk import Stay
from stays import homepage

LODGE = timezone(timedelta(hours=-7))


def _state(state, **attrs):
    return {"entity_id": "sensor.bdl_stay_current", "state": state, "attributes": attrs}


@patch("stays.homepage.get_entity_state")
class CurrentStayTests(SimpleTestCase):
    def test_stay_in_progress(self, get):
        get.return_value = _state(
            "The Smiths", guest="The Smiths", pin="1234",
            arrival="2026-11-07T16:00:00-07:00", checkout="2026-11-09T11:00:00-07:00",
        )
        stay = homepage.current_stay()
        self.assertEqual(stay, Stay(
            "The Smiths",
            datetime(2026, 11, 7, 16, tzinfo=LODGE),
            datetime(2026, 11, 9, 11, tzinfo=LODGE),
        ))
        get.assert_called_once_with("sensor.bdl_stay_current")

    def test_no_stay(self, get):
        get.return_value = _state("none", guest=None, arrival=None, checkout=None)
        self.assertIsNone(homepage.current_stay())

    def test_unreadable_sensor_raises_so_hub_keeps_last_stay(self, get):
        for value in (None, MagicMock(), _state("unavailable"), _state("unknown")):
            get.return_value = value
            with self.subTest(value), self.assertRaises(RuntimeError):
                homepage.current_stay()

    def test_bad_or_naive_dates_are_dropped(self, get):
        get.return_value = _state("Jo", arrival="soon", checkout="2026-11-09T11:00:00")
        self.assertEqual(homepage.current_stay(), Stay("Jo"))

    @override_settings(BDH_STAYS_ENTITY="sensor.other_stay")
    def test_entity_is_configurable(self, get):
        get.return_value = _state("none")
        homepage.current_stay()
        get.assert_called_once_with("sensor.other_stay")


class HubGuestModeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @patch("stays.homepage.get_entity_state")
    def test_hub_is_in_guest_mode_during_a_stay(self, get):
        checkout = (datetime.now(LODGE) + timedelta(days=1)).isoformat()
        get.return_value = _state("The Smiths", guest="The Smiths", checkout=checkout)
        self.assertEqual(self.client.get("/hub/api/status/").json()["mode"], "guest")

        cache.clear()
        get.return_value = _state("none")
        self.assertEqual(self.client.get("/hub/api/status/").json()["mode"], "dashboard")
