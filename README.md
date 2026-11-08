# bdh-app-stays

Black Diamond Hub app that puts the homepage in **guest mode** while guests are
staying, and welcomes them by name with their checkout time.

It has no pages or tiles. Its `stay` hook reads the sensor published by the
Stays AppDaemon app (`appdaemon-bdl-stays`): `sensor.bdl_stay_current` is
`none` between stays and the guest's name during one, with `guest`,
`arrival` and `checkout` attributes. The hub only gets the name and times;
door PINs on the sensor are never passed on, because the homepage is a kiosk.

If Home Assistant can't be reached, or the sensor is `unknown`/`unavailable`
(e.g. AppDaemon hasn't republished it after an HA restart), the hook raises
and the hub keeps the last known stay until its checkout.

## Settings

| Setting | Default | |
|---|---|---|
| `BDH_STAYS_ENTITY` | `sensor.bdl_stay_current` | HA entity to read |

Home Assistant URL and token come from the hub (`HOMEASSISTANT_URL`,
`HOMEASSISTANT_ACCESS_TOKEN`).

## Install

Add the hashed line from the latest release to the site's `apps.txt` in
BlackDiamondHub. Requires a hub on bdh-sdk 0.3 or newer.

## Development

CI runs the tests inside the current BlackDiamondHub `main` using
`bdh-sdk`'s reusable `app-ci.yml`. Bump `version` in `pyproject.toml` and
merge to `main` to publish a release.
