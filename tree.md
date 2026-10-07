# Repository Structure

This overview records the paths relevant to the safety-alert maintenance work.
The existing component tree remains in custom_components/korea_incubator/tree.md.

```text
README.md
changelog.jsonl
caution.jsonl
tree.md
custom_components/
  korea_incubator/
    safety_alert/
      api.py
      device.py
      exceptions.py
      region_api.py
    sensor.py
    tree.md
  korea_safety/                 # Existing local standalone integration
    api.py
    device.py
    exceptions.py
    sensor.py
    ...
tests/
tools/
  test_safety_alert_fallback.py  # Offline emergency-page regression checks
  test_safety_alert_region.py
  test_safety_alert_options.py  # Offline existing-entry region options checks
```
