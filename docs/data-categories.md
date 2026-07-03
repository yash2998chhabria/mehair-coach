# Data Categories

The first sync pass focuses on Fitbit-device-relevant Google Health data. Food/nutrition is excluded.

## Queried Data Types

- `steps`
- `heart-rate`
- `sleep`
- `exercise`
- `active-minutes`
- `active-zone-minutes`
- `active-energy-burned`
- `activity-level`
- `distance`
- `heart-rate-variability`
- `oxygen-saturation`
- `respiratory-rate-sleep-summary`
- `sedentary-period`
- `swim-lengths-data`
- `time-in-heart-rate-zone`
- `daily-heart-rate-variability`
- `daily-resting-heart-rate`
- `daily-oxygen-saturation`
- `daily-respiratory-rate`
- `daily-sleep-temperature-derivations`
- `daily-vo2-max`
- `calories-in-heart-rate-zone`
- `total-calories`
- `floors`

## Why No Food

Food records live under Google Health nutrition scopes. The current assistant is meant to start with data that can plausibly come from the wearable or Fitbit cloud sync, so nutrition is out of scope until the user explicitly wants food logging.
