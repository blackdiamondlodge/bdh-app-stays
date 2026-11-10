from datetime import datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from bdh_sdk import INFO, ON, WARN, Reading, Stay
from stays import card, homepage

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

    def test_owner_visit(self, get):
        get.return_value = _state("Owner visit", guest="Owner visit", owner=True)
        self.assertEqual(homepage.current_stay(), Stay("Owner visit", owner=True))


def _states(**overrides):
    base = {
        "sensor.bdl_stay_current": ("none", {}),
        "sensor.bdl_stay_next": ("none", {}),
        "sensor.bdl_modes_status": ("done", {"kind": "vacation", "issues": []}),
        "input_select.bdl_occupancy": ("away", {}),
        "sensor.hot_tub_current_temperature": ("38.6", {"unit_of_measurement": "°C"}),
        "sensor.main_floor_temperature": ("57.2", {"unit_of_measurement": "°F"}),
        "sensor.kitchen_bdl_temperature": ("18", {"unit_of_measurement": "°C"}),
        "sensor.outside_temperature": ("-5", {"unit_of_measurement": "°C"}),
    }
    base.update(overrides)
    return [{"entity_id": e, "state": s, "attributes": a} for e, (s, a) in base.items()]


@patch("stays.card.get_all_states")
class LodgeCardTests(SimpleTestCase):
    # The hub runs in UTC; times are shown in the stay's own offset.
    def _soon(self, **delta):
        return (datetime.now(LODGE) + timedelta(**delta)).isoformat()

    def _tomorrow_4pm(self):
        return datetime.combine(datetime.now(LODGE).date() + timedelta(days=1), time(16),
                                tzinfo=LODGE).isoformat()

    def test_vacation_mode_with_next_arrival_and_readings(self, get):
        get.return_value = _states(**{"sensor.bdl_stay_next": (
            "The Smiths", {"guest": "The Smiths", "arrival": "2027-01-04T16:00:00-07:00"})})
        c = card.lodge_card()
        self.assertEqual(c.title, "Vacation mode")
        self.assertEqual(c.detail, "Next: The Smiths, Mon Jan 4, 4 PM")
        # The main floor thermostat (57.2 F), not the in-floor sensors.
        self.assertEqual(c.readings, (Reading("Inside", 14.0, "C"),
                                      Reading("Hot tub", 38.6, "C")))
        self.assertEqual((c.alerts, c.level, c.url_name), ((), INFO, "vacation_mode"))

    def test_unreadable_thermostat_leaves_out_inside(self, get):
        get.return_value = _states(**{"sensor.main_floor_temperature": ("unavailable", {})})
        self.assertEqual(card.lodge_card().readings, (Reading("Hot tub", 38.6, "C"),))

    def test_lodge_empty_without_stays(self, get):
        get.return_value = _states(**{"input_select.bdl_occupancy": ("home", {})})
        c = card.lodge_card()
        self.assertEqual((c.title, c.detail), ("Lodge empty", "No upcoming stays"))

    def test_preheating(self, get):
        get.return_value = _states(**{
            "input_select.bdl_occupancy": ("preheat", {}),
            "sensor.bdl_stay_next": ("Owner visit", {
                "guest": "Owner visit", "owner": True, "arrival": self._tomorrow_4pm()}),
        })
        c = card.lodge_card()
        self.assertEqual((c.title, c.level), ("Preheating for your visit", ON))
        self.assertEqual(c.detail, "Ready tomorrow, 4 PM")

    def test_guest_and_owner_stays(self, get):
        checkout = self._soon(minutes=1)
        get.return_value = _states(**{"sensor.bdl_stay_current": (
            "The Smiths", {"guest": "The Smiths", "checkout": checkout})})
        c = card.lodge_card()
        self.assertEqual(c.title, "Welcome, The Smiths")
        self.assertTrue(c.detail.startswith("Checkout "), c.detail)

        get.return_value = _states(**{"sensor.bdl_stay_current": (
            "Owner visit", {"guest": "Owner visit", "owner": True, "checkout": checkout})})
        c = card.lodge_card()
        self.assertEqual(c.title, "Welcome back")
        self.assertTrue(c.detail.startswith("Leaving "), c.detail)

    def test_unresolved_mode_issues_are_alerts(self, get):
        get.return_value = _states(**{"sensor.bdl_modes_status": (
            "failed", {"issues": ["Living room fireplace off"]})})
        c = card.lodge_card()
        self.assertEqual(c.alerts, ("Living room fireplace off: didn't complete",))
        self.assertEqual(c.level, WARN)


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
