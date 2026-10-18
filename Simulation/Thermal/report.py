"""Figures and results.md from the output of power_paths.py (results.json, fields.npz).

    C:\\openEMS\\venv\\Scripts\\python.exe report.py

The figures go to ../../Images/Simulation/.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'LTspice')))
import plotstyle  # noqa: E402
from plotstyle import C1, C2, C3, C4, INK, INK2, SURFACE, plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

import power_paths as pp  # noqa: E402

BLUES = LinearSegmentedColormap.from_list('blues', [SURFACE, '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5',
                                                    '#256abf', '#184f95', '#0d366b'])
HEAT = LinearSegmentedColormap.from_list('heat', ['#fff7e8', '#fde3b0', '#f8c26a', C4, '#ef8a2c', C2,
                                                  '#c4441c', '#7a1f0a'])
PHASE_COL = {'U': C1, 'V': C2, 'W': C3}


def load():
    with open(pp.RESULTS) as f:
        res = json.load(f)
    fields = dict(np.load(pp.FIELDS))
    return res, fields


def draw_parts(ax, geom, labels=True, bottom=False):
    """Pins of J1, J2 and the shunts, the PBV bodies, the INA241 (bottom side) as markers."""
    for p in geom['pads']:
        if p['ref'] in (pp.ESC_SIDE, pp.MOTOR_SIDE) + tuple(pp.SHUNT.values()) and p['drill'] > 0:
            ax.add_patch(Circle(p['xy'], p['drill'] / 2, fc='none', ec=INK, lw=0.9, zorder=4))
    for k, ref in pp.SHUNT.items():
        xs = [p['xy'][0] for p in geom['pads'] if p['ref'] == ref]
        y = next(p['xy'][1] for p in geom['pads'] if p['ref'] == ref)
        x0 = min(xs) - 2.36
        ax.add_patch(Rectangle((x0, y - 1.9), 22.5, 4.44, fc='none', ec=INK, lw=0.9, ls='--' if bottom else '-', zorder=4))
        if labels:
            ax.text(x0 + 22.5 + 0.5, y, ref, va='center', fontsize=8.5, color=INK)
    for k, ref in pp.INA.items():
        part = next(p for p in geom['parts'] if p['ref'] == ref)
        ax.add_patch(Rectangle((part['xy'][0] - 1.5, part['xy'][1] - 1.5), 3.0, 3.0, fc='none', ec=INK2, lw=0.9,
                               ls='-' if bottom else ':', zorder=4))
        if labels and bottom:
            ax.text(part['xy'][0], part['xy'][1] + 1.9, ref, ha='center', va='bottom', fontsize=7.5, color=INK2)
    if labels:
        for ref, dx in ((pp.ESC_SIDE, -1), (pp.MOTOR_SIDE, 1)):
            ys = [p['xy'] for p in geom['pads'] if p['ref'] == ref and p['net'] != 'GND']
            x = ys[0][0]
            ax.text(x + dx * 3.2, max(y for _, y in ys) + 3.2, '%s\n(%s)' % (ref, 'ESC' if ref == pp.ESC_SIDE else 'motor'),
                    ha='center', va='bottom', fontsize=8.5, color=INK)


# ----------------------------------------------------------------------------- figures

def fig_current(res, fields, geom):
    main = res['main']['board']
    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 5.6), gridspec_kw={'width_ratios': [1.45, 1.0]})
    ex, ey = fields['ex'], fields['ey']
    j = np.ma.masked_where(fields['own_e'][0] < 0, fields['J_board'][0])
    im = a.pcolormesh(ex, ey, j.T, cmap=BLUES, norm=LogNorm(vmin=1, vmax=100), shading='nearest', rasterized=True)
    draw_parts(a, geom)
    a.set_aspect('equal'); a.set_xlim(ex[0], ex[-1]); a.set_ylim(ey[0], ey[-1] + 4.5)
    a.set_xlabel('x (mm, board centre = 0)'); a.set_ylabel('y (mm)')
    a.set_title('Current density on L1 (F.Cu, 70 um), %.0f A rms in each phase' % main['I'])
    a.grid(False)
    cb = fig.colorbar(im, ax=a, shrink=0.8, pad=0.02)
    cb.set_label('A/mm2')
    share = main['paths']['U']['shares']['IN-U']
    a.text(0.0, 0.99, 'every layer carries its share of copper: L1 %.0f %%, L2 %.0f %%, L3 %.0f %%, L6 %.0f %%'
           % tuple(100 * s for s in share), transform=a.transAxes, ha='left', va='top', fontsize=8.5, color=INK2)

    # where the heat comes from, per phase
    ks = list(pp.PHASES)
    rows = [('P_in', 'copper J1 to shunt', C1), ('P_shunt', 'shunt (1 mOhm)', C4), ('P_out', 'copper shunt to J2', C3)]
    left = np.zeros(3)
    for key, label, col in rows:
        v = np.array([main['paths'][k][key] for k in ks])
        b.barh(ks, v, left=left, color=col, label=label, height=0.55)
        for y_, l_, v_ in zip(range(3), left, v):
            if v_ > 0.15:
                b.text(l_ + v_ / 2, y_, '%.2f' % v_, ha='center', va='center', color='white', fontsize=9, fontweight='bold')
        left += v
    pc = res['main']['contacts']['P_contacts'] / 3
    b.barh(ks, [pc] * 3, left=left, color='none', ec=C2, hatch='////', label='MR60PW contacts at 1.0 mOhm, half to the board',
           height=0.55)
    for y_, k in enumerate(ks):
        p = main['paths'][k]
        b.text(left[y_] + pc + 0.05, y_, '%.3f + %.3f mOhm' % (p['R_in'] * 1e3, p['R_out'] * 1e3), va='center',
               fontsize=8.5, color=INK2)
    b.set_yticks(range(3), ['phase %s\n(%s)' % (k, pp.SHUNT[k]) for k in ks])
    b.invert_yaxis()
    b.set_xlim(0, left.max() + pc + 1.1)
    b.set_xlabel('W per phase at %.0f A rms' % main['I'])
    b.set_title('Where the heat comes from (copper paths: resistance J1-shunt + shunt-J2)')
    b.legend(fontsize=8.5, loc='upper center', bbox_to_anchor=(0.5, -0.13), ncol=2)
    plotstyle.save(fig, 'thermal_current_density.png')


def fig_temperature(res, fields, geom):
    tx, ty = fields['tx'], fields['ty']
    t_lo = pp.T_AMB
    t_hi = max(float(fields['T_' + c].max()) for c in pp.CASES)
    fig, axs = plt.subplots(1, 2, figsize=(15, 7.4))
    norm = Normalize(vmin=t_lo, vmax=np.ceil(t_hi / 5) * 5)
    for a, case in zip(axs, pp.CASES):
        s = res['main'][case]
        t = fields['T_' + case]
        im = a.pcolormesh(tx, ty, t[0].T, cmap=HEAT, norm=norm, shading='nearest', rasterized=True)
        cs = a.contour(tx, ty, t[0].T, levels=np.arange(30, 200, 5), colors=INK2, linewidths=0.4, alpha=0.6)
        a.clabel(cs, fmt='%d', fontsize=7)
        draw_parts(a, geom)
        hot = max(s['layers'], key=lambda ly: ly['t_max'])
        a.plot(*hot['xy'], 'x', color=INK, ms=9, mew=2, zorder=5)
        a.annotate('%.0f C' % hot['t_max'], hot['xy'], xytext=(hot['xy'][0] + 4, hot['xy'][1] - 3.5), fontsize=9,
                   fontweight='bold', arrowprops=dict(arrowstyle='-', color=INK, lw=0.8))
        a.set_aspect('equal'); a.set_xlim(tx[0], tx[-1]); a.set_ylim(ty[0], ty[-1])
        a.set_xlabel('x (mm)'); a.set_ylabel('y (mm)')
        a.set_title('%s: top face, %.1f W in the board' % (pp.CASES[case], s['P_total']))
        a.grid(False)
        lines = ['phase %s: PBV terminal %.0f C, %s %.0f C' % (k, ph['t_terminal'], pp.INA[k], ph['t_ina'])
                 for k, ph in s['phases'].items()]
        a.text(0.02, 0.98, '\n'.join(['mean of the board %.0f C' % s['layers'][0]['t_mean']] + lines),
               transform=a.transAxes, ha='left', va='top', fontsize=8.5, color=INK, zorder=10,
               bbox=dict(fc=SURFACE, ec='none', alpha=0.9))
    cb = fig.colorbar(im, ax=axs, shrink=0.75, pad=0.02)
    cb.set_label('C (still air at %.0f C, %.0f A rms in each phase)' % (pp.T_AMB, res['main']['board']['I']))
    d = np.abs(fields['T_board'][0] - fields['T_board'][3])
    fig.suptitle('Temperature of the board, steady state. The bottom face follows the top one within %.1f K on 99 %% '
                 'of the board,\nup to %.0f K hotter along the Kelvin tracks of L6 that the shunt bodies heat through '
                 'their U pins' % (np.percentile(d, 99), d.max()), fontweight='bold', x=0.45)
    plotstyle.save(fig, 'thermal_temperature.png')


def probe(s, what):
    ph = s['phases'].values()
    return {'terminal': max(p['t_terminal'] for p in ph),
            'connector': max(max(p['pins'][pp.ESC_SIDE], p['pins'][pp.MOTOR_SIDE]) for p in ph),
            'ina': max(p['t_ina'] for p in ph),
            'mean': s['layers'][0]['t_mean']}[what]


def fig_sweep(res):
    fig, a = plt.subplots(figsize=(10, 6))
    what = [('terminal', 'PBV terminal (hottest shunt)', C2), ('connector', 'MR60PW pin (hottest)', C1),
            ('ina', 'INA241 (hottest)', C3), ('mean', 'board mean', INK2)]
    for case, ls in (('board', '-'), ('contacts', '--')):
        sw = res['sweep'][case]
        i = [s['I'] for s in sw]
        for key, label, col in what:
            a.plot(i, [probe(s, key) for s in sw], ls, color=col, lw=2,
                   label=label if case == 'board' else None, marker='o', ms=3.5)
    ig = np.linspace(min(pp.SWEEP), max(pp.SWEEP), 200)
    a.plot(ig, [pp.pbv_limit(x) for x in ig], ':', color=C2, lw=2, label='PBV limit (derating without heatsink)')
    a.axhline(pp.T_MR60_MAX, color=C1, ls=':', lw=2, label='MR60PW limit (120 C)')
    a.axvline(pp.I_MR60, color=INK2, lw=1)
    a.text(pp.I_MR60 + 0.4, a.get_ylim()[0] + 3, 'MR60PW rating %.0f A' % pp.I_MR60, rotation=90, va='bottom',
           fontsize=8.5, color=INK2)
    a.plot([], [], '-', color=INK, label='copper and shunts')
    a.plot([], [], '--', color=INK, label='plus MR60PW contacts at 1.0 mOhm')
    a.set_xlabel('RMS current in each of the three phases (A)'); a.set_ylabel('C (still air at %.0f C)' % pp.T_AMB)
    a.set_title('Steady temperature against the phase current')
    a.legend(fontsize=8.5, loc='upper left', ncol=2)
    plotstyle.save(fig, 'thermal_vs_current.png')


# ----------------------------------------------------------------------------- results.md

def crossing(sweep, key, limit):
    """Current where a probe meets a limit (a number or a function of the current), by interpolation."""
    i = np.array([s['I'] for s in sweep])
    margin = np.array([(limit(s['I']) if callable(limit) else limit) - probe(s, key) for s in sweep])
    k = np.nonzero(margin < 0)[0]
    if not len(k):
        return None
    k = k[0]
    if k == 0:
        return float(i[0])
    return float(i[k - 1] + (i[k] - i[k - 1]) * margin[k - 1] / (margin[k - 1] - margin[k]))


def write_md(res, fields, geom):
    b, c = res['main']['board'], res['main']['contacts']

    def where(xy):
        """The pin of J1, J2 or a shunt nearest to a point."""
        refs = (pp.ESC_SIDE, pp.MOTOR_SIDE) + tuple(pp.SHUNT.values())
        p = min((p for p in geom['pads'] if p['ref'] in refs),
                key=lambda p: np.hypot(p['xy'][0] - xy[0], p['xy'][1] - xy[1]))
        return '%s pin %s, net %s' % (p['ref'], p['pad'], p['net'])

    def kelvin_rise():
        return float(np.abs(fields['T_board'][0] - fields['T_board'][3]).max())

    md = ['# Current and temperature of the motor phase paths (generated by report.py)', '',
          'DC current in the six phase pours (J1 to shunt, shunt to J2) on the routed copper and steady temperature '
          'of the whole board, %.0f A rms in each of the three phases, still air at %.0f C, board horizontal '
          '(power_paths.py; solvers checked by validate_solver.py). The RMS current sets the heat whatever the '
          'waveform.' % (b['I'], pp.T_AMB), '',
          '## Current paths at %.0f A rms' % b['I'], '',
          '| Phase | R J1 to shunt | R shunt to J2 | Drop over the copper | Copper loss | Shunt loss | Densest current (outside the vias) | Most current in one via |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for k, p in b['paths'].items():
        md.append('| %s (%s) | %.3f mOhm | %.3f mOhm | %.1f mV | %.2f W | %.2f W | %.0f A/mm2 | %.2f A |' % (
            k, pp.SHUNT[k], p['R_in'] * 1e3, p['R_out'] * 1e3, (p['R_in'] + p['R_out']) * p['I'] * 1e3,
            p['P_in'] + p['P_out'], p['P_shunt'], max(p['j_max']), max(p['via_max'])))
    sh = b['paths']['U']['shares']['IN-U']
    md += ['', 'The four layers carry the same pour, so the current splits by copper thickness: L1 %.0f %%, L2 %.0f %%, '
           'L3 %.0f %%, L6 %.0f %%, and the vias carry almost nothing; the pins of J1, J2 and the shunts tie the '
           'layers together. The copper adds %.0f %% to the shunt heat: the shunts (%.2f W each) and, if present, '
           'the connector contacts dominate.' % (tuple(100 * s for s in sh) + (
               100 * sum(p['P_in'] + p['P_out'] for p in b['paths'].values()) / sum(p['P_shunt'] for p in b['paths'].values()),
               b['paths']['U']['P_shunt'])), '',
           '## Temperatures at %.0f A rms' % b['I'], '',
           '| | %s | %s | Limit |' % (pp.CASES['board'], pp.CASES['contacts']), '| --- | --- | --- | --- |',
           '| Heat in the board | %.2f W | %.2f W | |' % (b['P_total'], c['P_total'])]
    lim = pp.pbv_limit(b['I'])
    for k in pp.PHASES:
        pb, pc = b['phases'][k], c['phases'][k]
        md.append('| %s terminals (pins 1 / 4) | %.0f / %.0f C | %.0f / %.0f C | %.0f C (PBV derating, %.2f W, no heatsink) |' % (
            pp.SHUNT[k], pb['pins']['R.1'], pb['pins']['R.4'], pc['pins']['R.1'], pc['pins']['R.4'], lim, b['paths'][k]['P_shunt']))
    for k in pp.PHASES:
        pb, pc = b['phases'][k], c['phases'][k]
        md.append('| J1 / J2 pin, phase %s | %.0f / %.0f C | %.0f / %.0f C | %.0f C (MR60PW) |' % (
            k, pb['pins'][pp.ESC_SIDE], pb['pins'][pp.MOTOR_SIDE], pc['pins'][pp.ESC_SIDE], pc['pins'][pp.MOTOR_SIDE], pp.T_MR60_MAX))
    for k in pp.PHASES:
        md.append('| %s (bottom, under %s) | %.0f C | %.0f C | |' % (pp.INA[k], pp.SHUNT[k], b['phases'][k]['t_ina'], c['phases'][k]['t_ina']))
    hb, hc = max(b['layers'], key=lambda l: l['t_max']), max(c['layers'], key=lambda l: l['t_max'])
    md += ['| Hottest point of the board | %.0f C at (%.1f, %.1f) | %.0f C at (%.1f, %.1f) | |' % (
        hb['t_max'], *hb['xy'], hc['t_max'], *hc['xy']),
        '| Mean of the board | %.0f C | %.0f C | |' % (b['layers'][0]['t_mean'], c['layers'][0]['t_mean']), '',
        'Phase W runs hottest: its shunt sits 3 mm from the bottom edge of the board, with less copper around it to '
        'spread the heat. Without the contacts the hottest point is a Kelvin pin of a shunt (%s): its small pads and '
        'the Kelvin tracks of L6 take the heat that flows down from the body through the U pins, up to %.0f K above '
        'the top face just there. With the contacts it is the %s.' % (
            where(hb['xy']), kelvin_rise(), where(hc['xy'])), '',
        '## Against the current', '',
        '| I rms per phase | PBV terminal | MR60PW pin | INA241 | Board mean | PBV limit |',
        '| --- | --- | --- | --- | --- | --- |']
    for sb, sc in zip(res['sweep']['board'], res['sweep']['contacts']):
        md.append('| %.0f A | %.0f / %.0f C | %.0f / %.0f C | %.0f / %.0f C | %.0f / %.0f C | %.0f C |' % (
            sb['I'], probe(sb, 'terminal'), probe(sc, 'terminal'), probe(sb, 'connector'), probe(sc, 'connector'),
            probe(sb, 'ina'), probe(sc, 'ina'), probe(sb, 'mean'), probe(sc, 'mean'), pp.pbv_limit(sb['I'])))
    md.append('')
    md.append('Each cell: copper and shunts / plus the MR60PW contacts at 1.0 mOhm.')
    for case in pp.CASES:
        x = crossing(res['sweep'][case], 'terminal', pp.pbv_limit)
        y = crossing(res['sweep'][case], 'connector', pp.T_MR60_MAX)
        md.append('- %s: the PBV terminals reach their derating limit %s; the MR60PW pins reach 120 C %s.' % (
            pp.CASES[case], 'at %.0f A' % x if x else 'beyond %.0f A' % max(pp.SWEEP),
            'at %.0f A' % y if y else 'beyond %.0f A' % max(pp.SWEEP)))
    md += ['', '## Model', '',
           '- Copper from the board file: 70 um on L1 and L6, 35 um on L2 and L3; resistivity 1.724e-8 Ohm.m at 20 C, '
           '+0.393 %/K, iterated with the temperature. Vias: 20 um barrel. Pins of J1, J2 and the shunts: one '
           'potential and one temperature over their hole on all layers.',
           '- FR4: 0.30 W/mK through the board, 0.80 in its plane. Faces: natural convection of a horizontal plate '
           '(%.1f W/m2K up, %.1f down at 35 A, copper and shunts) plus radiation, solder mask emissivity 0.9.' % (b['h_up'], b['h_down']),
           '- PBV-R001: 1 mOhm, body on its four pins (copper, 0.8 mm thick, 3 mm above the board). The three bodies '
           'lose %.2f W to the air themselves at 35 A (%.0f %% of the shunt heat): natural convection of a vertical '
           'plate on all faces (the 5.5 mm channels between them convect nearly as freely), radiation (emissivity '
           '0.5) only from the edges and the faces that see the room. They stand in the air the board warms, so '
           'they may lose less: with no loss from the bodies at all, the hottest PBV terminal would reach %.0f C '
           '(copper and shunts) or %.0f C (plus contacts) instead of %.0f / %.0f C. This is the largest uncertainty '
           'of the model; a thermocouple on a PBV terminal settles it. The inside is not published: 5.1 mm of '
           'terminal copper assumed from the resistive strip to each I pin (about 1 K).' % (
               b['loss']['bodies'], 100 * b['loss']['bodies'] / sum(p['P_shunt'] for p in b['paths'].values()),
               probe(res['no_body_loss']['board'], 'terminal'), probe(res['no_body_loss']['contacts'], 'terminal'),
               probe(b, 'terminal'), probe(c, 'terminal')),
           '- MR60PW contacts: datasheet maximum 1.0 mOhm (no typical value given); half of their heat enters the '
           'board, the other half the plug and its cable. With the cables also warming up at 35 A, the true share '
           'depends on their gauge and length.',
           '- Not modelled: the battery line (J3, R9, J5); the cables; other parts (the analog front end is well under '
           '1 W); the shade of the connectors and shunts on the faces; the board edges; any airflow or enclosure.',
           '', '## Checks', '',
           '- Heat balance: %.4f W in, %.4f W out (copper and shunts, 35 A).' % (b['P_total'], b['P_lost']),
           '- Kirchhoff: current through the shunt %.4f A for %.0f A injected.' % (b['paths']['U']['i_shunt'], b['I']),
           '- validate_solver.py: ring of copper fed by a J1-size pin, resistance +2.1 % at 0.1 mm (+0.7 % at '
           '0.05 mm), so the path resistances above lean high by about 2 %; copper sheet cooled on both faces, '
           'temperature within 0.03 % of the Bessel solution.']
    for key, s in res['grid_check'].items():
        md.append('- Grid %s mm (current / heat) instead of %g / %g: R J1 to R1 %.4f instead of %.4f mOhm, PBV R1 '
                  'terminal %.2f instead of %.2f C, hottest point %.2f instead of %.2f C.' % (
                      key, *res['res'], s['paths']['U']['R_in'] * 1e3, b['paths']['U']['R_in'] * 1e3,
                      s['phases']['U']['t_terminal'], b['phases']['U']['t_terminal'],
                      max(l['t_max'] for l in s['layers']), hb['t_max']))
    md.append('')
    with open(os.path.join(HERE, 'results.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('  results.md written')


def main():
    res, fields = load()
    geom = pp.load_geometry()
    fig_current(res, fields, geom)
    fig_temperature(res, fields, geom)
    fig_sweep(res)
    write_md(res, fields, geom)
    return 0


if __name__ == '__main__':
    sys.exit(main())
