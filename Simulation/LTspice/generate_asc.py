# Generates the PhaseSense-8586 LTspice schematics (.asc) as properly wired circuits.
# WARNING: running it overwrites the .asc files in this folder (hand edits made
# in LTspice are lost). Reuse the Sch class / PINS table for other projects.
import os

OUT = os.path.dirname(os.path.abspath(__file__))

PINS = {  # R0 pin coordinates
    "res": {"A": (16, 16), "B": (16, 96)},
    "cap": {"A": (16, 0), "B": (16, 64)},
    "ind": {"A": (16, 16), "B": (16, 96)},
    "voltage": {"+": (0, 16), "-": (0, 96)},
    "current": {"+": (0, 0), "-": (0, 80)},
    "schottky": {"A": (16, 0), "K": (16, 64)},
    "LT8362": {"EN": (-160, -144), "MODE": (-160, -48), "RT": (-160, 48), "SS": (-160, 144),
               "VIN": (-80, -208), "SW": (80, -208), "INTVCC": (160, -144), "FBX": (160, -48),
               "VC": (160, 48), "BIAS": (160, 144), "GND": (0, 208)},
    "LT3045-1": {"IN": (-240, -144), "EN": (-240, -64), "VIOC": (-240, 16), "PG": (-240, 96),
                 "SET": (-128, 160), "GND": (0, 160), "ILIM": (96, 160), "PGFB": (224, 160),
                 "OUT": (304, 0), "OUTS": (304, 80)},
    "LTC6655-5": {"IN": (-144, -32), "SHDN": (-144, 32), "GND": (0, 64),
                  "OUT_F": (144, -32), "P6": (144, 32)},
    "LTC6655LN-2.5": {"IN": (-144, -32), "SHDN": (-144, 32), "GND": (0, 64),
                      "OUT_F": (144, -32), "P6": (144, 32)},
    "INA241A2_behav": {"IN+": (-128, -48), "IN-": (-128, 48), "REF1": (-64, 96), "REF2": (64, 96),
                       "VS": (0, -96), "GND": (0, 96), "OUT": (128, 0)},
}


def tf(rot, p):
    x, y = p
    return {"R0": (x, y), "R90": (-y, x), "R180": (-x, -y), "R270": (y, -x),
            "M0": (-x, y), "M180": (x, -y)}[rot]


WIN = {  # attribute windows for rotated two-pin parts (symbol frame)
    ("res", "R270"): ["WINDOW 0 32 56 VTop 2", "WINDOW 3 0 56 VBottom 2"],
    ("ind", "R270"): ["WINDOW 0 32 56 VTop 2", "WINDOW 3 4 56 VBottom 2"],
    ("schottky", "R270"): ["WINDOW 0 32 32 VTop 2", "WINDOW 3 0 32 VBottom 2"],
}


class Sch:
    def __init__(self, w, h):
        self.head = ["Version 4", f"SHEET 1 {w} {h}"]
        self.w, self.f, self.s, self.t = [], [], [], []

    def part(self, sym, pin, at, name, value=None, rot="R0", spiceline=None, value2=None,
             windows=None):
        """Place `sym` so that its pin `pin` lands on `at`; return all pin positions."""
        px, py = tf(rot, PINS[sym][pin])
        ox, oy = at[0] - px, at[1] - py
        s = [f"SYMBOL {sym} {ox} {oy} {rot}"]
        s += windows if windows is not None else WIN.get((sym, rot), [])
        s.append(f"SYMATTR InstName {name}")
        if value is not None:
            s.append(f"SYMATTR Value {value}")
        if value2:
            s.append(f"SYMATTR Value2 {value2}")
        if spiceline:
            s.append(f"SYMATTR SpiceLine {spiceline}")
        self.s += s
        return {k: (ox + tf(rot, v)[0], oy + tf(rot, v)[1]) for k, v in PINS[sym].items()}

    def wire(self, *pts):
        for a, b in zip(pts[:-1], pts[1:]):
            self.w.append(f"WIRE {a[0]} {a[1]} {b[0]} {b[1]}")

    def bus(self, y, xs):
        """Horizontal rail split at every tap so each tap is a real junction."""
        xs = sorted(set(xs))
        for a, b in zip(xs[:-1], xs[1:]):
            self.wire((a, y), (b, y))

    def gnd(self, p, drop=0):
        if drop:
            self.wire(p, (p[0], p[1] + drop))
            p = (p[0], p[1] + drop)
        self.f.append(f"FLAG {p[0]} {p[1]} 0")

    def label(self, p, name):
        self.f.append(f"FLAG {p[0]} {p[1]} {name}")

    def text(self, x, y, txt, size=2, directive=False):
        self.t.append(f"TEXT {x} {y} Left {size} {'!' if directive else ';'}{txt.replace(chr(10), chr(92) + 'n')}")

    def shunt_cap(self, x, y, name, value, spiceline=None):
        c = self.part("cap", "A", (x, y), name, value, spiceline=spiceline)
        self.gnd(c["B"])

    def save(self, fname):
        with open(os.path.join(OUT, fname), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(self.head + self.w + self.f + self.s + self.t) + "\n")


MODELS = (
    ".model PMEG2020AEA D(Is=5.409u Rs=.05676 N=1.02 Cjo=.1908n M=.4863 Eg=.69 Xti=2 BV=22 IBV=50u "
    "Vj=.3408 Iave=2 Vpk=20 mfg=NXP type=Schottky)"
)

# As-built values. Simulation 02 steps through the two corrections discussed in the README.
ASBUILT = ".param Rnr=1m R12v=49.9k Iavcc=45m"
CASES = (".step param run 1 3 1\n"
         ".param Rnr=table(run, 1,1m, 2,1G, 3,1G)\n"
         ".param R12v=table(run, 1,49.9k, 2,49.9k, 3,24.9k)\n"
         ".param Iavcc=45m")
CASES_NOTE = ("run 1 = as built : LTC6655LN pin 6 (NR) tied to pin 7 (VOUT), R12 = 49.9k\n"
              "run 2 = NR separated from VOUT, R12 = 49.9k\n"
              "run 3 = NR separated from VOUT, R12 = 24.9k (100 uA x 24.9k = 2.49 V, no current in R11)")


# ------------------------------------------------------------------ blocks
def boost(s, v1="PWL(0 0 100u 3.3)"):
    """LT8362 +3.3V -> +6V (sheet ALIMENTATION). +3.3V rail at y = 0, +6V rail from x = 1200."""
    Y = 0
    v = s.part("voltage", "+", (0, Y), "V1", v1, spiceline="Rser=20m",
               windows=["WINDOW 0 -104 48 Left 2", "WINDOW 3 -200 80 Left 1", "WINDOW 39 -200 104 Left 1"])
    s.gnd(v["-"])
    s.text(-200, 176, "Host +3.3V\n(no connector on the board yet)", 1)
    s.label((96, Y), "+3.3V")
    for x, n, val, sl in ((176, "C22", "4.7u", "Rser=5m"), (304, "C23", "0.1u", "Rser=20m"),
                          (432, "C21", "0.1u", "Rser=20m")):
        s.shunt_cap(x, Y, n, val, sl)
    i = s.part("current", "+", (560, Y), "I_VDRIVE", "1.8m")
    s.gnd(i["-"])
    s.text(416, 112, "C21 + I_VDRIVE =\nAD7606C VDRIVE (1 MSPS)", 1)
    # LT8362: VIN and SW pins come out of the top of the symbol
    ic = s.part("LT8362", "VIN", (912, 160), "IC5")
    s.wire(ic["VIN"], (912, Y))
    s.wire(ic["EN"], (752, 224), (752, Y))
    s.bus(Y, [0, 96, 176, 304, 432, 560, 752, 912, 944])
    l1 = s.part("ind", "A", (944, Y), "L1", "2.2u", rot="R270", spiceline="Rser=3.2m")
    s.text(912, -120, "WE-LHMI 744373965022", 1)
    s.wire(l1["B"], (1072, Y), (1136, Y))
    s.wire(ic["SW"], (1072, Y))
    s.label((1072, Y), "SW")
    d2 = s.part("schottky", "A", (1136, Y), "D2", "PMEG2020AEA", rot="R270")
    s.text(1112, -120, "PMEG2020EH", 1)
    s.text(600, 304, "SYNC/MODE open\n= pulse-skipping", 1)
    # RT, SS
    s.wire(ic["RT"], (704, 416))
    r2 = s.part("res", "A", (704, 416), "R2", "20k")
    s.gnd(r2["B"])
    s.wire(ic["SS"], (768, 512))
    c24 = s.part("cap", "A", (768, 512), "C24", "10n")
    s.gnd(c24["B"])
    s.label((768, 512), "SS")
    # INTVCC, VC compensation, BIAS
    s.wire(ic["INTVCC"], (1232, 224))
    c27 = s.part("cap", "A", (1232, 224), "C27", "1u")
    s.gnd(c27["B"])
    s.label((1232, 224), "INTVCC")
    s.wire(ic["VC"], (1232, 416))
    r3 = s.part("res", "A", (1232, 416), "R3", "36.5k")
    s.wire(r3["B"], (1232, 528))
    c26 = s.part("cap", "A", (1232, 528), "C26", "1n")
    s.gnd(c26["B"])
    s.label((1232, 416), "VC")
    s.label((1232, 528), "CC")
    s.wire(ic["BIAS"], (1184, 512), (1184, 544))
    s.gnd((1184, 544))
    s.gnd(ic["GND"], 32)
    # feedback divider + feed-forward capacitor
    r5 = s.part("res", "A", (1360, Y), "R5", "1Meg")
    r6 = s.part("res", "A", (1360, 176), "R6", "365k")
    s.wire(r5["B"], (1360, 128), r6["A"])
    s.gnd(r6["B"])
    s.wire(ic["FBX"], (1296, 320), (1296, 128), (1360, 128))
    s.label((1296, 128), "FBX")
    c28 = s.part("cap", "A", (1456, Y), "C28", "4.7p")
    s.wire(c28["B"], (1456, 128), (1360, 128))
    rail6 = [d2["K"][0], 1360, 1456]
    for x, n, val, sl in ((1584, "C30", "22u", "Rser=3m"), (1712, "C9", "4.7u", "Rser=5m"),
                          (1840, "C11", "4.7u", "Rser=5m")):
        s.shunt_cap(x, Y, n, val, sl)
        rail6.append(x)
    s.text(0, -240, "LT8362 BOOST  +3.3V -> +6V, 2 MHz   (schematic sheet ALIMENTATION)", 3)
    return rail6


def six_volt_source(s, value, value2=None, note="+6V (settled boost output)"):
    v = s.part("voltage", "+", (1840, 0), "V_6V", value, spiceline="Rser=10m", value2=value2,
               windows=["WINDOW 0 -104 48 Left 2", "WINDOW 3 -280 80 Left 1", "WINDOW 39 -280 104 Left 1",
                        "WINDOW 123 -280 128 Left 1"])
    s.gnd(v["-"])
    s.text(1560, 176, note, 1)
    return [1840]


def ref_ldo(s, y0, ref_sym, ref_name, ldo_name, r_ser, r_set, c_ref, c_set, lab_ref, lab_set,
            nr_link):
    """LTC6655 reference driving the SET pin of an LT3045-1 through 1 k. +6V rail at y = y0.

    Returns the x positions of the +6V taps and of the start of the output rail (y = y0 + 144)."""
    yr = y0 + 448
    ref = s.part(ref_sym, "IN", (2128, yr), ref_name,
                 windows=["WINDOW 0 -144 -88 Left 2", "WINDOW 3 -64 -88 Left 2"])
    s.wire(ref["IN"], (2080, yr), (2080, y0))
    s.wire(ref["SHDN"], (2080, yr + 64), (2080, yr))
    s.gnd(ref["GND"], 32)
    if nr_link:  # LTC6655LN: pin 6 is NR; on the board it is tied to pin 7
        rl = s.part("res", "A", (2432, yr + 64), "R_NR", "{Rnr}", rot="R270")
        s.wire(ref["P6"], rl["A"])
        s.wire(rl["B"], (2512, yr))
        s.text(2320, yr + 160, "R_NR = PCB link pin 6 (NR) - pin 7 (VOUT)\nas built: 1m  /  removed: 1G", 1)
    else:    # LTC6655: pin 6 is VOUT_S, Kelvin-tied to VOUT_F
        s.wire(ref["P6"], (2512, yr + 64), (2512, yr))
    s.bus(yr, [ref["OUT_F"][0], 2512, 2560, 2608, 2688])
    s.label((2560, yr), lab_ref)
    s.shunt_cap(2608, yr, c_ref, "10u", "Rser=5m")
    rs = s.part("res", "A", (2688, yr), r_ser[0], r_ser[1], rot="R270")
    rset = s.part("res", "A", (2848, yr), r_set[0], r_set[1])
    s.gnd(rset["B"])
    s.shunt_cap(2976, yr, c_set, "10u", "Rser=5m")
    s.bus(yr, [rs["B"][0], 2848, 2976, 3040, 3104])
    s.label((3040, yr), lab_set)
    ldo = s.part("LT3045-1", "IN", (2992, y0), ldo_name)
    s.wire(ldo["EN"], (2944, y0 + 80), (2944, y0))
    s.wire(ldo["SET"], (3104, yr))
    s.gnd(ldo["GND"], 32)
    s.gnd(ldo["ILIM"], 32)
    s.wire(ldo["PGFB"], (3456, y0 + 368))
    s.label((3456, y0 + 368), "+6V")
    s.text(3488, y0 + 344, "PGFB = IN : fast start-up and PG disabled\nVIOC, PG open", 1)
    s.wire(ldo["OUTS"], (3584, y0 + 224), (3584, y0 + 144))
    return [2080, 2944, 2992], [ldo["OUT"][0], 3584]


def analog_rails(s, rail6):
    """Both precision rails (sheet ALIMENTATION) and their loads."""
    # --- +5VA : IC7 LTC6655-5 -> R8 -> SET of IC8
    taps, rail5 = ref_ldo(s, 0, "LTC6655-5", "IC7", "IC8", ("R8", "1k"), ("R14", "49.9k"), "C8", "C13",
                          "REF5", "SET5", nr_link=False)
    s.bus(0, rail6 + [1968, 2016] + taps)
    s.label((1968, 0), "+6V")
    Y5 = 144
    s.label((3648, Y5), "+5VA")
    s.shunt_cap(3744, Y5, "C14", "10u", "Rser=5m")
    s.shunt_cap(3872, Y5, "C1", "0.1u", "m=6 Rser=20m")
    s.shunt_cap(4000, Y5, "C5", "1u", "m=3 Rser=10m")
    i = s.part("current", "+", (4128, Y5), "I_AVCC", "{Iavcc}")
    s.gnd(i["-"])
    i = s.part("current", "+", (4288, Y5), "I_INA", "7.5m")
    s.gnd(i["-"])
    s.bus(Y5, rail5 + [3648, 3744, 3872, 4000, 4128, 4288])
    s.text(3840, 256, "C1 (x6) = C1 C2 C17 C20 C35 C38\nC5 (x3) = C5 C10 C18", 1)
    s.text(4096, 256, "I_AVCC = AD7606C AVCC (1 MSPS)\nI_INA = 3 x INA241 IQ", 1)
    s.text(2080, -240, "+5VA : LTC6655-5 (IC7) reference buffered by LT3045-1 (IC8)", 3)
    # --- +2.5VA : IC3 LTC6655LN-2.5 -> R11 -> SET of IC9
    YB = 880
    taps, rail25 = ref_ldo(s, YB, "LTC6655LN-2.5", "IC3", "IC9", ("R11", "1k"), ("R12", "{R12v}"), "C12",
                           "C19", "REF2V5", "SET2V5", nr_link=True)
    s.wire((2016, 0), (2016, YB))
    s.bus(YB, [2016] + taps)
    Y25 = YB + 144
    s.label((3648, Y25), "+2.5VA")
    s.shunt_cap(3744, Y25, "C15", "10u", "Rser=5m")
    s.shunt_cap(3872, Y25, "C41", "0.1u", "Rser=20m")
    i = s.part("current", "+", (4000, Y25), "I_REF", "100u")
    s.gnd(i["-"])
    s.bus(Y25, rail25 + [3648, 3744, 3872, 4000])
    s.text(3840, Y25 + 112, "C41 = AD7606C REFIN/REFOUT\nI_REF = INA241 REF pins + REFIN (estimate)", 1)
    s.text(2080, YB - 112, "+2.5VA : LTC6655LN-2.5 (IC3) reference buffered by LT3045-1 (IC9)", 3)


def header(s, title, sub):
    s.text(0, -448, title, 4)
    s.text(0, -376, sub, 2)


SHEET = (4700, 1900)
DX, DY = 0, 760   # directives: free area under the boost stage

# ============================================================ 01 start-up
s = Sch(*SHEET)
header(s, "PhaseSense-8586 - 01 - Power chain start-up : +3.3V -> LT8362 -> +6V -> LT3045-1 -> +5VA / +2.5VA",
       "Switching simulation (2 MHz) of the boost soft-start, as built. Full settling of the analog rails: see 02_Analog_Rails_Startup.asc")
analog_rails(s, boost(s))
s.text(DX, DY, ".tran 0 12m 0 20n", 2, True)
s.text(DX, DY + 40, ASBUILT, 2, True)
s.text(DX, DY + 80, ".save V(+3.3V) V(+6V) V(+5VA) V(+2.5VA) V(SS) V(VC) V(SET5) V(SET2V5) V(REF5) V(REF2V5) I(L1) I(V1)", 2, True)
s.text(DX, DY + 120, ".meas tran V6_at_12ms AVG V(+6V) FROM 11m TO 12m\n.meas tran V6_max MAX V(+6V)\n"
                     ".meas tran T6_90 WHEN V(+6V)=5.37 RISE=1\n.meas tran IL_peak MAX I(L1)\n"
                     ".meas tran I3V3_inrush MIN I(V1)", 2, True)
s.text(DX, DY + 360, MODELS, 1, True)
s.save("01_Power_Chain_Startup.asc")

# ============================================================ 02 analog rails
s = Sch(*SHEET)
header(s, "PhaseSense-8586 - 02 - Analog rails start-up and accuracy : +5VA and +2.5VA",
       "The boost is replaced by its settled output (1 ms ramp, see 01). Three runs: the board as built and two corrections of the +2.5VA rail.")
r6 = six_volt_source(s, "PWL(0 0 1m 5.96)", note="+6V from the boost\n(1 ms ramp)")
analog_rails(s, r6)
s.text(DX, DY, ".tran 0 150m 0 20u", 2, True)
s.text(DX, DY + 40, CASES, 2, True)
s.text(DX, DY + 200, CASES_NOTE, 2)
s.text(DX, DY + 320, ".meas tran V5VA AVG V(+5VA) FROM 140m TO 150m\n.meas tran V2V5A AVG V(+2.5VA) FROM 140m TO 150m\n"
                     ".meas tran VREF5 AVG V(REF5) FROM 140m TO 150m\n.meas tran VREF2V5 AVG V(REF2V5) FROM 140m TO 150m\n"
                     ".meas tran I_R8 AVG I(R8) FROM 140m TO 150m\n.meas tran I_R11 AVG I(R11) FROM 140m TO 150m\n"
                     ".meas tran T5_99 WHEN V(+5VA)=4.95 RISE=1\n.meas tran T5_999 WHEN V(+5VA)=4.995 RISE=1\n"
                     ".meas tran I_6V AVG I(V_6V) FROM 140m TO 150m", 2, True)
s.save("02_Analog_Rails_Startup.asc")

# ============================================================ 03 boost ripple
# The encrypted LDO / reference models cannot be started from a preset operating point and need
# ~70 ms to settle, so the steady-state ripple is simulated on the boost alone, loaded by the
# input current of the analog rails (I_6V of simulation 02). What is left on +5VA / +2.5VA is
# obtained from the PSRR of simulation 04.
s = Sch(2700, 1500)
header(s, "PhaseSense-8586 - 03 - Steady-state ripple of the LT8362 boost on +6V",
       "Boost alone, loaded by the input current of both analog rails (AD7606C at 1 MSPS, see I_6V in 02). Measured over 5..6 ms.")
r6 = boost(s)
i = s.part("current", "+", (2096, 0), "I_6V", "PWL(0 0 2m 0 2.1m {I6})",
           windows=["WINDOW 0 24 16 Left 2", "WINDOW 3 24 44 Left 1"])
s.gnd(i["-"])
s.bus(0, r6 + [1968, 2096])
s.label((1968, 0), "+6V")
s.text(2120, 96, "I_6V = input current of both LT3045-1\nand both LTC6655 (simulation 02)", 1)
s.text(DX, DY, ".tran 0 6m 0 5n", 2, True)
s.text(DX, DY + 40, ".param I6=65.3m\n.options plotwinsize=0", 2, True)
s.text(DX, DY + 120, ".save V(+3.3V) V(+6V) V(SW) I(L1) I(V1) V(VC)", 2, True)
s.text(DX, DY + 160, ".meas tran V6_avg AVG V(+6V) FROM 5m TO 6m\n.meas tran V6_pp PP V(+6V) FROM 5m TO 6m\n"
                     ".meas tran I3V3 AVG I(V1) FROM 5m TO 6m\n.meas tran IL_pk MAX I(L1) FROM 5m TO 6m\n"
                     ".meas tran V3V3_pp PP V(+3.3V) FROM 5m TO 6m", 2, True)
s.text(DX, DY + 400, MODELS, 1, True)
s.save("03_Boost_Ripple.asc")

# ============================================================ 04 PSRR
s = Sch(*SHEET)
header(s, "PhaseSense-8586 - 04 - PSRR of the analog rails : transfer from +6V ripple to +5VA and +2.5VA",
       "PSRR(dB) = -20*log10|V(rail)/V(+6V)|. Includes the path through the LTC6655 references and the SET filters. 2 MHz = LT8362 switching frequency.")
r6 = six_volt_source(s, "5.96", value2="AC 1", note="+6V with\n1 V AC ripple")
analog_rails(s, r6)
s.text(DX, DY, ".ac dec 50 10 10Meg", 2, True)
s.text(DX, DY + 40, ".param Rnr=1G R12v=24.9k Iavcc=45m", 2, True)
s.text(DX, DY + 100, "Corrected +2.5VA rail (run 3 of 02): the as-built reference has no valid operating point.\n"
                     "+5VA is the same in both cases.", 2)
s.text(DX, DY + 260, ".meas ac PSRR5_1k FIND mag(V(+5VA)) AT 1k\n.meas ac PSRR5_100k FIND mag(V(+5VA)) AT 100k\n"
                     ".meas ac PSRR5_2M FIND mag(V(+5VA)) AT 2Meg\n.meas ac PSRR2V5_1k FIND mag(V(+2.5VA)) AT 1k\n"
                     ".meas ac PSRR2V5_100k FIND mag(V(+2.5VA)) AT 100k\n.meas ac PSRR2V5_2M FIND mag(V(+2.5VA)) AT 2Meg", 2, True)
s.save("04_Analog_Rails_PSRR.asc")


# ============================================================ 05 / 06 measurement channels
def adc_input(s, x, yp, yn, tag, name_p, name_n):
    """AD7606C-18 analog input pair: RIN to an internal 2 V node, CIN to AGND (datasheet)."""
    rp = s.part("res", "A", (x, yp), f"RIN_{tag}P", "1.2Meg", rot="R270")
    rn = s.part("res", "A", (x, yn), f"RIN_{tag}N", "1.2Meg", rot="R270")
    xb = rp["B"][0] + 64
    s.wire(rp["B"], (xb, yp), (xb, yn))
    s.wire(rn["B"], (xb, yn))
    vb = s.part("voltage", "+", (xb, yn), f"VB_{tag}", "2",
                windows=["WINDOW 0 24 56 Left 2", "WINDOW 3 24 84 Left 2"])
    s.gnd(vb["-"])
    s.shunt_cap(x - 144, yp, f"CIN_{tag}P", "5p")
    s.shunt_cap(x - 240, yn, f"CIN_{tag}N", "5p")
    s.label((x - 336, yp), name_p)
    s.label((x - 336, yn), name_n)
    s.text(x - 160, yp - 104, f"AD7606C-18 {name_p[:-1]}+ / {name_p[:-1]}- input pins\n"
                              "(RIN 1.2 Meg to an internal 2 V node, CIN 5 pF)", 1)
    return x - 336, x - 240, x - 144


def channels(s, vph, vph_ac, im, im_ac):
    """Phase A: shunt R1 + INA241A2 (IC2) -> V6, and divider R27/R28 -> V5 (sheets INA241 and AD7606C)."""
    # --- phase conductor J1 -> shunt -> J2
    v = s.part("voltage", "+", (0, 0), "V_PH", vph, value2=vph_ac,
               windows=["WINDOW 0 -112 40 Left 2", "WINDOW 3 -232 88 Left 1", "WINDOW 123 -232 112 Left 1"])
    s.gnd(v["-"])
    s.text(-232, 152, "ESC phase A\n(J1 pin 1)", 1)
    r1 = s.part("res", "A", (160, 0), "R1", "1m", rot="R270")
    i = s.part("current", "+", (304, 0), "I_M", im, value2=im_ac,
               windows=["WINDOW 0 24 16 Left 2", "WINDOW 3 24 44 Left 1", "WINDOW 123 24 68 Left 1"])
    s.gnd(i["-"])
    s.text(336, -88, "I_M = motor phase current (J2 pin 3)", 1)
    s.bus(0, [0, 96, 160])
    s.bus(0, [r1["B"][0], 304, 720])
    s.label((96, 0), "IN-A")
    s.label((720, 0), "OUT-A")
    s.text(144, -88, "PBV-R001 shunt", 1)
    # --- INA241A2, Kelvin connection
    u = s.part("INA241A2_behav", "IN+", (384, 256), "IC2")
    s.wire((240, 0), (240, 256), u["IN+"])
    s.wire((160, 0), (160, 352), u["IN-"])
    s.wire(u["VS"], (512, 160))
    s.label((512, 160), "+5VA")
    s.gnd(u["GND"], 16)
    s.wire(u["REF1"], (448, 464), (576, 464), u["REF2"])
    s.wire((576, 464), (640, 464))
    s.label((640, 464), "+2.5VA")
    # --- current channel filter: R13 / C25 / R15 -> V6+ / V6-
    YP, YN = 304, 432
    s.wire(u["OUT"], (688, YP))
    s.label((688, YP), "SNG-A1N")
    r13 = s.part("res", "A", (736, YP), "R13", "33", rot="R270")
    s.wire((688, YP), r13["A"])
    c25 = s.part("cap", "A", (912, YP), "C25", "1n")
    s.wire(c25["B"], (912, YN))
    r15 = s.part("res", "A", (784, YN), "R15", "9.1k")
    s.gnd(r15["B"])
    xl, xcn, xcp = adc_input(s, 1392, YP, YN, "I", "V6+", "V6-")
    s.bus(YP, [r13["B"][0], 912, xl, xcp, 1392])
    s.bus(YN, [784, 912, xl, xcn, 1392])
    s.text(0, -216, "CURRENT CHANNEL  (phase A : R1, IC2, R13, C25, R15 -> AD7606C V6)", 3)
    # --- voltage channel: R27 / R28 / Re2 / C31 / R19 -> V5+ / V5-
    YP, YN = 800, 928
    s.label((96, YP), "OUT-A")
    r27 = s.part("res", "A", (160, YP), "R27", "40.2k", rot="R270")
    s.wire((96, YP), r27["A"])
    r28 = s.part("res", "A", (336, YP), "R28", "10k")
    s.gnd(r28["B"])
    re2 = s.part("res", "A", (432, YP), "Re2", "1k", rot="R270")
    s.bus(YP, [r27["B"][0], 336, 432])
    c31 = s.part("cap", "A", (912, YP), "C31", "180p")
    s.wire(c31["B"], (912, YN))
    r19 = s.part("res", "A", (784, YN), "R19", "9.1k")
    s.gnd(r19["B"])
    xl, xcn, xcp = adc_input(s, 1392, YP, YN, "V", "V5+", "V5-")
    s.bus(YP, [re2["B"][0], 912, xl, xcp, 1392])
    s.bus(YN, [784, 912, xl, xcn, 1392])
    s.text(0, 664, "VOLTAGE CHANNEL  (phase A : R27, R28, Re2, C31, R19 -> AD7606C V5)", 3)
    # --- supplies
    for x, n, val, lab in ((-320, "V_5VA", "5", "+5VA"), (-176, "V_2V5A", "2.5", "+2.5VA")):
        v = s.part("voltage", "+", (x, 432), n, val,
                   windows=["WINDOW 0 -40 120 Left 2", "WINDOW 3 -40 148 Left 2"])
        s.wire(v["+"], (x, 400))
        s.label((x, 400), lab)
        s.gnd(v["-"])
    s.text(-400, 616, "Ideal analog rails\n(see 02 for the real ones)", 1)


s = Sch(2100, 1500)
header(s, "PhaseSense-8586 - 05 - Measurement channels : frequency response (shunt / divider -> AD7606C pins)",
       "k = 1 : AC on the phase current (current channel, V/A).  k = 0 : AC on the phase voltage (voltage channel, V/V).")
channels(s, "12", "AC {1-k}", "0", "AC {k}")
s.text(-400, 1120, ".ac dec 100 10 10Meg\n.step param k list 0 1", 2, True)
s.text(-400, 1200, ".meas ac G_I FIND mag(V(V6+,V6-)) AT 10\n.meas ac F3dB_I WHEN mag(V(V6+,V6-))=G_I/sqrt(2)\n"
                   ".meas ac G_I_24k FIND mag(V(V6+,V6-)) AT 24k\n.meas ac G_I_2M FIND mag(V(V6+,V6-)) AT 2Meg", 2, True)
s.text(640, 1200, ".meas ac G_V FIND mag(V(V5+,V5-)) AT 10\n.meas ac F3dB_V WHEN mag(V(V5+,V5-))=G_V/sqrt(2)\n"
                  ".meas ac G_V_24k FIND mag(V(V5+,V5-)) AT 24k\n.meas ac G_V_2M FIND mag(V(V5+,V5-)) AT 2Meg", 2, True)
s.save("05_Measurement_Channels_AC.asc")

s = Sch(2100, 1500)
header(s, "PhaseSense-8586 - 06 - Measurement channels : DC transfer and step response",
       "Phase voltage steps 0 -> 25.2 V (6S battery) at 100 us, phase current steps 0 -> 35 A (MR60 rating, J1 -> J2) at 300 us.")
channels(s, "PWL(0 0 100u 0 100.1u 25.2)", None, "PWL(0 0 300u 0 300.1u 35)", None)
s.text(-400, 1120, ".tran 0 600u 0 20n", 2, True)
s.text(-400, 1160, ".meas tran VI_zero AVG V(V6+,V6-) FROM 50u TO 90u\n.meas tran VI_35A AVG V(V6+,V6-) FROM 550u TO 600u\n"
                   ".meas tran V6N_bias AVG V(V6-) FROM 550u TO 600u\n.meas tran T_I_1pct WHEN V(V6+,V6-)=VI_zero+0.99*(VI_35A-VI_zero) FALL=1", 2, True)
s.text(720, 1160, ".meas tran VV_zero AVG V(V5+,V5-) FROM 50u TO 90u\n.meas tran VV_25V AVG V(V5+,V5-) FROM 250u TO 290u\n"
                  ".meas tran VOUTA AVG V(OUT-A) FROM 250u TO 290u\n.meas tran T_V_1pct WHEN V(V5+,V5-)=VV_zero+0.99*(VV_25V-VV_zero) RISE=1", 2, True)
s.save("06_Measurement_Channels_Step.asc")
print("ok")
