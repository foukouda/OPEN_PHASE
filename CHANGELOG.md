# Changelog

All notable changes to this board are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [Semantic Versioning](https://semver.org/) (tag `X.Y.Z`, no `v` prefix).
Keep entries short: the `[Unreleased]` section is printed on the schematic Revision History page.

## [Unreleased]

### Added

-   3x PBV 1 mOhm shunt + INA241A2 (20 V/V)
-   3x phase voltage divider 40.2k / 10k
-   AD7606C-18 ADC, 6 inputs used
-   +3.3V -> LT8362 6 V -> LT3045-1 +5VA / +2.5VA
-   Self-contained libs and 3D models (lib/)
-   LTspice simulations (Simulation/LTspice)
-   Predicted measurement quality (sim 07, 08)

### Changed

-   Renamed to OPEN_PHASE, KiCad 10
-   Sheets named after their function
-   IC3: LTC6655LN-2.5 -> LTC6655-2.5 (pin 6 = VOUT_S)
-   R12: 49.9k -> 24.9k (+2.5VA = 2.500 V)
