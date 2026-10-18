"""Run the OPEN_PHASE LTspice simulations and plot the results.

Usage (from this folder):
    python run_simulations.py            # run LTspice in batch mode, then plot
    python run_simulations.py --no-run   # only re-plot existing .raw files
    python run_simulations.py --only 02 05   # restrict to some simulations

Figures are written to ../../Images/Simulation/ (referenced by the README),
the .meas results to results.md.
"""
import argparse
import os
import re
import subprocess
import sys

import numpy as np

import measurement_quality
from ltraw import read_raw, split_steps
from plotstyle import C1, C2, C3, C4, GRID, HERE, INK2, SURFACE, plt, save

SIMS = ["01_Power_Chain_Startup", "02_Analog_Rails_Startup", "03_Boost_Ripple",
        "04_Analog_Rails_PSRR", "05_Measurement_Channels_AC", "06_Measurement_Channels_Step",
        "07_Measurement_Quality_Waveforms", "08_Measurement_Quality_Tolerances"]
LTSPICE = os.path.expandvars(r"%LOCALAPPDATA%\Programs\ADI\LTspice\LTspice.exe")


def run(name):
    print(f"  LTspice: {name}.asc", flush=True)
    subprocess.run([LTSPICE, "-b", os.path.join(HERE, name + ".asc")], check=True, cwd=HERE)


def meas(name):
    """Return {measure: [result string per .step]} parsed from the LTspice log."""
    out, cur = {}, None
    with open(os.path.join(HERE, name + ".log"), encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"^Measurement: (\w+)", line)
            if m:                                  # stepped: one row per step follows
                cur = m.group(1)
                out[cur] = []
                continue
            if cur and re.match(r"^\s+\d+\t", line):
                out[cur].append(line.split("\t")[1].strip())
                continue
            if line.strip() and not line.startswith(" "):
                cur = None
            m = re.match(r"^(\w+):\s*(.*=.*)$", line.strip())
            if m and not line.startswith(("C:", "WARNING", "Warning", "Options", "Circuit", "Start")):
                out[m.group(1)] = [m.group(2)]
    return out


def num(s):
    """Numeric result of a .meas string (dB value, abscissa of a WHEN, or the value)."""
    if "dB" in s:
        return float(re.search(r"\(([-\d.eE+]+)dB", s).group(1))
    m = re.search(r"\bAT\s+([-+\d.eE]+)", s, re.I)
    if m:
        return float(m.group(1))
    return float(re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s.split("=")[-1])[0])


def decimate(t, *ys, n=6000):
    """Min/max decimation so dense switching traces keep their envelope."""
    if len(t) <= 2 * n:
        return (t,) + ys
    edges = np.linspace(0, len(t), n + 1).astype(int)
    tt, outs = [], [[] for _ in ys]
    for a, b in zip(edges[:-1], edges[1:]):
        tt += [t[a], t[b - 1]]
        for o, y in zip(outs, ys):
            seg = y[a:b]
            o += [seg.min(), seg.max()]
    return (np.array(tt),) + tuple(np.array(o) for o in outs)


def bw_limit(t, y, f3db=20e6, dt=0.5e-9):
    """Resample on a uniform grid and apply a 1st-order low-pass, like a
    scope's 20 MHz bandwidth limit (removes single-sample switching spikes)."""
    tu = np.arange(t[0], t[-1], dt)
    yu = np.interp(tu, t, y)
    a = 1 - np.exp(-2 * np.pi * f3db * dt)
    out = np.empty_like(yu)
    acc = yu[0]
    for i, v in enumerate(yu):
        acc += a * (v - acc)
        out[i] = acc
    return tu, out


# ------------------------------------------------------------------ figures
def fig01():
    d = read_raw(os.path.join(HERE, "01_Power_Chain_Startup.raw"))
    t = d["time"] * 1e3
    fig, (a, b) = plt.subplots(2, 1, figsize=(9, 6.2), sharex=True,
                               gridspec_kw={"height_ratios": [2, 1]})
    for key, lab, col, dy in (("v(+3.3v)", "+3.3V (host)", C1, 7), ("v(+6v)", "+6V (LT8362)", C2, 0),
                              ("v(+5va)", "+5VA (LT3045-1, IC8)", C3, -7),
                              ("v(+2.5va)", "+2.5VA (IC9, as built)", C4, 0)):
        tt, y = decimate(t, d[key])
        a.plot(tt, y, color=col, label=lab, lw=1.6)
        a.annotate(f"{y[-1]:.2f} V", (tt[-1], y[-1]), xytext=(4, dy), textcoords="offset points",
                   color=INK2, fontsize=8, va="center")
    a.set_ylim(-0.3, 6.5)
    a.set_ylabel("Voltage (V)")
    a.set_title("01 - Power-chain start-up, as built (2 MHz switching simulation)")
    a.legend(loc="lower right", ncol=2)
    tt, il = decimate(t, d["i(l1)"])
    b.plot(tt, il, color=C1, lw=0.8)
    b.set_ylabel("I(L1) (A)")
    b.set_xlabel("Time (ms)")
    b.set_xlim(0, t[-1] * 1.06)
    save(fig, "sim01_power_startup.png")


def fig02():
    runs = split_steps(read_raw(os.path.join(HERE, "02_Analog_Rails_Startup.raw")))
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    d = runs[0]
    t = d["time"] * 1e3
    for key, lab, col in (("v(+6v)", "+6V", C2), ("v(+5va)", "+5VA", C3), ("v(+2.5va)", "+2.5VA", C4)):
        a.plot(t, d[key], color=col, label=lab, lw=1.8)
    t99 = t[np.argmax(d["v(+5va)"] > 4.95)]
    a.axvline(t99, color=INK2, lw=1, ls="--")
    a.text(t99 + 2, 0.5, f"+5VA within 1 %\nafter {t99:.0f} ms", color=INK2, fontsize=9)
    a.set_xlim(0, 100)
    a.set_xlabel("Time (ms)")
    a.set_ylabel("Voltage (V)")
    a.set_title("02 - Analog rails start-up")
    a.legend(loc="center right")
    b.axhspan(2.495, 2.505, color=GRID, lw=0)
    b.text(148, 2.512, "AD7606C REFIN: 2.495 ... 2.505 V", color=INK2, fontsize=8, ha="right")
    y = d["v(+2.5va)"]
    b.plot(t, y, color=C4, label=f"+2.5VA: {y[-1]:.4f} V", lw=1.8)
    b.set_xlim(0, 150)
    b.set_ylim(2.44, 2.52)
    b.set_xlabel("Time (ms)")
    b.set_ylabel("+2.5VA (V)")
    b.set_title("+2.5VA settling into the AD7606C reference window")
    b.legend(loc="lower right", fontsize=9)
    save(fig, "sim02_analog_rails.png")


def fig03():
    d = read_raw(os.path.join(HERE, "03_Boost_Ripple.raw"))
    t = d["time"]
    w = (t >= 5.8e-3) & (t <= 6.0e-3)          # steady-state window for the numbers
    raw_pp = np.ptp(d["v(+6v)"][w])
    bw_pp = np.ptp(bw_limit(t[w], d["v(+6v)"][w])[1])
    # what is left after the LDOs: attenuation of simulation 04 at the switching frequency
    ac = read_raw(os.path.join(HERE, "04_Analog_Rails_PSRR.raw"))
    k = np.argmin(np.abs(ac["frequency"] - 2e6))
    left = {n: bw_pp * abs(ac[key][k]) for n, key in (("+5VA", "v(+5va)"), ("+2.5VA", "v(+2.5va)"))}
    m = (t >= 5.99e-3) & (t <= 5.995e-3)       # 5 us = 10 switching periods for the plot
    t0 = t[m][0]
    fig, (a, b) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True)
    y = d["v(+6v)"][m]
    a.plot((t[m] - t0) * 1e6, (y - y.mean()) * 1e3, color=GRID, lw=1,
           label=f"raw simulation ({raw_pp * 1e3:.2f} mV pp)")
    tb, yb = bw_limit(t[m], y)
    a.plot((tb - t0) * 1e6, (yb - y.mean()) * 1e3, color=C2, lw=1.6,
           label=f"20 MHz bandwidth ({bw_pp * 1e3:.2f} mV pp)")
    a.set_ylabel("+6V ripple (mV)")
    span = abs(yb - y.mean()).max() * 1e3
    a.set_ylim(-2.2 * span, 2.4 * span)          # room for the legend above, the note below
    a.legend(loc="upper right", fontsize=8, ncol=2)
    load = measurement_quality.params("03_Boost_Ripple")[0]["I6"]
    a.set_title(f"03 - LT8362 steady-state ripple on +6V, {load * 1e3:.0f} mA load (5 us window)")
    a.text(0.01, 0.05, "after the LT3045-1 (PSRR at 2 MHz, simulation 04):  "
           + ",  ".join(f"{n} = {v * 1e6:.2f} uV pp" for n, v in left.items()),
           transform=a.transAxes, color=INK2, fontsize=9)
    b.plot((t[m] - t0) * 1e6, d["i(l1)"][m] * 1e3, color=C1, lw=1.4)
    b.set_ylabel("I(L1) (mA)")
    b.set_xlabel("Time (us)")
    save(fig, "sim03_ripple.png")
    print(f"  +6V: raw {raw_pp * 1e3:.3f} mV pp, 20 MHz BW {bw_pp * 1e3:.3f} mV pp; left on rails: "
          + ", ".join(f"{n} {v * 1e6:.3f} uV pp" for n, v in left.items()))


def fig04():
    d = read_raw(os.path.join(HERE, "04_Analog_Rails_PSRR.raw"))
    f = d["frequency"]
    fig, a = plt.subplots(figsize=(9, 4.4))
    for key, lab, col, dx, dy in (("v(+5va)", "+5VA (IC8)", C1, 12, -22),
                                  ("v(+2.5va)", "+2.5VA (IC9)", C2, -96, 16)):
        psrr = -20 * np.log10(np.abs(d[key]))
        a.semilogx(f, psrr, color=col, lw=2, label=lab)
        i = np.argmin(np.abs(f - 2e6))
        a.plot(f[i], psrr[i], "o", color=col, ms=8, mec=SURFACE, mew=2)
        a.annotate(f"{psrr[i]:.0f} dB @ 2 MHz", (f[i], psrr[i]), xytext=(dx, dy),
                   textcoords="offset points", color=INK2, fontsize=9,
                   arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    a.axvline(2e6, color=INK2, lw=1, ls="--")
    a.text(2e6, a.get_ylim()[1], " LT8362\n 2 MHz", color=INK2, fontsize=8, va="top")
    a.set_xlabel("Frequency (Hz)")
    a.set_ylabel("PSRR (dB)")
    a.set_title("04 - PSRR from +6V to the analog rails (reference + LT3045-1, board capacitors)")
    a.set_xlim(f[0], f[-1])
    a.legend(loc="lower left")
    save(fig, "sim04_psrr.png")


def fig05():
    volt, curr = split_steps(read_raw(os.path.join(HERE, "05_Measurement_Channels_AC.raw")))
    fig, a = plt.subplots(figsize=(9, 4.4))
    for d, kp, kn, lab, unit, col in ((curr, "v(v8+)", "v(v8-)", "Current channel", "mV/A", C1),
                                      (volt, "v(v7+)", "v(v7-)", "Voltage channel", "mV/V", C2)):
        f = d["frequency"]
        g = np.abs(d[kp] - d[kn])
        db = 20 * np.log10(g / g[0])
        f3 = 10 ** np.interp(3.0103, -db, np.log10(f))
        a.semilogx(f, db, color=col, label=f"{lab}: {g[0] * 1e3:.2f} {unit}, -3 dB at {f3 / 1e3:.1f} kHz")
        a.plot(f3, -3.01, "o", color=col, ms=8, mec=SURFACE, mew=2)
    for fx, lab, ha in ((24e3, "ESC PWM \n24 kHz ", "right"), (2e6, "LT8362 \n2 MHz ", "right")):
        a.axvline(fx, color=INK2, lw=1, ls="--")
        a.text(fx, -52, lab, color=INK2, fontsize=8, va="bottom", ha=ha)
    a.set_xlabel("Frequency (Hz)")
    a.set_ylabel("Gain relative to DC (dB)")
    a.set_title("05 - Measurement channels, from the phase to the AD7606C input pins")
    a.set_ylim(-55, 3)
    a.set_xlim(f[0], f[-1])
    a.legend(loc="center left")
    save(fig, "sim05_channels_ac.png")


def fig06():
    d = read_raw(os.path.join(HERE, "06_Measurement_Channels_Step.raw"))
    t = d["time"] * 1e6
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.5, 4.2))
    vv = d["v(v7+)"] - d["v(v7-)"]
    m = (t > 90) & (t < 170)
    a.plot(t[m] - 100, vv[m], color=C2)
    a.axhline(vv[np.argmin(np.abs(t - 290))], color=INK2, lw=1, ls="--")
    a.text(68, vv[np.argmin(np.abs(t - 290))] - 0.15, f"{vv[np.argmin(np.abs(t - 290))]:.3f} V for 25.2 V",
           color=INK2, fontsize=9, ha="right", va="top")
    a.set_xlabel("Time after the voltage step (us)")
    a.set_ylabel("V(V7+) - V(V7-) (V)")
    a.set_title("06 - Voltage channel: 0 -> 25.2 V phase step")
    vi = d["v(v8+)"] - d["v(v8-)"]
    m = (t > 280) & (t < 420)
    b.plot(t[m] - 300, vi[m], color=C1)
    for tx, ha, dx in ((250, "left", -18), (590, "right", 118)):
        y = vi[np.argmin(np.abs(t - tx))]
        b.axhline(y, color=INK2, lw=1, ls="--")
        b.text(dx, y + 0.02, f"{y:.4f} V", color=INK2, fontsize=9, ha=ha)
    b.set_xlabel("Time after the current step (us)")
    b.set_ylabel("V(V8+) - V(V8-) (V)")
    b.set_title("Current channel: 0 -> 35 A step (J1 -> J2)")
    save(fig, "sim06_channels_step.png")


FIGS = {"01": fig01, "02": fig02, "03": fig03, "04": fig04, "05": fig05, "06": fig06,
        "07": measurement_quality.fig07, "08": measurement_quality.fig08}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("--only", nargs="*", default=None, help="simulation numbers, e.g. 02 05")
    args = ap.parse_args()
    sims = [s for s in SIMS if args.only is None or s[:2] in args.only]
    if not args.no_run:
        if not os.path.exists(LTSPICE):
            sys.exit(f"LTspice not found at {LTSPICE}")
        for s in sims:
            run(s)
    for s in sims:
        FIGS[s[:2]]()
    with open(os.path.join(HERE, "results.md"), "w", encoding="utf-8") as f:
        f.write("# LTspice .meas results (generated by run_simulations.py)\n\n")
        for s in SIMS:
            if not os.path.exists(os.path.join(HERE, s + ".log")):
                continue
            res = meas(s)
            if not res:                            # 07 / 08: analysed by measurement_quality.py
                continue
            n = max((len(v) for v in res.values()), default=1)
            head = ["Measure"] + (["Result"] if n == 1 else [f"Step {i + 1}" for i in range(n)])
            f.write(f"## {s}\n\n| " + " | ".join(head) + " |\n|" + " --- |" * len(head) + "\n")
            for k, v in res.items():
                f.write(f"| `{k}` | " + " | ".join(f"`{x}`" for x in v) + " |\n")
            f.write("\n")
    print("  results.md written")
    measurement_quality.write_report()


if __name__ == "__main__":
    main()
