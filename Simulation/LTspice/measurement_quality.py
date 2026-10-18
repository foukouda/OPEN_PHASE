"""Measurement quality predicted from the simulations (called by run_simulations.py).

07_Measurement_Quality_Waveforms
    A realistic ESC waveform goes through both channels of phase U. The phase voltage and the motor
    current of the simulation are the truth. The readings are rebuilt from the AD7606C pin voltages
    the way a firmware would do it, then compared with the truth. Three runs: shunt without
    inductance, then with half and with the whole inductance allowed by its datasheet.
    The DC bus channel (battery -> R9 -> ESC) carries the three phases together and is analysed the
    same way: battery current, bus voltage, power from the battery, ESC efficiency read by the board.
08_Measurement_Quality_Tolerances
    Monte Carlo on the component tolerances: spread of the DC readings before any calibration.

What the simulations cannot give comes from the datasheets and is gathered in the constants below:
the AD7606C-18 (input filter, sampling, noise, gain and zero errors) and the drift with temperature.
Results are written to measurement_quality.md and to three figures.
"""
import os
import re

import numpy as np

from ltraw import read_raw, split_steps
from plotstyle import C1, C2, C3, C4, GRID, HERE, INK2, plt, save

SIM7, SIM8 = "07_Measurement_Quality_Waveforms", "08_Measurement_Quality_Tolerances"

# Constants a firmware would use when it only knows the schematic
K_I = 1e-3 * 20                      # V/A  : 1 mohm shunt x 20 V/V
K_V = 10e3 / (40.2e3 + 10e3)         # V/V  : R18 / (R17 + R18)
V_ZERO = 2.5                         # V    : zero-current level of the INA241 (+2.5VA)

# R1 / R4 / R7 / R9 = PBV-R001-F1-0.5, Isabellenhuette datasheet (issue 10-Nov-2016, link stored in the KiCad symbol)
SHUNT = {"r": 1e-3, "tol": 0.005,    # 1 mohm, +/-0.5 % (last field of the ordering code)
         "tcr": 75e-6,               # /K, maximum for values below 10 mohm (20 ... 60 degC)
         "rth": 15.0,                # K/W to ambient, maximum, without heatsink
         "power": 3.0,               # W without heatsink
         "l_max": 10e-9,             # H, maximum
         "emf": 2e-6,                # V/K, thermal EMF, maximum
         "stability": 0.5}           # %, after 2000 h at nominal load
# AD7606C-18 datasheet (Rev. A), +/-10 V single-ended range (hardware mode, RANGE pin high)
ADC = {"full_scale": 10.0,
       "lsb": 20.0 / 2 ** 18,        # 76.3 uV
       "snr_db": 92.5,               # typical, low bandwidth mode, no oversampling
       "f_lp": 25e3,                 # analog input filter, low bandwidth mode (-3 dB)
       "pfs_lsb": 120,               # positive / negative full-scale error, maximum
       "zero_lsb": 80,               # bipolar zero code error, maximum
       "ref": (2.495, 2.505)}        # external reference input voltage
INA_NOISE = 49e-9                    # V/sqrt(Hz), input-referred, INA241A2 datasheet
# Drift per kelvin, datasheet maxima
DRIFT = {"ina_gain": 1e-6, "ina_vos": 150e-9,       # INA241A2
         "adc_fs": 3e-6, "adc_zero": 2.5e-6,        # AD7606C-18, of the 20 V span
         "ref": 2e-6,                               # LTC6655B
         "r_tcr": 100e-6}                           # R17 / R18: no part number in the schematic, thick film assumed
DT_AMB = 20.0                        # K : temperature change since the calibration
DT = 25e-9                           # resampling step of the simulated waveforms
PERIODS = 4                          # electrical periods analysed (end of the simulation)
RATES = (10e3, 20e3, 50e3, 100e3, 200e3, 500e3, 1e6)

_report = {}                         # filled by fig07 / fig08, written by write_report


def spice_num(txt):
    m = re.match(r"([-+]?[\d.]+(?:e[-+]?\d+)?)(meg|[kmunp]?)", txt.lower())
    return float(m.group(1)) * {"": 1, "k": 1e3, "meg": 1e6, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12}[m.group(2)]


def params(name):
    """.param values and .step list of a simulation, read from its .asc so the analysis follows the schematic."""
    out, steps = {}, []
    with open(os.path.join(HERE, name + ".asc"), encoding="utf-8") as f:
        for line in f:
            if "!.param" in line:
                for k, v in re.findall(r"(\w+)=([-+\d.]+[a-zA-Z]*)", line):
                    out[k] = spice_num(v)
            m = re.search(r"\.step param \w+ list ([\w. ]+)", line)
            if m:
                steps = [spice_num(v) for v in m.group(1).split()]
    return out, steps


def lowpass(x, fc):
    """First-order low-pass on the DT grid."""
    a = 1 - np.exp(-2 * np.pi * fc * DT)
    out = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        acc += a * (v - acc)
        out[i] = acc
    return out


def calibration():
    """Two-point DC calibration (0 / 35 A, 0 / 25.2 V) taken from simulation 06."""
    d = read_raw(os.path.join(HERE, "06_Measurement_Channels_Step.raw"))
    t = d["time"]

    def avg(key_p, key_n, a, b):
        m = (t >= a) & (t <= b)
        return float(np.mean(d[key_p][m] - d[key_n][m]))

    i_zero, i_35 = avg("v(v8+)", "v(v8-)", 50e-6, 90e-6), avg("v(v8+)", "v(v8-)", 550e-6, 600e-6)
    v_zero, v_25 = avg("v(v7+)", "v(v7-)", 50e-6, 90e-6), avg("v(v7+)", "v(v7-)", 250e-6, 290e-6)
    return {"i_zero": i_zero, "k_i": (i_zero - i_35) / 35.0, "v_zero": v_zero, "k_v": (v_25 - v_zero) / 25.2}


def bandwidths():
    """-3 dB corners of both channels, from simulation 05."""
    volt, curr = split_steps(read_raw(os.path.join(HERE, "05_Measurement_Channels_AC.raw")))
    out = []
    for d, kp, kn in ((curr, "v(v8+)", "v(v8-)"), (volt, "v(v7+)", "v(v7-)")):
        g = np.abs(d[kp] - d[kn])
        db = 20 * np.log10(g / g[0])
        out.append(float(10 ** np.interp(3.0103, -db, np.log10(d["frequency"]))))
    return out


def phasor(x, t, f):
    """Amplitude and phase (rad, sine reference) of the component of x at f, over whole periods."""
    c = 2 * np.mean(x * np.exp(-2j * np.pi * f * t))
    return abs(c), float(np.angle(c * 1j))


def rms(x):
    return float(np.sqrt(np.mean(x ** 2)))


def pct(a, b):
    return 100.0 * (a - b) / b


# ------------------------------------------------------------------ 07 : waveforms
def analyse(d, fe, cal, f_i, f_v):
    """Truth and readings of one run of simulation 07, on the DT grid, with their figures of merit."""
    t_end = d["time"][-1]
    tu = np.arange(0.0, t_end, DT)
    g = {k: np.interp(tu, d["time"], d[k]) for k in d if k != "time"}
    w = tu >= t_end - PERIODS / fe - DT / 2             # analysis window, whole electrical periods
    tw = tu[w]
    r = {"tu": tu, "w": w, "i_true": g["i(l_m)"], "v_true": g["v(out-u)"]}
    adc_i = lowpass(g["v(v8+)"] - g["v(v8-)"], ADC["f_lp"])                      # AD7606C input filter
    adc_v = lowpass(g["v(v7+)"] - g["v(v7-)"], ADC["f_lp"])
    r["i_nom"], r["v_nom"] = (V_ZERO - adc_i) / K_I, adc_v / K_V                 # schematic constants only
    r["i_cal"], r["v_cal"] = (cal["i_zero"] - adc_i) / cal["k_i"], (adc_v - cal["v_zero"]) / cal["k_v"]
    # matched channels: each reading also gets the corner of the other channel, so both see the same filtering
    r["i_eq"], r["v_eq"] = lowpass(r["i_cal"], f_v), lowpass(r["v_cal"], f_i)

    # fundamental of each signal -> gain and delay of each channel
    (ai, pi_), (av, pv) = phasor(r["i_true"][w], tw, fe), phasor(r["v_true"][w], tw, fe)
    (aic, pic), (avc, pvc) = phasor(r["i_cal"][w], tw, fe), phasor(r["v_cal"][w], tw, fe)
    r["fund"] = (ai, aic, av, avc)
    r["delay"] = ((pi_ - pic) / (2 * np.pi * fe), (pv - pvc) / (2 * np.pi * fe))
    i_shift = np.interp(tu + (r["delay"][0] - r["delay"][1]), tu, r["i_cal"])    # current aligned on the voltage

    r["p_true"] = float(np.mean(r["v_true"][w] * r["i_true"][w]))
    r["power"] = {"schematic constants": float(np.mean(r["v_nom"][w] * r["i_nom"][w])),
                  "after DC calibration": float(np.mean(r["v_cal"][w] * r["i_cal"][w])),
                  "DC calibration + time shift of the current": float(np.mean(r["v_cal"][w] * i_shift[w])),
                  "DC calibration + matched channel filters": float(np.mean(r["v_eq"][w] * r["i_eq"][w]))}
    r["ripple"] = (rms(r["i_true"][w] - ai * np.sin(2 * np.pi * fe * tw + pi_) - np.mean(r["i_true"][w])),
                   rms(r["i_cal"][w] - aic * np.sin(2 * np.pi * fe * tw + pic) - np.mean(r["i_cal"][w])))
    for key in ("i", "v"):
        sig = [r[key + "_true"][w], r[key + "_nom"][w], r[key + "_cal"][w]]
        r[key + "_rms"], r[key + "_mean"] = tuple(rms(x) for x in sig), tuple(float(np.mean(x)) for x in sig)
    return r


def sampling(r, fe, i_key, v_key):
    """Power error against the ADC sampling rate: both channels sampled together, any phase against the PWM."""
    rng = np.random.default_rng(1)
    tu, w = r["tu"], r["w"]
    t0, span, i_rms = tu[w][0], PERIODS / fe, rms(r["i_true"][w])
    out = []
    for fs in RATES:
        n = int(round(fs * span))
        err_p, err_i = [], []
        for off in rng.uniform(0, 1 / fs, 300):
            ts = t0 + off + np.arange(n) / fs
            i_s = np.interp(ts, tu, r[i_key])
            err_p.append(pct(float(np.mean(i_s * np.interp(ts, tu, r[v_key]))), r["p_true"]))
            err_i.append(pct(rms(i_s), i_rms))
        out.append((float(np.median(np.abs(err_p))), float(np.max(np.abs(err_p))), float(np.max(np.abs(err_i)))))
    return out


def analyse_bus(d, fe, cal):
    """Truth and readings of the DC bus channel (battery -> R9 -> ESC) for one run of simulation 07.

    The channel has the same parts and values as phase U, so it is read with the same calibration."""
    t_end = d["time"][-1]
    tu = np.arange(0.0, t_end, DT)
    g = {k: np.interp(tu, d["time"], d[k]) for k in ("i(l_bat)", "v(out-b)", "v(v2+)", "v(v2-)", "v(v1+)", "v(v1-)")}
    w = tu >= t_end - PERIODS / fe - DT / 2
    r = {"tu": tu, "w": w, "i_true": g["i(l_bat)"], "v_true": g["v(out-b)"]}
    adc_i = lowpass(g["v(v2+)"] - g["v(v2-)"], ADC["f_lp"])
    adc_v = lowpass(g["v(v1+)"] - g["v(v1-)"], ADC["f_lp"])
    r["i_nom"], r["v_nom"] = (V_ZERO - adc_i) / K_I, adc_v / K_V
    r["i_cal"], r["v_cal"] = (cal["i_zero"] - adc_i) / cal["k_i"], (adc_v - cal["v_zero"]) / cal["k_v"]
    r["p_true"] = float(np.mean(r["v_true"][w] * r["i_true"][w]))
    r["power"] = {"schematic constants": float(np.mean(r["v_nom"][w] * r["i_nom"][w])),
                  "after DC calibration": float(np.mean(r["v_cal"][w] * r["i_cal"][w]))}
    for key in ("i", "v"):
        sig = [r[key + "_true"][w], r[key + "_nom"][w], r[key + "_cal"][w]]
        r[key + "_mean"] = tuple(float(np.mean(x)) for x in sig)
        r[key + "_ripple"] = tuple(float(np.std(x)) for x in sig)                # rms around the mean
        r[key + "_pp"] = tuple(float(np.ptp(x)) for x in sig)
    return r


def efficiency(phase, bus):
    """ESC efficiency as the board reads it: power to the motor (three phases like phase U) over power from the battery."""
    pp, pb = phase["power"], bus["power"]
    return {"truth": 100 * 3 * phase["p_true"] / bus["p_true"],
            "schematic constants": 100 * 3 * pp["schematic constants"] / pb["schematic constants"],
            "after DC calibration": 100 * 3 * pp["after DC calibration"] / pb["after DC calibration"],
            "DC calibration + matched channel filters":
                100 * 3 * pp["DC calibration + matched channel filters"] / pb["after DC calibration"]}


def fig07_bus(p, lsh, runs, bus, rates):
    """Figure of the DC bus channel; `rates` is the sampling study of phase U, for comparison."""
    base = bus[0]                                         # shunts without inductance
    bus_rates = sampling(base, p["fe"], "i_cal", "v_cal")
    eff = [efficiency(a, b) for a, b in zip(runs, bus)]
    err_bus = [pct(b["power"]["after DC calibration"], b["p_true"]) for b in bus]
    err_ph = [pct(a["power"]["after DC calibration"], a["p_true"]) for a in runs]
    keep = ("p_true", "power", "i_mean", "v_mean", "i_ripple", "v_ripple", "i_pp", "v_pp")
    _report["07"]["bus"] = dict(runs=[{k: r[k] for k in keep} for r in bus], eff=eff, rates=bus_rates,
                                err_bus=err_bus, err_ph=err_ph)

    fig, ax = plt.subplots(2, 2, figsize=(12, 7.6))
    a, b, c, e = ax[0, 0], ax[0, 1], ax[1, 0], ax[1, 1]
    tu, w = base["tu"], base["w"]
    us = (tu - tu[w][0]) * 1e6
    m = (us >= 0) & (us <= 6e6 / p["fpwm"])               # six PWM periods
    a.plot(us[m], base["i_true"][m], color=INK2, lw=1.2, label="battery current (truth)")
    a.plot(us[m], base["i_cal"][m], color=C1, label="reading")
    a.set_ylim(0, a.get_ylim()[1] * 1.22)
    a.set_xlabel("Time (us)")
    a.set_ylabel("DC bus current (A)")
    a.set_title(f"07 - DC bus current: {base['i_mean'][0]:.1f} A, the reading keeps "
                f"{100 * base['i_ripple'][2] / base['i_ripple'][0]:.0f} % of the ripple")
    a.legend(loc="upper right", fontsize=9, ncol=2)

    b.plot(us[m], base["v_true"][m], color=INK2, lw=1.2, label="bus voltage at the ESC connector (truth)")
    b.plot(us[m], base["v_cal"][m], color=C2, label="reading")
    lo, hi = b.get_ylim()
    b.set_ylim(lo, hi + 0.35 * (hi - lo))
    b.set_xlabel("Time (us)")
    b.set_ylabel("DC bus voltage (V)")
    b.set_title(f"DC bus voltage: {base['v_mean'][0]:.2f} V on average, {base['v_pp'][0]:.1f} V pp of ripple")
    b.legend(loc="upper right", fontsize=9, ncol=2)

    nh = [v * 1e9 for v in lsh]
    c.axhline(0, color=INK2, lw=1, ls="--")
    c.plot(nh, err_ph, "o-", color=C4, ms=8, label="power to the motor (three phases)")
    c.plot(nh, err_bus, "o-", color=C3, ms=8, label="power from the battery (DC bus)")
    span = max(abs(v) for v in err_ph + err_bus)
    c.set_ylim(-1.25 * span, 1.9 * span)
    c.set_xticks(nh)
    c.set_xlabel("Inductance of the shunts (nH)")
    c.set_ylabel("Error on the power (%)")
    c.set_title("Power read after DC calibration: the DC bus does not depend on the shunt")
    c.legend(loc="upper left", fontsize=9)

    fs = np.array(RATES) / 1e3
    e.semilogx(fs, [x[1] for x in rates["built"]], "o-", color=C4, ms=8, label="power to the motor (phase U)")
    e.semilogx(fs, [x[1] for x in bus_rates], "o-", color=C3, ms=8, label="power from the battery (DC bus)")
    e.set_ylim(0, None)
    e.set_xlabel("ADC sampling rate (kSPS)")
    e.set_ylabel("Error on the power (%)")
    e.set_title(f"Power error, worst sampling phase, {PERIODS * 1e3 / p['fe']:.0f} ms window")
    e.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    save(fig, "sim07_dc_bus.png")


def fig07():
    p, lsh = params(SIM7)
    fe, fpwm = p["fe"], p["fpwm"]
    cal = calibration()
    f_i, f_v = bandwidths()
    steps = split_steps(read_raw(os.path.join(HERE, SIM7 + ".raw")))
    runs = [analyse(d, fe, cal, f_i, f_v) for d in steps]
    lsh = [0.0 if v < 1e-10 else v for v in lsh] or [0.0]
    base, worst = runs[0], runs[-1]                      # shunt without inductance / with the datasheet maximum
    rates = {"built": sampling(base, fe, "i_cal", "v_cal"), "matched": sampling(base, fe, "i_eq", "v_eq"),
             "lmax": sampling(worst, fe, "i_cal", "v_cal")}

    # noise and resolution of one sample (datasheet figures, simulated gains and bandwidths)
    adc_noise = ADC["full_scale"] / np.sqrt(2) / 10 ** (ADC["snr_db"] / 20)
    enbw = np.pi / 2 * f_i * ADC["f_lp"] / (f_i + ADC["f_lp"])                   # two cascaded first-order poles
    ina_noise = INA_NOISE * np.sqrt(enbw) / SHUNT["r"]                           # A rms through the shunt
    keep = ("p_true", "power", "fund", "delay", "ripple", "i_rms", "i_mean", "v_rms", "v_mean")
    _report["07"] = dict(
        p=p, cal=cal, f_i=f_i, f_v=f_v, lsh=lsh, rates=rates, runs=[{k: r[k] for k in keep} for r in runs],
        noise_i=(adc_noise / cal["k_i"], ina_noise, float(np.hypot(adc_noise / cal["k_i"], ina_noise))),
        noise_v=adc_noise / cal["k_v"], lsb=(ADC["lsb"] / cal["k_i"], ADC["lsb"] / cal["k_v"]))

    # ---- figure
    fig, ax = plt.subplots(2, 2, figsize=(12, 7.6))
    a, b, c, e = ax[0, 0], ax[0, 1], ax[1, 0], ax[1, 1]
    tu, w = base["tu"], base["w"]
    ms = (tu - tu[w][0]) * 1e3
    m = (ms >= 0) & (ms <= 1e3 / fe)
    a.plot(ms[m], base["i_true"][m], color=GRID, lw=1, label="motor current (truth)")
    a.plot(ms[m], base["i_cal"][m], color=C1, lw=1.4, label="reading")
    a.set_xlabel("Time (ms)")
    a.set_ylabel("Phase current (A)")
    a.set_title("07 - Phase current over one electrical period")
    a.legend(loc="lower left", fontsize=9)

    us = ms * 1e3
    k0 = 0.25e6 / fe                                                             # zoom at the current peak
    m = (us >= k0) & (us <= k0 + 150)
    b.plot(us[m] - k0, base["i_true"][m], color=INK2, lw=1.2, label="truth")
    b.plot(us[m] - k0, base["i_cal"][m], color=C1, label="reading, shunt without inductance")
    b.plot(us[m] - k0, worst["i_cal"][m], color=C3, label=f"reading, shunt with {lsh[-1] * 1e9:.0f} nH")
    b.set_ylim(None, b.get_ylim()[1] + 3.5)
    b.set_xlabel("Time (us)")
    b.set_ylabel("Phase current (A)")
    b.set_title("Zoom on the PWM ripple: the shunt inductance changes the reading")
    b.legend(loc="upper right", fontsize=9)

    c.plot(us[m] - k0, base["v_true"][m], color=INK2, lw=1.2, label="truth")
    c.plot(us[m] - k0, base["v_cal"][m], color=C2, label="reading")
    c.set_xlabel("Time (us)")
    c.set_ylabel("Phase voltage (V)")
    c.set_ylim(-2, 33)
    c.set_title(f"Phase voltage: the {fpwm / 1e3:.0f} kHz PWM is still in the reading")
    c.legend(loc="upper right", fontsize=9, ncol=2)

    fs = np.array(RATES) / 1e3
    e.semilogx(fs, [x[1] for x in rates["built"]], "o-", color=C2, label="as built, shunt without inductance")
    e.semilogx(fs, [x[1] for x in rates["lmax"]], "o-", color=C3, label=f"as built, shunt with {lsh[-1] * 1e9:.0f} nH")
    e.semilogx(fs, [x[1] for x in rates["matched"]], "o-", color=C1, label="same filtering on both channels")
    e.set_ylim(0, None)
    e.set_xlabel("ADC sampling rate (kSPS)")
    e.set_ylabel("Error on the phase power (%)")
    e.set_title(f"Power error, worst sampling phase, {PERIODS * 1e3 / fe:.0f} ms window")
    e.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    save(fig, "sim07_measurement_quality.png")
    fig07_bus(p, lsh, runs, [analyse_bus(d, fe, cal) for d in steps], rates)


# ------------------------------------------------------------------ 08 : tolerances
def fig08():
    d = read_raw(os.path.join(HERE, SIM8 + ".raw"))
    n = len(d["i_m"]) // 4                               # per run: (0 A, 0 V) (35 A, 0 V) (0 A, 25.2 V) (35 A, 25.2 V)
    pin_i = (d["v(v8+)"] - d["v(v8-)"]).reshape(n, 4)
    pin_v = (d["v(v7+)"] - d["v(v7-)"]).reshape(n, 4)
    v25 = d["v(+2.5va)"].reshape(n, 4)[:, 0]

    def readings(code_i, code_v):
        i0, i35 = (V_ZERO - code_i[:, 2]) / K_I, (V_ZERO - code_i[:, 3]) / K_I
        v0, v25v = code_v[:, 0] / K_V, code_v[:, 2] / K_V
        return {"zero": i0, "gain_i": pct((i35 - i0) / 35.0, 1.0), "zero_v": v0 * 1e3, "gain_v": pct((v25v - v0) / 25.2, 1.0)}

    analog = readings(pin_i, pin_v)                      # ideal ADC, exact 2.5 V reference
    # ADC of the datasheet: +2.5VA is its reference, plus its own full-scale and zero errors
    rng = np.random.default_rng(1)

    def adc(pin):
        gain = 1 + rng.uniform(-1, 1, (n, 1)) * ADC["pfs_lsb"] * ADC["lsb"] / ADC["full_scale"]
        zero = rng.uniform(-1, 1, (n, 1)) * ADC["zero_lsb"] * ADC["lsb"]
        return pin * (2.5 / v25[:, None]) * gain + zero

    total = readings(adc(pin_i), adc(pin_v))

    def stats(x):
        return float(np.mean(x)), float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5)), float(x.min()), float(x.max())

    outside = float(np.mean((v25 < ADC["ref"][0]) | (v25 > ADC["ref"][1])) * 100)
    _report["08"] = dict(n=n, analog={k: stats(v) for k, v in analog.items()}, total={k: stats(v) for k, v in total.items()},
                         v25=stats(v25), v25_outside=outside, boards=total)

    fig, ax = plt.subplots(1, 3, figsize=(13, 4.2))
    for a, key, label, title in ((ax[0], "zero", "Reading (A)", "Current reading at 0 A"),
                                 (ax[1], "gain_i", "Error (%)", "Current gain error"),
                                 (ax[2], "gain_v", "Error (%)", "Voltage gain error")):
        lo, hi = min(analog[key].min(), total[key].min()), max(analog[key].max(), total[key].max())
        bins = np.linspace(lo, hi, 41)
        h1 = a.hist(analog[key], bins=bins, color=C1, alpha=0.75)[2]
        h2 = a.hist(total[key], bins=bins, histtype="step", color=C2, lw=1.8)[2]
        a.axvline(0, color=INK2, lw=1, ls="--")
        a.set_xlabel(label)
        a.set_title(title)
    ax[0].set_ylabel(f"Boards out of {n}")
    fig.suptitle("08 - Spread of the readings before calibration (Monte Carlo on the tolerances)", fontweight="bold", y=1.08)
    fig.legend([h1[0], h2[0]], ["analog chain (simulated)", "with the ADC and its reference (datasheet)"],
               loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.02), fontsize=9)
    save(fig, "sim08_tolerances.png")


# ------------------------------------------------------------------ accuracy budget
def budget(cal, boards):
    """Error of one reading at a few operating points, for three levels of calibration."""
    k_i, k_v = cal["k_i"], cal["k_v"]
    d = {"i_gain": (SHUNT["tcr"] + DRIFT["ina_gain"] + DRIFT["adc_fs"] + DRIFT["ref"]) * DT_AMB,
         "i_zero": (DRIFT["ina_vos"] / SHUNT["r"] + DRIFT["adc_zero"] * 20 / k_i + DRIFT["ref"] * V_ZERO / k_i) * DT_AMB,
         "v_gain": ((1 - K_V) * 2 * DRIFT["r_tcr"] + DRIFT["adc_fs"] + DRIFT["ref"]) * DT_AMB,
         "v_zero": DRIFT["adc_zero"] * 20 / k_v * DT_AMB}

    def spread(x):                                       # centre and half-width of the interval holding 95 % of the boards
        lo, hi = np.percentile(x, 2.5), np.percentile(x, 97.5)
        return float((lo + hi) / 2), float((hi - lo) / 2)

    rows = []
    for amps in (5.0, 10.0, 20.0, 35.0):
        heat = SHUNT["tcr"] * SHUNT["rth"] * amps ** 2 * SHUNT["r"]              # self-heating of the shunt
        rows.append(("current", amps, spread(boards["zero"] + boards["gain_i"] / 100 * amps),
                     spread(boards["gain_i"] / 100 * amps)[1], (d["i_gain"] + heat) * amps))
    for volts in (12.0, 25.2, 50.0):
        rows.append(("voltage", volts, spread(boards["zero_v"] / 1e3 + boards["gain_v"] / 100 * volts),
                     spread(boards["gain_v"] / 100 * volts)[1], d["v_gain"] * volts))
    return d, rows


# ------------------------------------------------------------------ report
def write_report():
    try:                                                  # --only without 07 / 08: rebuild from the .raw files
        if "07" not in _report:
            fig07()
        if "08" not in _report:
            fig08()
    except FileNotFoundError:
        print("  measurement_quality.md not written (simulations 05 to 08 must have run)")
        return
    q, m = _report["07"], _report["08"]
    p, cal, lsh = q["p"], q["cal"], q["lsh"]
    r = q["runs"][0]                                      # shunt without inductance
    err = [{k: pct(v, x["p_true"]) for k, v in x["power"].items()} for x in q["runs"]]
    p_cal = [e["after DC calibration"] for e in err]
    drift, rows = budget(cal, m["boards"])
    fast = [fs for fs, x in zip(RATES, q["rates"]["built"]) if x[1] <= abs(p_cal[0]) + 0.5]
    b = q["bus"]                                          # DC bus channel
    br, eff = b["runs"][0], b["eff"]
    eff_cal = [e["after DC calibration"] for e in eff]
    heat35 = SHUNT["rth"] * 35 ** 2 * SHUNT["r"]

    L = ["# Predicted measurement quality (generated by run_simulations.py)", "",
         "Phase U and the DC bus (battery to ESC, channel B), from simulations 07 (ESC waveforms) and 08 (Monte Carlo on the tolerances),",
         "completed with the datasheets for what is not simulated: the AD7606C-18 and the drift with temperature.", "",
         "## How far a reading is from the truth", "",
         "Error of one reading of a steady value, for three levels of calibration:", "",
         "- **None**: the firmware uses the schematic values.",
         "- **Zero**: the reading at 0 A is taken before the run and subtracted.",
         f"- **Zero and gain**: the gain has also been calibrated once against a known current and voltage. What is left is the drift "
         f"{DT_AMB:.0f} K away from that calibration, shunt self-heating included (datasheet maxima added together).", "",
         "| True value | No calibration | Zero | Zero and gain |", "| --- | --- | --- | --- |"]
    for kind, x, (centre, half), gain_only, cal_err in rows:
        unit = "A" if kind == "current" else "V"
        zero_cal = f"±{gain_only:.2f} {unit} (±{100 * gain_only / x:.1f} %)" if kind == "current" else "as without calibration"
        L.append(f"| {x:g} {unit} | reads {x + centre - half:.2f} … {x + centre + half:.2f} {unit} | {zero_cal} | "
                 f"±{cal_err:.3f} {unit} (±{100 * cal_err / x:.2f} %) |")
    L += ["", "The first two columns hold for 95 % of the boards. On top of these figures: "
              f"{q['noise_i'][2] * 1e3:.0f} mA rms and {q['noise_v'] * 1e3:.2f} mV rms of noise on one sample (it averages out), and "
              f"±{drift['i_zero'] * 1e3:.0f} mA on the current if the zero is not taken again after a {DT_AMB:.0f} K change.", "",
          "## What the test shows", "",
          f"- **Calibrate the zero of the current.** With the schematic constants the reading at 0 A is {r['i_mean'][1]:+.2f} A. "
          f"Multiplied by the mean phase voltage ({r['v_mean'][0]:.1f} V) it adds {r['i_mean'][1] * r['v_mean'][0]:.1f} W "
          f"to a phase that carries {r['p_true']:.0f} W.",
          f"- **The gain of the current is the shunt.** Its ±{SHUNT['tol'] * 100:g} % tolerance is the whole spread before a gain calibration.",
          f"- **The power under PWM depends on the inductance of the shunt.** The datasheet only says \"below {SHUNT['l_max'] * 1e9:.0f} nH\". "
          f"After DC calibration the power reads {p_cal[0]:+.1f} % without inductance and {p_cal[-1]:+.1f} % with {lsh[-1] * 1e9:.0f} nH: "
          "the phase between the two channels has to be measured on a real board.",
          f"- **Sample fast.** Below {fast[0] / 1e3:g} kSPS the PWM aliases into the power "
          f"(up to {max(x[1] for x in q['rates']['built']):.0f} % at the worst sampling phase over {PERIODS * 1e3 / p['fe']:.0f} ms).",
          f"- **The DC bus is the accurate side.** After DC calibration the power from the battery reads within "
          f"{max(x[1] for x in b['rates']):.2f} %, whatever the inductance of the shunt and from {RATES[0] / 1e3:g} kSPS: "
          "both readings are almost steady, so the delay between the two channels does not matter.",
          f"- **The ESC efficiency is not readable yet.** For a true {eff[0]['truth']:.1f} %, the board reads {min(eff_cal):.1f} % to "
          f"{max(eff_cal):.1f} % depending on the inductance of the phase shunts: the error on the phase power is larger than the losses of an ESC.", "",
          "## Shunt R1 / R4 / R7 / R9: PBV-R001-F1-0.5 (datasheet)", "",
          "| Datasheet figure | Value | Effect on the current reading |", "| --- | --- | --- |",
          f"| Tolerance | ±{SHUNT['tol'] * 100:g} % | ±{SHUNT['tol'] * 100:g} % of gain, removed by a gain calibration |",
          f"| Temperature coefficient | < {SHUNT['tcr'] * 1e6:.0f} ppm/K | ±{SHUNT['tcr'] * DT_AMB * 100:.2f} % for {DT_AMB:.0f} K |",
          f"| Thermal resistance to ambient | < {SHUNT['rth']:.0f} K/W | at 35 A: {35 ** 2 * SHUNT['r']:.2f} W of the {SHUNT['power']:g} W allowed, "
          f"+{heat35:.0f} K, up to {SHUNT['tcr'] * heat35 * 100:.2f} % |",
          f"| Inductance | < {SHUNT['l_max'] * 1e9:.0f} nH | changes the PWM ripple and the delay of the reading, see below |",
          f"| Thermal EMF | < {SHUNT['emf'] * 1e6:.0f} µV/K | {SHUNT['emf'] / SHUNT['r'] * 1e3:.0f} mA of offset per kelvin of difference between the two sense terminals |",
          f"| Stability | < {SHUNT['stability']:g} % after 2000 h | slow drift of the gain at nominal load |", "",
          "The other resistors have no part number in the schematic: 1 % and 100 ppm/K are assumed for them.", "",
          "## Test waveform (simulation 07)", "",
          f"- Battery {p['Vbat']:g} V, PWM {p['fpwm'] / 1e3:g} kHz, electrical frequency {p['fe'] / 1e3:g} kHz.",
          f"- Motor phase: {p['Lm'] * 1e6:g} µH, {p['Rm'] * 1e3:g} mΩ, back-EMF {p['Eb']:g} V peak.",
          f"- Phase current {r['fund'][0]:.1f} A peak at {p['fe'] / 1e3:g} kHz, {r['i_rms'][0]:.2f} A rms with the PWM ripple "
          f"({r['ripple'][0]:.2f} A rms of ripple).",
          f"- True power in the phase: {r['p_true']:.2f} W.", "",
          "## Dynamic accuracy (simulation 07, shunt without inductance)", "",
          "| Quantity | Truth | Reading, schematic constants | Reading, after DC calibration |", "| --- | --- | --- | --- |",
          f"| Mean current | {r['i_mean'][0]:.3f} A | {r['i_mean'][1]:.3f} A | {r['i_mean'][2]:.3f} A |",
          f"| RMS current | {r['i_rms'][0]:.3f} A | {r['i_rms'][1]:.3f} A ({pct(r['i_rms'][1], r['i_rms'][0]):+.2f} %) | "
          f"{r['i_rms'][2]:.3f} A ({pct(r['i_rms'][2], r['i_rms'][0]):+.2f} %) |",
          f"| Mean phase voltage | {r['v_mean'][0]:.3f} V | {r['v_mean'][1]:.3f} V ({pct(r['v_mean'][1], r['v_mean'][0]):+.2f} %) | "
          f"{r['v_mean'][2]:.3f} V ({pct(r['v_mean'][2], r['v_mean'][0]):+.2f} %) |",
          f"| RMS phase voltage | {r['v_rms'][0]:.3f} V | {r['v_rms'][1]:.3f} V ({pct(r['v_rms'][1], r['v_rms'][0]):+.2f} %) | "
          f"{r['v_rms'][2]:.3f} V ({pct(r['v_rms'][2], r['v_rms'][0]):+.2f} %) |", "",
          "The RMS of the phase voltage is low because the filters round the PWM edges: use the mean or the fundamental, not the RMS.", "",
          "| Phase power | Value | Error |", "| --- | --- | --- |", f"| Truth | {r['p_true']:.2f} W | |"]
    L += [f"| Reading, {k} | {v:.2f} W | {err[0][k]:+.2f} % |" for k, v in r["power"].items()]
    L += ["", "\"Matched channel filters\" means that the current reading is also filtered at the corner of the voltage channel and the",
          "voltage reading at the corner of the current channel, in the firmware or with the same RC on both channels.", "",
          "## Effect of the shunt inductance (simulation 07)", "",
          "The inductance adds a voltage proportional to the slope of the current. It acts against the RC filter of the current channel.", "",
          "| Shunt inductance | Delay of the current reading | Delay of the voltage reading | PWM ripple left | RMS current | "
          "Power after DC calibration | Power with a time shift of the current |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for value, x, e in zip(lsh, q["runs"], err):
        L.append(f"| {value * 1e9:.0f} nH | {x['delay'][0] * 1e6:.1f} µs | {x['delay'][1] * 1e6:.1f} µs | {100 * x['ripple'][1] / x['ripple'][0]:.0f} % | "
                 f"{pct(x['i_rms'][2], x['i_rms'][0]):+.2f} % | {e['after DC calibration']:+.2f} % | "
                 f"{e['DC calibration + time shift of the current']:+.2f} % |")
    L += ["", "Delays are measured at the electrical frequency and include the AD7606C input filter.", "",
          "## Sampling rate (simulation 07)", "",
          f"Both channels sampled together, after DC calibration, over {PERIODS} electrical periods and for 300 phases of the",
          "sampling clock against the PWM. Power error: median / worst phase.", "",
          f"| Sampling rate | As built, shunt without inductance | As built, shunt with {lsh[-1] * 1e9:.0f} nH | Same filtering on both channels |",
          "| --- | --- | --- | --- |"]
    L += [f"| {fs / 1e3:g} kSPS | {a[0]:.2f} % / {a[1]:.2f} % | {b[0]:.2f} % / {b[1]:.2f} % | {c[0]:.2f} % / {c[1]:.2f} % |"
          for fs, a, b, c in zip(RATES, q["rates"]["built"], q["rates"]["lmax"], q["rates"]["matched"])]
    L += ["", "## DC bus, battery to ESC (simulation 07)", "",
          "The DC bus channel (shunt R9, IC10, divider R32 / R33) has the same parts and values as the phase channels. The static",
          "accuracy, the noise and the drift given in this report apply to it, and it is read here with the same DC calibration.",
          "It is read on the ADC inputs V2 (current) and V1 (voltage); phase U is on V8 (current) and V7 (voltage).", "",
          f"- Load: the three phases together, {3 * r['p_true']:.0f} W to the motor.",
          f"- Battery and leads: {p['Rb'] * 1e3:g} mΩ, {p['Lb'] * 1e9:g} nH. ESC input capacitor: {p['Cdc'] * 1e6:g} µF, {p['Resr'] * 1e3:g} mΩ. "
          "These four values are assumed, no battery or ESC is specified in the project. They set the ripple, not the mean values.", "",
          "| Quantity | Truth | Reading, schematic constants | Reading, after DC calibration |", "| --- | --- | --- | --- |",
          f"| Mean battery current | {br['i_mean'][0]:.3f} A | {br['i_mean'][1]:.3f} A ({pct(br['i_mean'][1], br['i_mean'][0]):+.2f} %) | "
          f"{br['i_mean'][2]:.3f} A ({pct(br['i_mean'][2], br['i_mean'][0]):+.2f} %) |",
          f"| Current ripple | {br['i_pp'][0]:.1f} A pp | {br['i_pp'][1]:.1f} A pp | {br['i_pp'][2]:.1f} A pp |",
          f"| Mean bus voltage | {br['v_mean'][0]:.3f} V | {br['v_mean'][1]:.3f} V ({pct(br['v_mean'][1], br['v_mean'][0]):+.2f} %) | "
          f"{br['v_mean'][2]:.3f} V ({pct(br['v_mean'][2], br['v_mean'][0]):+.2f} %) |",
          f"| Voltage ripple | {br['v_pp'][0]:.2f} V pp | {br['v_pp'][1]:.2f} V pp | {br['v_pp'][2]:.2f} V pp |",
          f"| Power from the battery | {br['p_true']:.2f} W | {br['power']['schematic constants']:.2f} W "
          f"({pct(br['power']['schematic constants'], br['p_true']):+.2f} %) | {br['power']['after DC calibration']:.2f} W "
          f"({pct(br['power']['after DC calibration'], br['p_true']):+.2f} %) |", "",
          f"The filters keep {100 * br['i_ripple'][2] / br['i_ripple'][0]:.0f} % of the current ripple and "
          f"{100 * br['v_ripple'][2] / br['v_ripple'][0]:.0f} % of the voltage ripple: the ripple of the DC bus cannot be read, its mean values can.",
          f"Sampling rate: the power from the battery stays within {max(x[1] for x in b['rates']):.2f} % from {RATES[0] / 1e3:g} kSPS to "
          f"{RATES[-1] / 1e3:g} kSPS, at the worst sampling phase.", "",
          "### ESC efficiency read by the board", "",
          "Power to the motor (three phases, each read like phase U) divided by the power from the battery. The truth is what perfect",
          "sensors would read at the same points: the phase voltage is taken on the motor side of the shunts, and in this model the ESC",
          "only loses what its input capacitor dissipates.", "",
          "| Shunt inductance | Truth | Schematic constants | After DC calibration | DC calibration + matched channel filters |",
          "| --- | --- | --- | --- | --- |"]
    L += [f"| {value * 1e9:.0f} nH | {e['truth']:.2f} % | {e['schematic constants']:.2f} % | {e['after DC calibration']:.2f} % | "
          f"{e['DC calibration + matched channel filters']:.2f} % |" for value, e in zip(lsh, eff)]
    L += ["", "The error on the efficiency is the error on the phase power: over the three runs the power from the battery reads "
              f"{min(b['err_bus']):+.2f} % to {max(b['err_bus']):+.2f} %, the power to the motor {min(b['err_ph']):+.2f} % to {max(b['err_ph']):+.2f} %."]
    L += ["", "## Noise and resolution of one sample", "",
          "Computed from the datasheets with the simulated gains and bandwidths "
          f"(current channel {q['f_i'] / 1e3:.1f} kHz, voltage channel {q['f_v'] / 1e3:.1f} kHz, then 25 kHz in the ADC).", "",
          "| Quantity | Current channel | Voltage channel |", "| --- | --- | --- |",
          f"| 1 LSB (18 bits, ±10 V) | {q['lsb'][0] * 1e3:.1f} mA | {q['lsb'][1] * 1e3:.2f} mV |",
          f"| ADC noise (SNR {ADC['snr_db']} dB) | {q['noise_i'][0] * 1e3:.1f} mA rms | {q['noise_v'] * 1e3:.2f} mV rms |",
          f"| INA241A2 noise (49 nV/√Hz) | {q['noise_i'][1] * 1e3:.1f} mA rms | |",
          f"| Total | {q['noise_i'][2] * 1e3:.1f} mA rms | {q['noise_v'] * 1e3:.2f} mV rms |", "",
          f"## Static accuracy before calibration (simulation 08, {m['n']} boards)", "",
          "Readings computed with the schematic constants. Each cell gives the mean and the interval that holds 95 % of the boards.", "",
          "| Quantity | Analog chain (simulated) | With the ADC and its reference (datasheet) |", "| --- | --- | --- |"]
    for key, label, unit, fmt in (("zero", "Current reading at 0 A", "A", "%+.2f"), ("gain_i", "Current gain error", "%", "%+.2f"),
                                  ("zero_v", "Voltage reading at 0 V", "mV", "%+.1f"), ("gain_v", "Voltage gain error", "%", "%+.2f")):
        cells = ["%s %s (%s … %s)" % (fmt % s[0], unit, fmt % s[1], fmt % s[2]) for s in (m["analog"][key], m["total"][key])]
        L.append(f"| {label} | {cells[0]} | {cells[1]} |")
    L += ["", f"+2.5VA over the {m['n']} boards: {m['v25'][0]:.4f} V on average, {m['v25'][3]:.4f} … {m['v25'][4]:.4f} V. "
              f"The AD7606C accepts {ADC['ref'][0]} … {ADC['ref'][1]} V on REFIN: {m['v25_outside']:.1f} % of the boards are outside.", "",
          f"## Drift after calibration (datasheet maxima, {DT_AMB:.0f} K)", "",
          "| Contribution | Current | Voltage |", "| --- | --- | --- |",
          f"| Gain | ±{drift['i_gain'] * 100:.2f} % (shunt {SHUNT['tcr'] * 1e6:.0f}, INA241A2 {DRIFT['ina_gain'] * 1e6:.0f}, ADC {DRIFT['adc_fs'] * 1e6:.0f}, "
          f"reference {DRIFT['ref'] * 1e6:.0f} ppm/K) | ±{drift['v_gain'] * 100:.2f} % (divider with two {DRIFT['r_tcr'] * 1e6:.0f} ppm/K resistors, assumed) |",
          f"| Zero | ±{drift['i_zero'] * 1e3:.0f} mA (mostly the ADC zero drift) | ±{drift['v_zero'] * 1e3:.0f} mV |",
          f"| Shunt self-heating | up to {SHUNT['tcr'] * heat35 * 100:.2f} % at 35 A | |", "",
          "## Not covered by these simulations", "",
          "- INA241A2 common-mode rejection and its 1 µs output hold at each PWM edge (behavioural model).",
          "- Layout: Kelvin routing of the shunt, coupling of the PWM edges into the sense traces.",
          "- The other two phases and the real motor: the waveform is a single-phase equivalent.",
          "- The real battery and ESC: the DC bus values are assumed, the half-bridges have no loss and their PWM uses the nominal",
          "  battery voltage, not the sagging bus voltage.", ""]
    with open(os.path.join(HERE, "measurement_quality.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print("  measurement_quality.md written")
