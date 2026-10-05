<p align="center" width="100%">
  <img alt="Logo" width="33%" src="Logos/LOGO.png">
</p>

<h1 align="center">${PROJECT_NAME} – ${BOARD_NAME}</h1>

<p align="center">
  3-phase inline current and voltage sensing PCB for BLDC drone motors (INA241A2 + AD7606C-18)
</p>

<p align="center">
  Sub-project of <a href="https://opentruslab.vercel.app/">OPEN THRUST LAB</a>
</p>

<p align="center" width="100%">
  <a href="https://github.com/foukouda/PhaseSense-8586/actions/workflows/ci.yaml">
    <img alt="CI" src="https://github.com/foukouda/PhaseSense-8586/actions/workflows/ci.yaml/badge.svg?branch=dev">
  </a>
  <a href="LICENSE">
    <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue">
  </a>
  <img alt="KiCad 10" src="https://img.shields.io/badge/KiCad-10-brightgreen">
  <img alt="Status" src="https://img.shields.io/badge/Status-Work%20in%20progress-orange">
</p>

<p align="center">
  <img alt="3D Top Angled" src="${png_3d_viewer_angled_top_outpath}" width="45%">
&nbsp; &nbsp; &nbsp; &nbsp;
  <img alt="3D Bottom Angled" src="${png_3d_viewer_angled_bottom_outpath}" width="45%">
</p>

***

## OVERVIEW

**${PROJECT_NAME}** is an open-hardware measurement board developed as part of **OPEN THRUST LAB**, a community-driven project building open-source test benches for drone motor characterization.

The board is inserted between the ESC and a 3-phase BLDC motor (two Amass **MR60PW** connectors). On each phase it measures:

- the **phase current**, with a 1 mΩ four-terminal shunt (Isabellenhütte PBV-R001) and a **TI INA241A2** current-sense amplifier (20 V/V, enhanced PWM rejection, bidirectional around a 2.5 V reference);
- the **phase voltage**, with a 40.2 kΩ / 10 kΩ divider.

The six signals are sampled **simultaneously** by an **Analog Devices AD7606C-18** (8 channels, 18 bits, 1 MSPS), so that power, efficiency and ESC behaviour can be computed from time-aligned Va/Vb/Vc and Ia/Ib/Ic.

The board only needs **3.3 V**. An LT8362 boost converter (2 MHz) makes 6 V, and two LT3045-1 ultralow-noise LDOs make the analog rails. Each LDO has its SET pin driven by an LTC6655 precision reference, so the LDO works as a low-noise buffer for the reference: **+5VA** (ADC and amplifier supply) and **+2.5VA** (ADC reference and amplifier zero-current level).

> The project name comes from the first version of the design (INA240 + ADS8586S). The schematic now uses the **INA241A2** and the **AD7606C-18**; everything in this README is taken from the current netlist.

***

## STATUS

This revision is **not ready for fabrication**. What is in the repository today:

| Area | State |
| --- | --- |
| Analog front-end (shunts, INA241A2, dividers, input filters) | Drawn and routed |
| AD7606C-18 supply, reference and analog inputs | Drawn and routed |
| AD7606C-18 digital interface (CONVST, BUSY, CS, SCLK, DOUTx, RESET, OS, RANGE, PAR/SER, STBY, REF SELECT) | **Not connected**, there is no host connector yet |
| +3.3V input | **No connector** on the board yet |
| Power supply (LT8362, LTC6655, LT3045-1) | Drawn; the boost stage is **not placed** on the PCB (37 unrouted connections) |
| ERC / DRC | 43 ERC and 126 DRC violations, CI runs the `PRELIMINARY` variant (no ERC/DRC gate) |

See [DESIGN REVIEW](#design-review) for the points found while documenting and simulating the design.

***

## SPECIFICATIONS

### Electrical specifications

| Parameter | Value |
| --- | --- |
| Input voltage | 3.3 V (LT8362 input range starts at 2.8 V) |
| Boost output — LT8362 | 5.98 V, 2 MHz (RT = 20 kΩ), FBX divider R5/R6 = 1 MΩ / 365 kΩ |
| Analog supply +5VA | 5.000 V — LTC6655-5 (IC7) driving the SET pin of an LT3045-1 (IC8) through R8 = 1 kΩ |
| Reference rail +2.5VA | 2.5 V nominal — LTC6655LN-2.5 (IC3) and LT3045-1 (IC9), see [DESIGN REVIEW](#design-review) |
| Digital supply (AD7606C VDRIVE) | 3.3 V, from the host |
| ADC | AD7606C-18, 8-channel simultaneous sampling, 18 bits, 1 MSPS, external reference on REFIN/REFOUT |
| Current sensing | 3 × PBV-R001 1 mΩ shunt + INA241A2 (20 V/V): **20 mV/A**, zero current = 2.5 V |
| Current range | ±35 A continuous (MR60PW rating) = 2.5 V ± 0.7 V; the amplifier output swing allows about ±115 A |
| Voltage sensing | 3 × divider 40.2 kΩ / 10 kΩ: 0.1992 V/V unloaded, **0.1977 V/V** with the AD7606C input impedance |
| Voltage range | 50 V on a ±10 V ADC range (25.2 V for a 6S pack gives 4.98 V) |
| Current channel bandwidth | 17.5 kHz (R13 = 33 Ω, R15 = 9.1 kΩ, C25 = 1 nF) |
| Voltage channel bandwidth | 48.5 kHz (divider + Re2 = 1 kΩ, R19 = 9.1 kΩ, C31 = 180 pF) |
| Phase connectors | 2 × Amass MR60PW (J1 = IN-A/B/C, J2 = OUT-A/B/C), 35 A |

### ADC channel assignment

| AD7606C input | Signal | Source |
| --- | --- | --- |
| V1 | Phase C voltage | OUT-C, R35 / R36, Re3, C34, R22 |
| V2 | Phase C current | R7 shunt, IC6, R21, C33, R18 |
| V3 | Phase B voltage | OUT-B, R31 / R32, Re1, C32, R20 |
| V4 | Phase B current | R4 shunt, IC4, R17, C29, R16 |
| V5 | Phase A voltage | OUT-A, R27 / R28, Re2, C31, R19 |
| V6 | Phase A current | R1 shunt, IC2, R13, C25, R15 |
| V7, V8 | Not used | Open (the datasheet asks to tie unused inputs to AGND) |

Current sign: IN+ of each INA241 is on the J2 side of the shunt, so a current flowing **from J1 to J2 lowers** the output: `V = 2.5 V − 20 mV/A × I(J1→J2)`. The phase voltage is measured on the J2 side of the shunt.

### Power budget

Power chain: **+3.3 V (host) → LT8362 → +6 V → LTC6655 + LT3045-1 → +5VA / +2.5VA**

| Load | Rail | Typical current |
| --- | --- | --- |
| AD7606C-18 AVCC (datasheet: 8.5 mA at 10 kSPS, 45 mA at 1 MSPS) | +5VA | 8.5 – 45 mA |
| 3 × INA241A2 (2.5 mA each) | +5VA | 7.5 mA |
| 2 × LTC6655 (5 mA each) and 2 × LT3045-1 | +6V | ≈ 13 mA |
| **Total on +6V** (simulated, 1 MSPS) | **+6V** | **65 mA** |
| AD7606C-18 VDRIVE | +3.3V | < 2 mA |
| **Board total** (simulated, 1 MSPS) | **+3.3V** | **≈ 130 mA (0.43 W)** |

### Physical specifications

| Parameter | Value |
| --- | --- |
| Project name | ${PROJECT_NAME} |
| Board name | ${BOARD_NAME} |
| Parent project | OPEN THRUST LAB |
| CAD tool | KiCad 10 |
| Automation tooling | KiBot + GitHub Actions |
| Dimensions | ${bb_w_mm} × ${bb_h_mm} mm |
| Stackup | 4 layers, 1.66 mm, 70 µm outer copper, ENIG |
| Mounting holes | 4 × M3, connected to GND |

***

## SCHEMATIC ARCHITECTURE

Five functional hierarchical sheets (under `Project Architecture`), plus the documentation sheets (Block Diagram, Power - Sequencing, Revision History):

| Sheet (file) | Description |
| --- | --- |
| `AD7606C-18_ADC` (`AD7606C-18 - ADC.kicad_sch`) | AD7606C-18 (IC1). AVCC = +5VA (C20, C35, C38), VDRIVE = +3.3V (C21), REFIN/REFOUT = +2.5VA (C41), REFCAPA/REFCAPB joined on C39 (10 µF), REGCAP pins on C36 / C37 (1 µF each). Six analog input pairs come from the INA241 sheet through global labels. |
| `INA241_Phase_Sense` (`INA241 - Phase Sensing.kicad_sch`) | Three identical phases. Shunt R1 / R4 / R7 with Kelvin connection to IC2 / IC4 / IC6 (INA241A2, VS = +5VA, REF1 = REF2 = +2.5VA), output filter 33 Ω + 1 nF. Voltage divider 40.2 kΩ / 10 kΩ, 1 kΩ + 180 pF. 9.1 kΩ return resistor on every negative ADC input. |
| `Connectors` (`Connectors.kicad_sch`) | J1 and J2, Amass MR60PW. Pins 1–3 = phases, mounting pins 4–5 = GND. |
| `Holes, Fiducials` (`Holes - Fiducials.kicad_sch`) | Four M3 mounting holes H1–H4 connected to GND. |
| `Power_Supply` (`Power Supply - Analog Rails.kicad_sch`) | LT8362 boost (IC5, L1 = 2.2 µH, D2 = PMEG2020EH, 2 MHz, pulse-skipping, soft-start C24 = 10 nF). LTC6655-5 (IC7) and LTC6655LN-2.5 (IC3) references, each driving the SET pin of an LT3045-1 (IC8 / IC9) through 1 kΩ with 10 µF on SET. PGFB tied to IN (no Power-Good, no fast start-up), ILIM to GND, VIOC open. |

***

## DESIGN REVIEW

Points found while checking the documentation against the netlist and the datasheets, and while simulating the design. None of them has been changed in the schematic: they are design decisions to take.

| # | Finding | Evidence | Suggested action |
| --- | --- | --- | --- |
| 1 | **LTC6655LN-2.5 (IC3): pin 6 is NR, and it is tied to VOUT (pin 7).** On the standard LTC6655 pin 6 is VOUT_S and must be tied to VOUT_F, which is how IC7 is wired. On the LN version the datasheet says: *"NR (Pin 6): Noise Reduction Pin. To band limit noise, connect a capacitor between this pin and ground"*, and gives its nominal voltage as 1.000 V (an internal node ahead of the output buffer). | Netlist: `Net-(IC3-NR)` = IC3.6, IC3.7, C12, R11. With the ADI model the reference then gives 2.02 V instead of 2.500 V (simulation 02, run 1). The model does not reproduce the NR node faithfully, so the exact value on a real board is unknown; the connection itself is not allowed by the datasheet. | Separate pin 6 from pin 7. Put the noise-reduction capacitor from pin 6 to GND and keep C12 on VOUT, or fit an LTC6655-2.5 (non-LN) on the unchanged footprint. |
| 2 | **R12 = 49.9 kΩ on the SET pin of IC9 gives 2.549 V, not 2.500 V.** The LT3045-1 sources 100 µA from SET: with 49.9 kΩ the pin wants 4.99 V, the 2.5 V reference holds it through R11 = 1 kΩ and sinks 49 µA, which leaves 49 mV across R11. | Simulation 02, run 2: +2.5VA = 2.549 V (+1.96 %). The AD7606C external reference input is specified from 2.495 V to 2.505 V. | R12 = 24.9 kΩ (100 µA × 24.9 kΩ = 2.49 V): simulation 02, run 3 gives 2.4996 V. R14 = 49.9 kΩ is already right for the 5 V rail (4.9998 V). |
| 3 | **The AD7606C-18 has no digital interface and the board has no +3.3V input.** CONVST, BUSY, CS, RD/SCLK, DOUTA–D, FRSTDATA, RESET, OS0–2, RANGE, PAR/SER SEL, STBY, WR and REF SELECT are open. | Netlist: 36 `unconnected-(IC1-…)` nets; J1 / J2 only carry the phases and GND. | Add the host connector and strap the mode pins (REF SELECT low for the external reference, PAR/SER SEL high for serial). |
| 4 | **AD7606C-18 pins left open that the datasheet asks to connect**: AGND pin 26 and REFGND pin 46 (*"All six of the AGND pins must connect to the AGND plane"*), unused inputs V7± / V8± (*"Connect all unused analog input channels to AGND"*). | Netlist: `unconnected-(IC1-AGND_2-Pad26)`, `…REFGND_2-Pad46`, `…V7+`, `…V8-`. | Connect them to GND. |
| 5 | **INA241A2 pin 4 (NC) is open** on IC2, IC4 and IC6. The datasheet pin table says: *"NC — Reserved. Connect to ground."* | Netlist: `unconnected-(IC2-NC-Pad4)` and the same for IC4, IC6. | Connect pin 4 to GND. |
| 6 | **The INA241A2 gain is 20 V/V.** The schematic note listed the INA240 gains (A2 = 50 V/V). With 1 mΩ the scale is 20 mV/A: 35 A only uses ±0.7 V of the ±2.5 V available. | TI datasheet SBOSA30D: A1 = 10, A2 = 20, A3 = 50, A4 = 100, A5 = 200 V/V. The note is corrected in the schematic. | Keep 20 V/V (±115 A range) or fit an INA241A3 (50 V/V, ±46 A) for more resolution. |
| 7 | **Current channels: the 9.1 kΩ return resistor creates a 15 mV offset.** The AD7606C inputs are 1.2 MΩ to an internal 2 V node. On the voltage channels both inputs see about 9 kΩ, so the two bias drops cancel (−0.15 mV). On the current channels the positive input sees 33 Ω and the negative one 9.1 kΩ: V− sits at +15 mV. | Simulation 06: 2.4849 V at zero current instead of 2.5000 V, which reads as −0.75 A. | Constant offset: remove it with a zero-current calibration. Do not shrink R15 / R16 / R18 without recomputing the filter: C25 is differential, so they set the 17.5 kHz corner. |
| 8 | **Voltage channels: −0.75 % gain error** from the 9 kΩ source impedance into the 1.2 MΩ input (−0.9 % at the 1 MΩ minimum). | Simulation 05: 0.1977 V/V instead of 0.1992 V/V. | Calibrate, or use the AD7606C per-channel gain register (software mode, 9 kΩ). |
| 9 | **PCB not finished**: IC5, L1 and the boost passives are outside the board outline, C16 has no schematic symbol, C14 / C15 / C39 use a 4-pin capacitor symbol on a 2-pad footprint. | DRC: 37 unconnected items, 20 schematic parity warnings. | Place and route the boost stage; align symbol and footprint of the 4-terminal capacitors. |

***

## SIMULATION (LTspice)

The power chain and the two measurement channels are simulated with **LTspice 26** in [`Simulation/LTspice/`](Simulation/LTspice). Every component value comes from the KiCad netlist and keeps its reference designator, so the simulation schematics can be read side by side with the KiCad sheets.

| File | Analysis | What it checks |
| --- | --- | --- |
| `01_Power_Chain_Startup.asc` | `.tran` 12 ms, switching | +3.3V → LT8362 → +6V → LT3045-1 soft-start, inrush and inductor current (board as built) |
| `02_Analog_Rails_Startup.asc` | `.tran` 150 ms, 3 runs | Settling and accuracy of +5VA and +2.5VA: as built, NR pin freed, NR freed + R12 = 24.9 kΩ |
| `03_Boost_Ripple.asc` | `.tran` 6 ms, switching | LT8362 steady-state ripple on +6V with the simulated load of both rails |
| `04_Analog_Rails_PSRR.asc` | `.ac` 10 Hz – 10 MHz | Rejection from +6V to +5VA and +2.5VA (reference + LDO, board capacitors) |
| `05_Measurement_Channels_AC.asc` | `.ac` 10 Hz – 10 MHz | Gain and bandwidth of the current and voltage channels, down to the ADC pins |
| `06_Measurement_Channels_Step.asc` | `.tran` 600 µs | DC transfer, offsets and settling for a 25.2 V and a 35 A step |

**Models**

- **LT8362, LT3045-1, LTC6655-5, LTC6655LN-2.5**: official Analog Devices models shipped with LTspice.
- **INA241A2**: TI does not provide an LTspice model, so `INA241A2_behav.sub` / `.asy` is a **behavioral model** written for this project from the datasheet (SBOSA30D): gain 20 V/V around (REF1 + REF2) / 2, 1.1 MHz bandwidth, 8 V/µs slew rate, output swing, 2.5 mA supply current, 35 µA input bias. It does not model offset, noise, CMRR or the 1 µs output hold of the enhanced PWM rejection.
- **AD7606C-18**: loads only. AVCC and VDRIVE are current sources (45 mA and 1.8 mA, the 1 MSPS figures). Each analog input is 1.2 MΩ to an internal 2 V node plus 5 pF, from the datasheet (*"Analog Input Current = (VIN − 2)/RIN"*).
- **D2**: PMEG2020EH modelled with the LTspice PMEG2020AEA (same 20 V / 2 A Nexperia MEGA Schottky family). **L1**: 2.2 µH, 3.2 mΩ.
- Ceramic capacitors use their nominal value (no DC-bias derating).

**Results**

| Quantity | Simulated | Notes |
| --- | --- | --- |
| +6V output (LT8362) | 5.96 V | 1.6 V × (1 + 1 MΩ / 365 kΩ) = 5.98 V |
| +6V reaches 90 % | 0.87 ms | 5.9 V after 1.0 ms, 6.04 V overshoot |
| Inrush in L1 / D2 when +3.3V is applied | 3.1 A peak | the 31 µF on +6V charge to VIN through L1 and D2; depends on the rise time of the host rail (100 µs assumed) |
| Peak inductor current during soft-start / steady state | 0.98 A / 0.30 A | L1 saturates at 20.7 A, LT8362 switch limit 2 A min |
| +6V ripple, 20 MHz bandwidth | 0.92 mV pp | discontinuous conduction, 65 mA load |
| Current drawn from +3.3V | 129 mA | AD7606C at 1 MSPS |
| +5VA | 4.9998 V | reference 5.0000 V; 100 µA × R14 = 4.99 V, almost no current in R8 |
| +5VA within 1 % / 0.1 % | 48 ms / 71 ms | τ = (R8 ∥ R14) × C13 = 9.8 ms; PGFB = IN disables the LT3045-1 fast start-up |
| +2.5VA as built | 2.08 V | NR tied to VOUT, see [DESIGN REVIEW](#design-review) 1 (model value, not reliable) |
| +2.5VA with NR freed, R12 = 49.9 kΩ | 2.549 V | [DESIGN REVIEW](#design-review) 2 |
| +2.5VA with NR freed, R12 = 24.9 kΩ | 2.4996 V | inside the 2.495 – 2.505 V window of the AD7606C |
| PSRR +6V → +5VA | 85 dB at 1 kHz, 77 dB at 2 MHz | ideal layout |
| PSRR +6V → +2.5VA (corrected rail) | 85 dB at 1 kHz, 94 dB at 2 MHz | ideal layout |
| Boost ripple left on +5VA / +2.5VA | 0.13 µV pp / 0.02 µV pp | +6V ripple × PSRR at 2 MHz |
| Current channel gain | 20.00 mV/A | 1 mΩ × 20 V/V |
| Current channel −3 dB | 17.5 kHz | −4.6 dB at 24 kHz, −46 dB at 2 MHz |
| Current channel at 0 A / 35 A (J1→J2) | 2.4849 V / 1.7849 V | 15 mV offset from the ADC input bias in R15 |
| Current channel 1 % settling | 42 µs | |
| Voltage channel gain | 0.1977 V/V | 25.2 V reads 4.982 V |
| Voltage channel −3 dB | 48.5 kHz | −0.95 dB at 24 kHz, −32 dB at 2 MHz |
| Voltage channel 1 % settling | 15 µs | |

<p align="center">
  <img alt="Power chain start-up" src="Images/Simulation/sim01_power_startup.png" width="80%">
</p>
<p align="center">
  <img alt="Analog rails start-up and +2.5VA accuracy" src="Images/Simulation/sim02_analog_rails.png" width="90%">
</p>
<p align="center">
  <img alt="Boost ripple" src="Images/Simulation/sim03_ripple.png" width="80%">
</p>
<p align="center">
  <img alt="PSRR of the analog rails" src="Images/Simulation/sim04_psrr.png" width="80%">
</p>
<p align="center">
  <img alt="Measurement channels frequency response" src="Images/Simulation/sim05_channels_ac.png" width="80%">
</p>
<p align="center">
  <img alt="Measurement channels step response" src="Images/Simulation/sim06_channels_step.png" width="90%">
</p>

**Re-run the simulations** (Windows, LTspice installed in the default location):

```bash
cd Simulation/LTspice
python run_simulations.py            # runs LTspice in batch mode, redraws Images/Simulation/*.png and results.md
python run_simulations.py --no-run   # only redraw from the existing .raw files
python generate_asc.py               # rebuilds the .asc files (overwrites hand edits)
```

Or open any `.asc` in LTspice and press *Run*. Simulation 01 switches at 2 MHz for 12 ms and takes about 7 minutes; 03 takes about 2 minutes.

> The simulations validate the design intent (regulation, sequencing, filtering). They do not replace bench measurements: layout parasitics, capacitor DC-bias derating and the real PWM edges on the phases will change the figures. The steady-state ripple is simulated on the boost alone because the encrypted LDO and reference models cannot be started from a preset operating point; what is left on the analog rails is computed from the simulated PSRR. The PSRR of +2.5VA is given for the corrected rail.

***

## STARTUP SEQUENCE

After 3.3 V is applied (values from the [LTspice simulations](#simulation-ltspice)):

| Stage | Duration | Indicator |
| --- | --- | --- |
| Output capacitors charge to VIN through L1 / D2 | < 0.2 ms | +6V ≈ 3 V |
| LT8362 soft-start (C24 = 10 nF) | +6V at 90 % after 0.9 ms, 5.9 V after 1.0 ms | +6V = 5.96 V |
| LTC6655 references charge their 10 µF and the SET capacitors | 93 % after 3 ms | REF5 → 5 V |
| LT3045-1 outputs follow the SET pins (τ = 9.8 ms) | 1 % after 48 ms, 0.1 % after 71 ms | +5VA, +2.5VA |
| **Minimum delay before the first conversion** | **≥ 100 ms** | rails settled |

> The LT3045-1 Power-Good outputs are not used (PGFB tied to IN), so there is no hardware "rails ready" signal: use the delay.

***

## HOW TO USE

### Prerequisites

- **KiCad 10** (files are saved in KiCad 10 format and cannot be opened with KiCad 9 or earlier)
- Nothing else: every symbol, footprint and 3D model is in `lib/` and referenced relative to the project (`KIPRJMOD`, project-local `sym-lib-table` / `fp-lib-table`)
- **KiBot** for automated output generation, **Docker** recommended for local CI runs

### Generate outputs locally

```bash
./kibot_launch.sh               # default configuration
./kibot_launch.sh -v CHECKED    # specific variant
```

| Variant | Outputs | ERC/DRC | Typical use |
| --- | --- | --- | --- |
| `DRAFT` | Schematic only | — | Early design work |
| `PRELIMINARY` | Schematic + PCB | — | Layout iterations (current CI setting) |
| `CHECKED` | Full | ✓ enforced | Design review |
| `RELEASED` | Full | ✓ enforced | Tagged version releases |

***

## REPOSITORY CONTENT

| Content | Description |
| --- | --- |
| Schematic sources | KiCad hierarchical schematic, 10 sheets |
| PCB layout | KiCad 4-layer PCB |
| Libraries | `lib/` — every symbol, footprint and 3D model used on the board |
| Manufacturing, validation, 3D exports | Generated by the CI (KiBot) |
| Documentation sheets | Block diagram, architecture, power sequencing, revision history |
| CI resources | GitHub Actions workflow, KiBot YAML configuration |
| Simulation | LTspice simulations of the power chain and the measurement channels |

***

## DIRECTORY STRUCTURE

    .
    ├─ Computations       # Design notes and calculations
    ├─ HTML               # Generated HTML pages
    ├─ Images             # Pictures, renders
    │  └─ Simulation      # Figures drawn by Simulation/LTspice/run_simulations.py
    │
    ├─ kibot_resources    # External resources used by KiBot
    │  ├─ colors          # Color themes for KiCad outputs
    │  ├─ fonts           # Fonts used in generated documents
    │  ├─ scripts         # Helper scripts used with KiBot
    │  └─ templates       # Templates for KiBot reports (this README: readme.txt)
    │
    ├─ kibot_yaml         # KiBot YAML configuration files
    ├─ KiRI               # KiRI PCB diff viewer files
    │
    ├─ lib                # Project libraries (self-contained)
    │  ├─ lib_sym         # PhaseSense-8586.kicad_sym — every symbol used
    │  ├─ lib_fp          # PhaseSense-8586.pretty — every footprint used
    │  └─ 3d_models       # STEP models referenced by the footprints
    │
    ├─ Logos              # Project logos
    │
    ├─ Manufacturing
    │  ├─ Assembly        # BoM, position files, assembly notes
    │  └─ Fabrication     # Gerbers, drill tables, fabrication notes
    │
    ├─ Report             # ERC / DRC reports
    ├─ Schematic          # Exported schematic PDFs
    ├─ Simulation
    │  └─ LTspice         # LTspice schematics, INA241A2 behavioral model, run/plot scripts
    ├─ Templates          # Drawing sheets and title block templates
    └─ Testing
       └─ Testpoints      # Test point tables

***

## DEVELOPMENT WORKFLOW

This project uses a reproducible hardware workflow based on **KiCad 10**, **KiBot** and **GitHub Actions**.

The CI pipeline (`.github/workflows/ci.yaml`) runs KiBot on every push to `dev` or `main` and commits the generated outputs back ("Update Outputs" commits). **Always `git pull` after the CI has run, before editing the project again**, otherwise the regenerated files (`.kicad_pro`, BoM, netlist, README…) will conflict.

> ℹ️ `README.md` is **generated** by KiBot from `kibot_resources/templates/readme.txt`. Edit the template, not `README.md`, or your changes will be overwritten by the next CI run.

**Branch convention:** `dev` is the development branch; `main` only receives merges from `dev` and carries the release tags.

**Project metadata** (project name, board name, company, designer, logo, repository URL) is defined once in `kibot_yaml/kibot_main.yaml` (`definitions:` section) and propagated to title blocks, documents and this README.

**Release a new hardware revision:**

1. On `dev`, fill the `[Unreleased]` section of [CHANGELOG.md](CHANGELOG.md).
2. Switch `kibot_variant` to `CHECKED` in `ci.yaml` once ERC and DRC are clean.
3. Merge `dev` into `main`: `git checkout main && git pull && git merge dev && git push`
4. Tag with a plain semantic version (**no `v` prefix**): `git tag 1.0.0 && git push origin 1.0.0`
5. Re-sync `dev`: `git checkout dev && git merge main`

***

## CHANGELOG

See [CHANGELOG.md](CHANGELOG.md) (Keep a Changelog format, semantic versioning).

***

## LICENSE

See [LICENSE](LICENSE) (MIT).
