# Changelog

All notable changes to this board are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [Semantic Versioning](https://semver.org/) (tag `X.Y.Z`, no `v` prefix).
Keep entries short: the `[Unreleased]` section is printed on the schematic Revision History page.

## [Unreleased]

### Added

-   4x PBV 1 mOhm shunt + INA241A2 (20 V/V)
-   4x voltage divider 40.2k / 10k
-   AD7606C-18 ADC, 8 inputs used
-   +3.3V -> LT8362 6 V -> LT3045-1 +5VA / +2.5VA
-   Self-contained libs and 3D models (lib/)
-   LTspice simulations (Simulation/LTspice)
-   Predicted measurement quality (sim 07, 08)
-   openEMS shunt inductance model (Simulation/openEMS)
-   Thermal / current density model (Simulation/Thermal)
-   3D animation (Images/OPEN_PHASE.mp4)
-   J4 host header 2x8: AD7606C serial, software mode
-   Test points TP1-TP16
-   4x rail indicator LED (D1, D3-D5), about 1 mA each
-   Silkscreen: rail names at the LEDs, test point tags, OSHW logo
-   100 Ohm in series on the 11 J4 lines: RN1, RN2 (4x0603 array, as OPEN_WEIGHT), R39-R41, bottom side
-   100k pull-up on CS (R42), pull-downs on CONVST (R43) and RESET (R44)
-   Silkscreen: board version table (INA241 A5/A4/A3/A2: motor cells, mV/A, peak current), fitted version ticked
-   D6 PMEG2020EH (+3.3V -> +5VA): AVCC follows VDRIVE at power-up (AD7606C abs. max.)
-   Test points TP1, TP2, TP7, TP8, TP13, TP14 placed on the bottom, with tags
-   BOM: manufacturer part numbers on the 90 passives, diodes, LEDs and J4 (schematic and PCB fields)

### Changed

-   Renamed to OPEN_PHASE, KiCad 10
-   Sheets named after their function
-   IC3: LTC6655LN-2.5 -> LTC6655-2.5 (pin 6 = VOUT_S)
-   R12: 49.9k -> 24.9k (+2.5VA = 2.500 V)
-   L1: 744373965022 -> WE-MAPI 4030 74438357022 (4.1 x 4.1 mm)
-   Solder mask white, silkscreen black
-   Nets renamed SHUNT_*, INA_*, ADC_*
-   IC1 AGND pin 26, REFGND pin 46 to GND
-   IC8, IC9: thermal vias on exposed pad 13
-   Licence: MIT -> CERN-OHL-P v2
-   README / HTML logo: INGENIERIE FRANCE badge
-   TP15 / TP16 on the AD7606C side of the series resistors
-   Power planes IN/OUT U, V, W, B: 744 stitching vias removed
-   IC2, IC4, IC6, IC10: INA241A2 -> INA241A4 (100 V/V, 100 mV/A, ±23 A), version for 1205.5 motors on 1S
-   Courtyards to IPC-7351 level C (0.1 mm) on passives, LEDs, SOP/SON, LT8362, MAPI-4030, SOD-123F
-   LED footprint copied into the project library (lib/)
-   R1, R4, R7, R9: PBV-R001-F1-1.0 -> PBV-R001-F1-0.5 (shunt ±1 % -> ±0.5 %, as in simulation 08)
-   Simulations 05-08 rerun with the INA241A4 (100 V/V, 18 A test current, 1205.5 motor on 1S in sim 07)

### Fixed

-   +5VA via of R36 sat on the ADC_~{CS} track (short): bus rerouted around it
-   Rail LED anodes (D1, D3-D5) routed to R35-R38; PCB values of R35-R38 updated
-   ERC clean: PWR_FLAG on +6V, +5VA, +2.5VA, GND1; SS label on its net
-   C14, C15, C39 (4-terminal symbol): 0805 footprint with pads 3/4 on pads 2/1
-   IC5 pads 0.305 -> 0.30 mm wide (0.20 mm gap, ADI MSE16 land pattern)
-   INA241 pin 4 (NC) tied to GND, as the datasheet asks
-   DRC errors: IC10 track widths as on IC2/4/6, via spacing (LDO grids, +3.3V row, INA REF vias), GND vias off other nets and off the edge, dangling track and via removed
-   J1/J2 and J5 mounting pads reduced (0.3 mm from the board edge)
-   IC8/IC9 thermal vias tented on the bottom
-   Silkscreen kept off pads, gold bands and board edge (connector outlines, J4, IC5 reference, labels)
-   KiBot BoM read "Manufacturer Part Number", the symbols use "Manufacturer_Part_Number": the MPN columns were empty
-   lib/: IC1, J3, J4, J5 footprints saved from the board (silkscreen fixes), no more lib_footprint_mismatch
