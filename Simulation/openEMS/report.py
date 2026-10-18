"""Results of shunt_coupling.py: shunt inductance per phase, coupling between phases, figures, results.md.

    C:\\openEMS\\venv\\Scripts\\python.exe report.py

Each run of shunt_coupling.py gives, for the three INA241 inputs, m = Im(V / I) / w with the current
I driven in on one phase and back on another. As the three phase currents sum to zero, what input k
reads is

    V_k = jw (L_k I_k + D_k (I_p - I_q))

with (k, p, q) in the order U, V, W, U, ..: L_k is the inductance of shunt k as its INA241 sees it,
whatever the other two currents do, D_k the coupling from the other two phases. With the drives
UV, VW, WU, L_k is half the difference of the two drives through k, and D_k half the drive that
does not go through k; the three drives must add up to zero on every input.

The figures go to ../../Images/Simulation/, the tables to results.md. LTspice simulation 07 (its
report Simulation/LTspice/measurement_quality.md) gives the phase power error for 0, 5 and 10 nH,
read here at the inductance found.
"""
import json
import os
import re
import sys

import h5py
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, 'run')
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'LTspice')))
import plotstyle  # noqa: E402
from plotstyle import C1, C2, C3, C4, INK, INK2, GRID, SURFACE, plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, LogNorm  # noqa: E402
from matplotlib.patches import Patch, Polygon, Rectangle  # noqa: E402

import shunt_coupling as sc  # noqa: E402

LTSPICE_MD = os.path.normpath(os.path.join(HERE, '..', 'LTspice', 'measurement_quality.md'))
MU0 = 4e-7 * np.pi
PHASES = sc.PHASES
CASES = {'foil': 'Body = foil only', 'backed': 'Body with a metal back'}
NEXT = {'U': 'V', 'V': 'W', 'W': 'U'}
PREV = {v: k for k, v in NEXT.items()}
BLUES = LinearSegmentedColormap.from_list('blues', [SURFACE, '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5',
                                                    '#256abf', '#184f95', '#0d366b'])


def load(name):
    path = os.path.join(RUN, name, 'results.json')
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def combine(runs):
    """L_k, D_k and the closure of the three drives, in nH, from {drive: results}."""
    out = {}
    for k in PHASES:
        m = {d: runs[d]['sense'][k]['m_nH'] for d in sc.DRIVES}
        own_in = k + NEXT[k]                  # drive in on k
        own_back = PREV[k] + k                # drive back on k
        other = NEXT[k] + PREV[k]             # drive that does not go through k
        out[k] = {'L': (m[own_in] - m[own_back]) / 2, 'D': m[other] / 2, 'closure': sum(m.values()),
                  'm': m, 'D_from': (NEXT[k], PREV[k])}
    return out


# ----------------------------------------------------------------------------- flux through the Kelvin loop

def read_dump(sim, name):
    with h5py.File(os.path.join(sim, name + '.h5'), 'r') as h5:
        mesh = [h5['Mesh'][a][...] * 1e3 for a in 'xyz']
        h = h5['FieldData/FD/f0_real'][...] + 1j * h5['FieldData/FD/f0_imag'][...]
    return mesh, h


def widths(centres, lines):
    """Width of the mesh cell around each cell centre of a dump."""
    i = np.searchsorted(lines, centres)
    return lines[i] - lines[i - 1]


def flux_shares(run, sim, mesh):
    """Flux through the Kelvin loop of the two driven shunts, split into its parts, as M in nH.

    The loop runs up the U pin on the J1 side, along the body, down the other U pin and back along
    the L6 tracks through the INA241: its surface is the window between the two U pins, below the
    body (normal +y), and on L6 the quadrilateral between the pins and the INA241 leads (normal +z).
    """
    f = np.array(run['f'])
    i_drive = np.interp(sc.F_FIELD, f, run['i_drive'][0]) + 1j * np.interp(sc.F_FIELD, f, run['i_drive'][1])
    a, b = run['drive']
    out = {}
    (lx, ly, lz), h6 = read_dump(sim, 'H_L6')
    for k, sign in ((a, 1), (b, -1)):
        g = run['geometry'][k]
        x2, x3 = g['x_pads'][1], g['x_pads'][2]
        (px, _, pz), hp = read_dump(sim, 'H_plane_' + k)
        hy = hp[1, :, 0, :]                                          # (z, x)
        dx, dz = widths(px, mesh['x']), widths(pz, mesh['z'])
        in_x = (px > x2) & (px < x3)
        parts = {}
        for name, z0, z1 in (('board', 0.0, g['z_top']), ('standoff', g['z_top'], g['z_body'])):
            sel = np.outer((pz > z0) & (pz < z1), in_x)
            parts[name] = MU0 * np.sum((hy * np.outer(dz, dx) * 1e-6)[sel])
        (x8, y8), (x1, y1) = g['xy_ina']
        quad = Polygon([(x2, g['y_pin']), (x3, g['y_pin']), (x8, y8), (x1, y1)]).get_path()
        X, Y = np.meshgrid(lx, ly)
        sel = quad.contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
        area = np.outer(widths(ly, mesh['y']), widths(lx, mesh['x'])) * 1e-6
        parts['tracks'] = MU0 * np.sum((h6[2, 0, :, :] * area)[sel])
        i_k = sign * i_drive
        out[k] = {p: float((v / i_k).real * 1e9) for p, v in parts.items()}
        out[k]['total'] = sum(out[k].values())
        out[k]['port'] = run['sense'][k]['m_nH'] * sign
    return out


# ----------------------------------------------------------------------------- filament bracket

def filament_bracket(run):
    """L_U from thin wires, for the two extreme ways the current can cross the PBV body.

    Sense loop: the window between the U pins, from L6 to the body. Each phase: along the middle of
    the board from J1 to its I pin, up, across the body, down, on to J2. The body current runs either
    along its bottom edge or spread evenly over its 17.5 mm height. Neumann integral of the open
    current paths with the closed sense loop, combined like the openEMS drives (L_U = M_UU - mean of
    the other two). Returns {label: nH}.
    """
    g = {k: run['geometry'][k] for k in PHASES}
    xp, zb, zm = g['U']['x_pads'], g['U']['z_body'], g['U']['z_top'] / 2
    x_conn = 16.3                                     # J1 / J2 pins

    def segs(points, n=300):
        p, d = [], []
        for a, b in zip(points[:-1], points[1:]):
            a, b = np.array(a) * 1e-3, np.array(b) * 1e-3
            t = (np.arange(n) + 0.5) / n
            p.append(a + np.outer(t, b - a)); d.append(np.tile((b - a) / n, (n, 1)))
        return np.vstack(p), np.vstack(d)

    def mutual(c1, c2):
        (p1, d1), (p2, d2) = c1, c2
        r = np.maximum(np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=2), 0.2e-3)
        return MU0 / (4 * np.pi) * np.sum((d1 @ d2.T) / r)

    y0 = g['U']['y_pin']
    sense = segs([(xp[1], y0, 0), (xp[1], y0, zb), (xp[2], y0, zb), (xp[2], y0, 0), (xp[1], y0, 0)])
    out = {}
    for label, heights in (('along the bottom of the body', [zb + 0.3]),
                           ('spread over the height of the body', np.linspace(zb + 0.4, zb + sc.PBV_HEIGHT - 0.4, 12))):
        m = {}
        for k in PHASES:
            y = g[k]['y_pin']
            m[k] = np.mean([mutual(segs([(-x_conn, y, zm), (xp[0], y, zm), (xp[0], y, h), (xp[3], y, h),
                                         (xp[3], y, zm), (x_conn, y, zm)]), sense) for h in heights])
        out[label] = (m['U'] - (m['V'] + m['W']) / 2) * 1e9
    return out


# ----------------------------------------------------------------------------- LTspice simulation 07

def ltspice_power():
    """Shunt inductance (nH) -> phase power error after DC calibration, and with a time shift (%)."""
    rows = []
    with open(LTSPICE_MD, encoding='utf-8') as f:
        for line in f:
            m = re.match(r'\| (\d+) nH \|(.*)', line)
            if m and line.count('|') == 8:
                cells = [c.strip() for c in m.group(2).split('|')]
                rows.append((float(m.group(1)), float(cells[4].rstrip(' %')), float(cells[5].rstrip(' %'))))
    return np.array(sorted(rows))


# ----------------------------------------------------------------------------- figures

def fig_field(sim, run, mesh):
    """|H| per ampere of phase current in the plane of shunt U, and seen from above at mid standoff."""
    f = np.array(run['f'])
    i_drive = abs(np.interp(sc.F_FIELD, f, run['i_drive'][0]) + 1j * np.interp(sc.F_FIELD, f, run['i_drive'][1]))
    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 6.2), gridspec_kw={'width_ratios': [1.0, 1.25]})
    norm = LogNorm(vmin=3, vmax=3e3)

    (px, _, pz), hp = read_dump(sim, 'H_plane_U')
    mag = np.sqrt(np.sum(np.abs(hp[:, :, 0, :]) ** 2, axis=0)) / i_drive
    im = a.pcolormesh(px, pz, mag, cmap=BLUES, norm=norm, shading='nearest', rasterized=True)
    g = run['geometry']['U']
    xp, zt, zb = g['x_pads'], g['z_top'], g['z_body']
    a.add_patch(Rectangle((px[0], 0), px[-1] - px[0], zt, fc='#cfd8c4', ec='none', alpha=0.6, zorder=2))
    a.add_patch(Rectangle((xp[0] - sc.PBV_OVERHANG, zb), xp[3] - xp[0] + 2 * sc.PBV_OVERHANG, sc.PBV_HEIGHT,
                          fc='none', ec=INK, lw=1.4, zorder=3))
    for x, (_, wpin) in zip(xp, sc.PBV_PINS):
        a.add_patch(Rectangle((x - wpin / 2, 0), wpin, zb, fc=INK2, ec='none', zorder=3))
    a.add_patch(Rectangle((xp[1], 0), xp[2] - xp[1], zb, fc='none', ec=C2, lw=2, ls='--', zorder=4))
    a.annotate('Kelvin window\nread by the INA241', (0.5 * (xp[1] + xp[2]), zb * 0.5), xytext=(0.5 * (xp[1] + xp[2]), zb + 4),
               ha='center', va='center', color=C2, fontsize=9, fontweight='bold', zorder=5,
               arrowprops=dict(arrowstyle='->', color=C2, lw=1.5))
    a.text(xp[0], -1.2, 'I', ha='center', color=INK2); a.text(xp[3], -1.2, 'I', ha='center', color=INK2)
    a.text(xp[1], -1.2, 'U', ha='center', color=INK2); a.text(xp[2], -1.2, 'U', ha='center', color=INK2)
    a.text(0.5 * (xp[0] + xp[3]), zb + sc.PBV_HEIGHT - 2, 'R1 (PBV), foil model', ha='center', color=INK, fontsize=9)
    a.set_xlim(px[0], px[-1]); a.set_ylim(pz[0], pz[-1]); a.set_aspect('equal')
    a.set_xlabel('x (mm, board centre = 0)'); a.set_ylabel('height above the bottom copper (mm)')
    a.set_title('Phase U shunt, seen from the side')
    a.grid(False)

    (hx, hy_, _), hh = read_dump(sim, 'H_above')
    mag = np.sqrt(np.sum(np.abs(hh[:, 0, :, :]) ** 2, axis=0)) / i_drive
    b.pcolormesh(hx, hy_, mag, cmap=BLUES, norm=norm, shading='nearest', rasterized=True)
    for k in PHASES:
        gk = run['geometry'][k]
        x0, x3 = gk['x_pads'][0] - sc.PBV_OVERHANG, gk['x_pads'][3] + sc.PBV_OVERHANG
        b.add_patch(Rectangle((x0, gk['y_pin'] - 1.9), x3 - x0, 4.44, fc='none', ec=INK, lw=1.2))
        b.text(x3 + 0.6, gk['y_pin'], {'U': 'R1', 'V': 'R4', 'W': 'R7'}[k], va='center', fontsize=9)
    a_, b_ = run['drive']
    yu, yv = run['geometry'][a_]['y_pin'], run['geometry'][b_]['y_pin']
    b.annotate('', xy=(10, yu - 2.8), xytext=(-10, yu - 2.8), arrowprops=dict(arrowstyle='->', color=C2, lw=2))
    b.annotate('', xy=(-10, yv - 2.8), xytext=(10, yv - 2.8), arrowprops=dict(arrowstyle='->', color=C2, lw=2))
    b.text(0, yu - 3.6, '1 A, phase %s' % a_, ha='center', va='top', color=C2, fontsize=9, fontweight='bold')
    b.text(0, yv - 3.6, '1 A back, phase %s' % b_, ha='center', va='top', color=C2, fontsize=9, fontweight='bold')
    b.text(-19.5, -14, 'J1 (ESC)', fontsize=9, color=INK2); b.text(14.5, -14, 'J2 (motor)', fontsize=9, color=INK2)
    b.set_xlim(hx[0], hx[-1]); b.set_ylim(hy_[0], hy_[-1]); b.set_aspect('equal')
    b.set_xlabel('x (mm)'); b.set_ylabel('y (mm)')
    b.set_title('Seen from above, %.1f mm over the board' % sc.I_PROBE_Z)
    b.grid(False)
    cb = fig.colorbar(im, ax=[a, b], shrink=0.85, pad=0.02)
    cb.set_label('|H| per ampere of phase current (A/m per A), %g MHz' % (sc.F_FIELD / 1e6))
    fig.suptitle('openEMS: magnetic field of the phase current around the PBV shunts (current in on U, back on V)',
                 fontweight='bold', x=0.45)
    plotstyle.save(fig, 'openems_shunt_field.png')


def fig_inductance(results, spectra, shares, power, mesh_check):
    fig, axs = plt.subplots(2, 2, figsize=(14, 9.5))
    a, b, c, d = axs.ravel()

    # (a) flat m(f): the coupling is a plain inductance over the band
    colours = {'U': C1, 'V': C2, 'W': C3}
    styles = {'UV': '-', 'VW': '--', 'WU': ':'}
    for drive, run in spectra.items():
        f = np.array(run['f'])
        for k in PHASES:
            m = np.array(run['sense'][k]['im']) / (2 * np.pi * f) * 1e9
            a.plot(f / 1e6, m, styles[drive], color=colours[k], lw=1.6)
    a.axvspan(*[v / 1e6 for v in sc.F_FIT], color=GRID, alpha=0.5, lw=0)
    a.text(np.sqrt(sc.F_FIT[0] * sc.F_FIT[1]) / 1e6, 0.97, 'band read', transform=a.get_xaxis_transform(),
           ha='center', va='top', color=INK2, fontsize=9)
    a.set_xscale('log')
    a.set_xlabel('Frequency (MHz)'); a.set_ylabel('Im(V / I) / ω (nH)')
    a.set_title('Voltage at each INA241 input per ampere driven (foil model)')
    handles = [plt.Line2D([], [], color=colours[k], lw=2, label='input %s (%s)' % (k, sc.INA[k])) for k in PHASES]
    handles += [plt.Line2D([], [], color=INK2, ls=s, lw=1.6, label='current in on %s, back on %s' % (dr[0], dr[1]))
                for dr, s in styles.items()]
    a.legend(handles=handles, fontsize=8.5, ncol=2, loc='center left')

    # (b) inductance per phase, both body models, against the datasheet bound and the LTspice steps
    x = np.arange(3)
    for n, (case, label) in enumerate(CASES.items()):
        if case not in results:
            continue
        r = results[case]
        bars = b.bar(x + (n - 0.5) * 0.36, [r[k]['L'] for k in PHASES], 0.34, color=[C1, C4][n], label=label)
        for bar, k in zip(bars, PHASES):
            b.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.12, '%.2f' % r[k]['L'],
                   ha='center', va='bottom', fontsize=9)
        b.errorbar(x + (n - 0.5) * 0.36, [abs(r[k]['D']) for k in PHASES], fmt='_', ms=22, mew=2.4,
                   color=INK, ls='none', label='coupling from the other phases |D|' if n == 0 else None)
    b.axhline(10, color=C2, lw=1.5, ls='--')
    b.text(2.55, 10.15, 'datasheet: < 10 nH', ha='right', va='bottom', color=C2, fontsize=9)
    for v in (5,):
        b.axhline(v, color=INK2, lw=1, ls=':')
        b.text(2.55, v + 0.15, 'LTspice 07 middle step', ha='right', va='bottom', color=INK2, fontsize=8.5)
    if mesh_check:
        b.plot([mesh_check['x']], [mesh_check['L']], 'o', color=INK, mfc='none', ms=8,
               label='same, mesh 0.15 mm' if mesh_check else None)
    b.set_xticks(x, ['%s (R1 / IC2)' % 'U', 'V (R4 / IC4)', 'W (R7 / IC6)'])
    b.set_ylabel('nH'); b.set_ylim(0, 13.5)                # the legend stays above the datasheet line
    b.set_title('Inductance of each shunt as its INA241 reads it')
    b.legend(fontsize=8.5, loc='upper left')

    # (c) where the flux comes from
    if shares:
        parts = [('standoff', 'under the body, above the board', C1), ('board', 'inside the board (1.41 mm)', C3),
                 ('tracks', 'Kelvin tracks on L6', C4)]
        ks = list(shares)
        left = np.zeros(len(ks))
        handles = [Patch(color=col, label=label) for _, label, col in parts]
        handles.append(Patch(fc='none', ec=INK2, hatch='////', label='negative part (subtracted)'))
        for key, label, col in parts:
            v = np.array([shares[k][key] for k in ks])
            # a negative part is drawn hatched, back over the parts before it
            for y_, l_, v_ in zip(range(len(ks)), left, v):
                if v_ >= 0:
                    c.barh(y_, v_, left=l_, color=col, height=0.5)
                else:
                    c.barh(y_, -v_, left=l_ + v_, fc='none', ec=col, hatch='////', lw=1.2, height=0.5)
                if abs(v_) > 0.25:
                    c.text(l_ + v_ / 2, y_, '%.2f' % v_, ha='center', va='center', color='white', fontsize=9, fontweight='bold')
            left += v
        for y_, k in enumerate(ks):
            c.plot(shares[k]['total'], y_, '|', color=INK2, ms=26, mew=2)
            c.plot(shares[k]['port'], y_, 'D', color=INK, ms=7)
        handles += [plt.Line2D([], [], marker='|', ls='none', color=INK2, ms=12, mew=2, label='sum of the parts'),
                    plt.Line2D([], [], marker='D', ls='none', color=INK, ms=7, label='read at the port')]
        c.set_yticks(range(len(ks)), ['input %s' % k for k in ks])
        c.set_ylim(-0.45, len(ks) - 0.55)
        c.set_xlabel('nH, current in on %s and back on %s (foil model)' % tuple(spectra['UV']['drive']))
        c.set_title('Where the flux read by the INA241 goes through')
        c.legend(handles=handles, fontsize=8.5, loc='center', ncol=2)      # in the gap between the two bars

    # (d) what it does to the phase power, from LTspice simulation 07
    if power is not None and len(power):
        lgrid = np.linspace(0, 10, 101)
        d.plot(lgrid, np.interp(lgrid, power[:, 0], power[:, 1]), color=C1, label='after DC calibration')
        d.plot(lgrid, np.interp(lgrid, power[:, 0], power[:, 2]), color=C3, label='DC calibration + time shift of the current')
        d.plot(power[:, 0], power[:, 1], 'o', color=C1); d.plot(power[:, 0], power[:, 2], 'o', color=C3)
        lo = min(r[k]['L'] for r in results.values() for k in PHASES)
        hi = max(r[k]['L'] for r in results.values() for k in PHASES)
        d.axvspan(lo, hi, color=C4, alpha=0.25, lw=0)
        d.text((lo + hi) / 2, 0.97, 'openEMS\n%.1f - %.1f nH' % (lo, hi), transform=d.get_xaxis_transform(),
               ha='center', va='top', fontsize=9, fontweight='bold')
        d.axhline(0, color=INK2, lw=1)
        d.set_xlabel('Inductance of the shunt (nH)'); d.set_ylabel('Phase power error (%)')
        d.set_title('LTspice 07: phase power read under PWM')
        d.legend(fontsize=8.5, loc='lower right')
    fig.tight_layout()
    plotstyle.save(fig, 'openems_shunt_inductance.png')


# ----------------------------------------------------------------------------- results.md

def write_md(results, shares, power, mesh_check, raw, bracket):
    fmt = lambda v: '%.2f' % v
    md = ['# openEMS results (generated by report.py)', '',
          'Inductance of the PBV-R001 shunts as the INA241 inputs read it, computed on the routed copper '
          '(shunt_coupling.py; method checked by validate_mutual.py). What input k reads, with the three phase currents summing to zero:', '',
          '    V_k = R I_k + jw (L_k I_k + D_k (I_p - I_q))      (k, p, q) = (U, V, W), (V, W, U), (W, U, V)', '',
          'R = 1 mOhm comes from the datasheet: the copper model has no resistance. L_k does not depend on how the current '
          'returns through the other two phases; D_k is the coupling from them.', '']
    md += ['## Inductance per phase', '',
           '| Phase (shunt / amplifier) | L, foil model (nH) | L, body with a metal back (nH) | D, foil model (nH) | R = jwL at |',
           '| --- | --- | --- | --- | --- |']
    for k in PHASES:
        lf = results['foil'][k]['L']
        lb = results['backed'][k]['L'] if 'backed' in results else float('nan')
        md.append('| %s (%s / %s) | %s | %s | %+.2f (I_%s - I_%s) | %.0f kHz |' % (
            k, sc.SHUNT[k], sc.INA[k], fmt(lf), fmt(lb), results['foil'][k]['D'], *results['foil'][k]['D_from'],
            1e-3 / (2 * np.pi * lf * 1e-9) / 1e3))
    md += ['', 'The last column is where the inductive part equals the 1 mOhm (foil model): above it, the reading '
           'follows dI/dt more than I. The PWM runs at 24 kHz in simulation 07.', '']
    if shares:
        md += ['## Where the flux goes through (foil model, current in on %s, back on %s)' % tuple(raw['foil']['UV']['drive']), '',
               '| Input | Under the body, above the board | Inside the board | Kelvin tracks on L6 | Sum | Read at the port |',
               '| --- | --- | --- | --- | --- | --- |']
        for k, s in shares.items():
            md.append('| %s | %s nH | %s nH | %s nH | %s nH | %s nH |' % (
                k, fmt(s['standoff']), fmt(s['board']), fmt(s['tracks']), fmt(s['total']), fmt(s['port'])))
        md += ['', 'Integral of the H field over the surface of the loop at %g MHz. The field maps are about 2 %% low '
               '(validate_mutual.py); the sum is compared with the port reading as a check.' % (sc.F_FIELD / 1e6), '']
    if power is not None and len(power):
        md += ['## Effect on the phase power (LTspice simulation 07)', '',
               'Phase power error under PWM read at the inductance found, interpolated between the 0, 5 and 10 nH runs '
               'of simulation 07 (Simulation/LTspice/measurement_quality.md).', '',
               '| Phase | Body model | L (nH) | After DC calibration | DC calibration + time shift of the current |',
               '| --- | --- | --- | --- | --- |']
        for case, r in results.items():
            for k in PHASES:
                l_ = r[k]['L']
                md.append('| %s | %s | %s | %+.1f %% | %+.1f %% |' % (
                    k, CASES[case].replace('Body = ', '').replace('Body with', 'with'), fmt(l_),
                    np.interp(l_, power[:, 0], power[:, 1]), np.interp(l_, power[:, 0], power[:, 2])))
        md.append('')
    md += ['## Raw readings', '',
           'm = Im(V / I) / w in nH, median over %g - %g MHz, I driven in at J1 on the first phase and back on the second.' % (
               sc.F_FIT[0] / 1e6, sc.F_FIT[1] / 1e6), '',
           '| Body model | Drive | Input U | Input V | Input W |', '| --- | --- | --- | --- | --- |']
    for case, runs in raw.items():
        for drive, run in runs.items():
            md.append('| %s | %s | %s |' % (case, drive, ' | '.join('%.3f' % run['sense'][k]['m_nH'] for k in PHASES)))
    md += ['', '## Checks', '']
    for case, r in results.items():
        md.append('- %s: the three drives add up to %s nH on inputs U / V / W (should be 0).' % (
            CASES[case], ' / '.join('%+.3f' % r[k]['closure'] for k in PHASES)))
        spread = max(run['sense'][k]['spread'] for run in raw[case].values() for k in PHASES)
        ratio = max(run['sense'][k]['re_over_im'] for run in raw[case].values() for k in PHASES)
        md.append('  m varies by %.1f %% at most over the band and the real part stays below %.1f %% of the imaginary one: '
                  'a plain inductance.' % (100 * spread, 100 * ratio))
    if mesh_check:
        md.append('- Mesh: with 0.15 mm instead of 0.2 mm in the fine window (drive UV, foil model), the inputs read '
                  '%s nH: the inductances above hold to about %.0f %%.' % (
                      ', '.join('%s %.3f instead of %.3f' % (q, f, m) for q, (m, f) in mesh_check['all'].items()),
                      100 * max(abs(f / m - 1) for q, (m, f) in mesh_check['all'].items() if abs(m) > 1)))
    run = raw['foil']['UV']
    pins = []
    for k in run['drive']:
        ref = sc.SHUNT[k]
        f = np.array(run['f'])
        band = (f >= sc.F_FIT[0]) & (f <= sc.F_FIT[1])
        pins.append('%s %+.3f / %+.3f' % (ref, *(np.median(np.array(run['pins']['%s.%s' % (ref, n)][0])[band]) for n in '14')))
    md.append('- The drive current goes through the shunts of the driven phases (current up pin 1 / up pin 4, per '
              'ampere driven, drive UV): %s.' % ', '.join(pins))
    md.append('- validate_mutual.py: two loops in one plane, openEMS within 1.2 % of the Neumann integral.')
    md.append('- Thin-wire bracket for input U (filament_bracket), the body current running %s.' % ', or '.join(
        '%s: %.2f nH' % kv for kv in bracket.items()))
    md.append('')
    with open(os.path.join(HERE, 'results.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('  results.md written')


def main():
    raw = {case: {d: load(sc.run_name(case, d, 0.2)) for d in sc.DRIVES} for case in CASES}
    raw = {case: runs for case, runs in raw.items() if all(runs.values())}
    if 'foil' not in raw:
        print('run shunt_coupling.py first (the foil model needs the three drives)')
        return 1
    results = {case: combine(runs) for case, runs in raw.items()}
    for case, r in results.items():
        print('%s:' % CASES[case])
        for k in PHASES:
            print('  %s: L = %.3f nH, D = %+.3f nH, closure %+.4f nH' % (k, r[k]['L'], r[k]['D'], r[k]['closure']))

    geom = sc.load_geometry()
    sc.RES = 0.2
    mesh = sc.build_mesh(geom)
    sim = os.path.join(RUN, sc.run_name('foil', 'UV', 0.2))
    shares = flux_shares(raw['foil']['UV'], sim, mesh) if os.path.exists(os.path.join(sim, 'H_L6.h5')) else None
    if shares:
        for k, s in shares.items():
            print('  flux %s: %s' % (k, ', '.join('%s %.3f' % kv for kv in s.items())))
    fine = load(sc.run_name('foil', 'UV', 0.15))
    mesh_check = None
    if fine:
        k = 'U'
        m, m_fine = raw['foil']['UV']['sense'][k]['m_nH'], fine['sense'][k]['m_nH']
        mesh_check = {'k': k, 'm': m, 'm_fine': m_fine, 'x': 0 - 0.18,
                      'L': results['foil'][k]['L'] * m_fine / m,
                      'all': {q: (raw['foil']['UV']['sense'][q]['m_nH'], fine['sense'][q]['m_nH']) for q in PHASES}}
    power = ltspice_power() if os.path.exists(LTSPICE_MD) else None
    if shares:
        fig_field(sim, raw['foil']['UV'], mesh)
    fig_inductance(results, raw['foil'], shares, power, mesh_check)
    bracket = filament_bracket(raw['foil']['UV'])
    print('  thin wires: %s' % ', '.join('%s %.2f nH' % kv for kv in bracket.items()))
    write_md(results, shares, power, mesh_check, raw, bracket)
    return 0


if __name__ == '__main__':
    sys.exit(main())
