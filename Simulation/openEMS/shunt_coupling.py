"""Inductance of the PBV shunts as the INA241 inputs see it, and coupling between phases, on the real layout.

A PBV shunt stands 3 mm above the board on four pins: the phase current goes up the outer (I) pins
and through the body, the INA241 reads the voltage between the inner (U) pins. The window between
the two U pins, under the body and down through the board to the Kelvin tracks on L6, is a loop:
every change of the phase current induces a voltage in it, which the INA241 adds to R.I. With
R = 1 mOhm, 1 nH of this "shunt inductance" is worth R at 160 kHz. LTspice simulation 07 could only
assume 0, 5 or 10 nH (datasheet: below 10 nH); this script computes it.

The copper of the four layers (geometry.json, written by export_kicad_geometry.py) is meshed in
openEMS, the three PBV shunts are added from their datasheet drawing (Z-DW-132b) and a current is
driven through two phases at a time, the way it flows in a motor:

    UV, VW, WU   the current enters the board at J1 on the first phase, crosses its shunt to J2,
                 comes back through the second phase. A 50 ohm lumped port bridges the two pins of
                 J1 2 mm above the board, where the plug of the ESC cable closes the loop; the two
                 pins of J2 are bridged the same way (the motor winding).

The three INA241 inputs are read through 1 Mohm lumped ports, from IN+ to IN- through the package
(0.5 mm under the board): V = jw.M.I on the copper model, R.I being added from the datasheet. Two
drives sharing a phase give the inductance that phase reads from its own current whatever the other
two currents do (they sum to zero), the third gives the coupling from the other phases.

Two models of the PBV body, whose inside is not published:
    foil     a metal sheet of the body outline in the plane of the pins (resistive foil and terminals)
    backed   the same plus a floating metal plate 1.6 mm behind it, in case the body has a metal back

Run with the Python that has the openEMS wheels:
    C:\\openEMS\\venv\\Scripts\\python.exe shunt_coupling.py      (6 runs, about 20 min each on 8 cores)
    ... --drive UV     one drive only: UV, VW or WU
    ... --case backed  one body model only: foil or backed
    ... --check        only mesh the board and verify the nets
    ... --view         open the model in AppCSXCAD instead of simulating
    ... --post-only    recompute the results from the existing run/ data
    ... --res 0.15     another mesh step, in run/<case>_<drive>_0.15mm (convergence check)
then report.py for the figures and results.md.

Not modelled: the cables beyond J1 / J2 and the battery channel (IC10 is not placed yet); solder
mask, copper thickness; the inside of the PBV (see the two body models); the resistance of the
copper, so the current spreads as it does above a few hundred kHz, not as at DC.
"""
import argparse
import json
import os
import re
import sys
import time

import numpy as np
from matplotlib.path import Path
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

HERE = os.path.dirname(os.path.abspath(__file__))
GEOM = os.path.join(HERE, 'geometry.json')
RUN = os.path.join(HERE, 'run')

EPS0 = 8.8541878128e-12

# Excitation: gaussian pulse covering 0..400 MHz. The coupling is quasi-static (V = jw.M.I, flat M)
# well above the 10-100 MHz band where M is read; validate_mutual.py checks the method there.
F0 = FC = 200e6
T_SETTLE = 3e-9
F_FIT = (10e6, 100e6)
F_FIELD = 50e6               # frequency of the field maps
R_DRIVE = 50.0
R_SENSE = 1e6                # the INA241 input: open
OVERSAMPLING = 1000          # store the probes every few timesteps: keeps the solver noise out of the band

# Mesh: RES inside the window holding the connectors, the shunts and the INA241, coarser elsewhere.
# The lines are rounded: a sheet or wire of zero width only becomes metal on a line it hits exactly.
RES = 0.2
FINE_X, FINE_Y = (-21.0, 21.0), (-39.2, -13.0)
AIR = 20.0

GND = 'GND'
RAILS = ('+5VA', '+2.5VA', '+6V')            # ideally decoupled, tied to the ground copper below them
DECOUPLING_PITCH = 2.0                       # mm
PHASES = ('U', 'V', 'W')
SHUNT = {'U': 'R1', 'V': 'R4', 'W': 'R7'}
INA = {'U': 'IC2', 'V': 'IC4', 'W': 'IC6'}
KELVIN = {'U': ('IN-1', 'OUT-1'), 'V': ('IN-2', 'OUT-2'), 'W': ('IN-3', 'OUT-3')}   # (IN-, IN+) of the INA241
POWER = {k: ('IN-' + k, 'OUT-' + k) for k in PHASES}                              # J1 side, J2 side of the shunt
ESC_SIDE, MOTOR_SIDE = 'J1', 'J2'
DRIVES = ('UV', 'VW', 'WU')                  # current in at J1 on the first phase, back on the second
CASES = ('foil', 'backed')

# PBV-R001-F1-1.0, datasheet drawing Z-DW-132b (mm)
PBV_PINS = (('1', 1.5), ('2', 1.1), ('3', 1.1), ('4', 1.5))    # pad, width of the pin: I, U, U, I
PBV_OVERHANG = 2.36          # body beyond the outer pins (22.5 mm wide body, pins 17.78 apart)
PBV_STANDOFF = 3.0           # body bottom above the board: length of the wide part of the pins
PBV_HEIGHT = 17.5
BACKING_DY = 1.6             # backed model: plate behind the foil, on the thicker side of the body
CONN_HEIGHT = 2.0            # where the plugs close the loop above J1 / J2
PKG_DEPTH = 0.5              # INA241 leads: the sense port runs this far under the board
I_PROBE_Z = 1.34             # height above the board of the current probes on the I pins


def load_geometry():
    """geometry.json without the parts placed outside the board (the boost stage is not placed yet)."""
    with open(GEOM, encoding='utf-8') as f:
        geom = json.load(f)
    w, h = geom['size_mm']
    on_board = lambda xy: abs(xy[0]) <= w / 2 + 1 and abs(xy[1]) <= h / 2 + 1
    geom['barrels'] = [b for b in geom['barrels'] if on_board(b['xy'])]
    geom['pads'] = [p for p in geom['pads'] if on_board(p['xy'])]
    geom['parts'] = [p for p in geom['parts'] if on_board(p['xy'])]
    geom['tracks'] = [t for t in geom['tracks'] if all(on_board(p) for p in t['pts'])]
    return geom


# ----------------------------------------------------------------------------- mesh

def build_mesh(geom):
    def axis(fine, half_board):
        lines = list(np.arange(int(round(fine[0] / RES)), int(round(fine[1] / RES)) + 1) * RES)
        for sign in (-1, 1):
            x, d = (lines[0] if sign < 0 else lines[-1]), RES
            while abs(x) < half_board + AIR:
                d = min(d * 1.3, 0.8 if abs(x) < half_board else 3.0)
                x += sign * d
                lines.insert(0, x) if sign < 0 else lines.append(x)
        return np.round(lines, 6)

    w, h = geom['size_mm']
    zl = [l['z'] for l in geom['layers']]            # L1 (top) .. L6 (bottom, z = 0)
    core = zl[2] + (zl[1] - zl[2]) * np.array([0.6, 1.6, 2.6, 3.6]) / 4.2
    below = -np.array([0.12, 0.28, PKG_DEPTH, 0.8, 1.2, 1.75, 2.5, 3.5, 4.9, 6.8, 9.3, 12.3, 16.0, 20.0])
    above = zl[0] + np.array([0.1, 0.24, 0.42, 0.66, 0.96, I_PROBE_Z, 1.67, CONN_HEIGHT, 2.5, PBV_STANDOFF,
                              3.4, 3.9, 4.5, 5.2, 6.0, 7.0, 8.2, 9.5, 11.0, 12.5, 14.0, 15.5, 17.0, 18.4, 19.6,
                              PBV_STANDOFF + PBV_HEIGHT, 21.3, 22.4, 24.0, 26.5, 30.0, 35.0, 41.0])
    z = np.round(np.concatenate([below[::-1], [zl[3], zl[2]], core, [zl[1], zl[0]], above]), 6)
    assert np.all(np.diff(z) > 0)
    return {'x': axis(FINE_X, w / 2), 'y': axis(FINE_Y, h / 2), 'z': z, 'zl': zl}


def snap(lines, v):
    return int(np.argmin(np.abs(lines - v)))


# ----------------------------------------------------------------------------- copper -> mesh edges

class Raster:
    """Decides which in-plane mesh edges are metal, and for which net.

    own_x[layer, i, j] is the net of the edge from node (i, j) to (i+1, j), own_y the same towards
    (i, j+1); -1 means no metal. An edge is metal when its midpoint lies in the copper (the rule
    openEMS applies to polygons), plus a staircase along every track centre line so that thin
    tracks cannot break. Where edges of two nets meet at a node, or a via barrel runs through
    another net, the lower-ranked net loses its edges there.
    """

    def __init__(self, geom, mesh):
        self.x, self.y = mesh['x'], mesh['y']
        self.nx, self.ny = len(self.x), len(self.y)
        self.names = list(geom['nets'])
        kelvin = [n for pair in KELVIN.values() for n in pair]
        power = [n for pair in POWER.values() for n in pair]
        self.rank = np.array([3 if n in kelvin else 2 if n in power or n in RAILS else 0 if n == GND else 1
                              for n in self.names])
        self.own_x = -np.ones((4, self.nx - 1, self.ny), int)
        self.own_y = -np.ones((4, self.nx, self.ny - 1), int)
        self._polygons(geom)
        self._tracks(geom)
        self.barrels = [(snap(self.x, b['xy'][0]), snap(self.y, b['xy'][1])) for b in geom['barrels']]
        self.barrel_net = [self.names.index(b['net']) for b in geom['barrels']]
        self.removed = self._resolve()
        self._components()

    def _polygons(self, geom):
        xm, ym = (self.x[:-1] + self.x[1:]) / 2, (self.y[:-1] + self.y[1:]) / 2
        for n, name in enumerate(self.names):
            for l, outlines in enumerate(geom['nets'][name]):
                for o in outlines:
                    p = np.asarray(o)
                    path = Path(np.vstack([p, p[:1]]), closed=True)
                    lo, hi = p.min(0), p.max(0)
                    for own, gx, gy in ((self.own_x[l], xm, self.y), (self.own_y[l], self.x, ym)):
                        i0, i1 = np.searchsorted(gx, [lo[0], hi[0]])
                        j0, j1 = np.searchsorted(gy, [lo[1], hi[1]])
                        if i1 <= i0 or j1 <= j0:
                            continue
                        X, Y = np.meshgrid(gx[i0:i1], gy[j0:j1], indexing='ij')
                        inside = path.contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
                        own[i0:i1, j0:j1][inside] = n

    def _tracks(self, geom):
        for t in geom['tracks']:
            n, l = self.names.index(t['net']), t['layer']
            nodes = [(snap(self.x, p[0]), snap(self.y, p[1])) for p in t['pts']]
            for (i, j), (i1, j1) in zip(nodes[:-1], nodes[1:]):
                di, dj, si, sj = abs(i1 - i), abs(j1 - j), np.sign(i1 - i), np.sign(j1 - j)
                cx = cy = 0
                while cx < di or cy < dj:
                    if cy >= dj or (cx < di and (cx + 0.5) * dj <= (cy + 0.5) * di):
                        self.own_x[l, min(i, i + si), j] = n
                        i += si; cx += 1
                    else:
                        self.own_y[l, i, min(j, j + sj)] = n
                        j += sj; cy += 1

    def _around(self, l, ix, iy):
        """The (array, index) of the up to four edges meeting at a node."""
        e = []
        if ix > 0: e.append((self.own_x, (l, ix - 1, iy)))
        if ix < self.nx - 1: e.append((self.own_x, (l, ix, iy)))
        if iy > 0: e.append((self.own_y, (l, ix, iy - 1)))
        if iy < self.ny - 1: e.append((self.own_y, (l, ix, iy)))
        return e

    def _resolve(self):
        size = np.bincount(np.concatenate([self.own_x.ravel(), self.own_y.ravel()]) + 1, minlength=len(self.names) + 1)[1:]
        removed = 0
        for (ix, iy), n in zip(self.barrels, self.barrel_net):      # a barrel keeps other nets away
            for l in range(4):
                for arr, k in self._around(l, ix, iy):
                    if arr[k] not in (-1, n):
                        arr[k] = -1; removed += 1
        for l in range(4):
            stack = -np.ones((4, self.nx, self.ny), int)
            stack[0, 1:, :] = self.own_x[l]; stack[1, :-1, :] = self.own_x[l]
            stack[2, :, 1:] = self.own_y[l]; stack[3, :, :-1] = self.own_y[l]
            hi = stack.max(0)
            lo = np.where(stack >= 0, stack, len(self.names)).min(0)
            for ix, iy in zip(*np.nonzero((hi >= 0) & (lo != hi))):
                edges = self._around(l, ix, iy)
                nets = {int(arr[k]) for arr, k in edges if arr[k] >= 0}
                if len(nets) < 2:
                    continue                                         # already settled from a neighbour
                keep = max(nets, key=lambda n: (self.rank[n], -size[n]))   # thin, important nets win
                for arr, k in edges:
                    if arr[k] not in (-1, keep):
                        arr[k] = -1; removed += 1
        return removed

    def _components(self):
        idx = np.arange(4 * self.nx * self.ny).reshape(4, self.nx, self.ny)
        a, b = [], []
        for l in range(4):
            m = self.own_x[l] >= 0
            a.append(idx[l, :-1, :][m]); b.append(idx[l, 1:, :][m])
            m = self.own_y[l] >= 0
            a.append(idx[l, :, :-1][m]); b.append(idx[l, :, 1:][m])
        for ix, iy in self.barrels:
            a.append(idx[:3, ix, iy]); b.append(idx[1:, ix, iy])
        a, b = np.concatenate(a), np.concatenate(b)
        graph = coo_matrix((np.ones(len(a), bool), (a, b)), shape=(idx.size, idx.size))
        self.labels = connected_components(graph, directed=False)[1].reshape(idx.shape)

    def components_of(self, net):
        """Connected pieces of a net: list of (label, number of edges), largest first."""
        n = self.names.index(net)
        lab = np.concatenate([np.concatenate([self.labels[l, :-1, :][self.own_x[l] == n],
                                              self.labels[l, :, :-1][self.own_y[l] == n]]) for l in range(4)])
        u, c = np.unique(lab, return_counts=True)
        return sorted(zip(u.tolist(), c.tolist()), key=lambda t: -t[1])

    def shorts(self):
        """Groups of different nets that ended up as one conductor."""
        by_label = {}
        for name in self.names:
            for lab, _ in self.components_of(name):
                by_label.setdefault(lab, set()).add(name)
        return [sorted(s) for s in by_label.values() if len(s) > 1]

    def net_nodes(self, layer, net):
        """Nodes of a layer that belong to the main piece of this net."""
        n = self.names.index(net)
        m = np.zeros((self.nx, self.ny), bool)
        ox, oy = self.own_x[layer] == n, self.own_y[layer] == n
        m[:-1, :] |= ox; m[1:, :] |= ox; m[:, :-1] |= oy; m[:, 1:] |= oy
        return m & (self.labels[layer] == self.components_of(net)[0][0])

    def pick_node(self, layer, xy, net, max_dist=0.6):
        """Mesh node of a layer nearest to xy that belongs to the net."""
        ix, iy = np.nonzero(self.net_nodes(layer, net))
        d = np.hypot(self.x[ix] - xy[0], self.y[iy] - xy[1])
        k = int(np.argmin(d))
        if d[k] > max_dist:
            raise RuntimeError('no mesh node of %s within %g mm of %s on layer %d' % (net, max_dist, xy, layer))
        return int(ix[k]), int(iy[k])


def edge_runs(raster, layer, net):
    """Metal edges of a net on a layer as straight runs [(x0, y0), (x1, y1)] in mm."""
    n, x, y, out = raster.names.index(net), raster.x, raster.y, []
    for j in range(raster.ny):                                   # runs along x on each y line
        row = np.flatnonzero(np.diff(np.r_[0, raster.own_x[layer][:, j] == n, 0].astype(np.int8)))
        out += [((x[a], y[j]), (x[b], y[j])) for a, b in zip(row[::2], row[1::2])]
    for i in range(raster.nx):                                   # runs along y on each x line
        col = np.flatnonzero(np.diff(np.r_[0, raster.own_y[layer][i, :] == n, 0].astype(np.int8)))
        out += [((x[i], y[a]), (x[i], y[b])) for a, b in zip(col[::2], col[1::2])]
    return out


def pad(geom, ref, number=None, net=None):
    return next(p for p in geom['pads'] if p['ref'] == ref and (number is None or p['pad'] == number)
                and (net is None or p['net'] == net))


# ----------------------------------------------------------------------------- what is driven and read

def plan(geom, mesh, raster, drive):
    """Mesh indices of the plug bridges, the shunt bodies, the INA241 ports and the current probes."""
    a, b = drive
    x, y, z = mesh['x'], mesh['y'], mesh['z']
    pl = {'drive': drive, 'shunts': {}, 'sense': {}, 'plugs': {}}
    # the plugs: J1 bridged through the drive port, J2 short. Each bridge runs from the pin of the
    # return phase b to the pin of phase a, so the port current leaves towards a.
    for ref, net_of in ((ESC_SIDE, lambda k: POWER[k][0]), (MOTOR_SIDE, lambda k: POWER[k][1])):
        ends = [raster.pick_node(0, pad(geom, ref, net=net_of(k))['xy'], net_of(k), max_dist=1.0) for k in (b, a)]
        assert ends[0][0] == ends[1][0], 'the pins of %s are not on one mesh line' % ref
        pl['plugs'][ref] = ends
    for k in PHASES:
        ref = SHUNT[k]
        pads = {n: pad(geom, ref, n) for n, _ in PBV_PINS}
        assert [pads[n]['net'] for n in '1234'] == [POWER[k][0], KELVIN[k][0], KELVIN[k][1], POWER[k][1]], ref
        assert pads['1']['xy'][0] < pads['4']['xy'][0] and abs(pads['1']['xy'][1] - pads['4']['xy'][1]) < 0.05
        yp = pads['1']['xy'][1]
        pl['shunts'][k] = {
            'ref': ref, 'iy': snap(y, yp), 'iy_back': snap(y, yp + BACKING_DY),
            'ix_body': (snap(x, pads['1']['xy'][0] - PBV_OVERHANG), snap(x, pads['4']['xy'][0] + PBV_OVERHANG)),
            'pins': [(snap(x, pads[n]['xy'][0] - w / 2), snap(x, pads[n]['xy'][0] + w / 2)) for n, w in PBV_PINS],
            'x_pads': [pads[n]['xy'][0] for n in '1234'], 'y_pin': yp}
        # INA241: IN+ (pin 8, J2 side of the shunt) to IN- (pin 1, J1 side), read through the package
        nodes = [raster.pick_node(3, pad(geom, INA[k], n)['xy'], net) for n, net in (('8', KELVIN[k][1]), ('1', KELVIN[k][0]))]
        assert nodes[0][1] == nodes[1][1], 'IN+ and IN- of %s are not on one mesh line' % INA[k]
        pl['sense'][k] = {'start': nodes[0], 'stop': nodes[1],
                          'xy_ina': [pad(geom, INA[k], n)['xy'] for n in ('8', '1')]}
    # supply rails are AC ground: every DECOUPLING_PITCH tied to the ground copper right below
    step = max(1, int(round(DECOUPLING_PITCH / RES)))
    grid = np.zeros((raster.nx, raster.ny), bool)
    grid[::step, ::step] = True
    for ix, iy in raster.barrels:
        grid[ix, iy] = False
    posts = []
    for rail in RAILS:
        for upper, lower in ((0, 1), (2, 3)):
            ok = grid & raster.net_nodes(upper, rail) & raster.net_nodes(lower, GND)
            posts += [(int(ix), int(iy), upper, lower) for ix, iy in zip(*np.nonzero(ok))]
    pl['posts'] = posts
    return pl


def report_plan(mesh, pl):
    x, y = mesh['x'], mesh['y']
    a, b = pl['drive']
    (ib, jb), (ia, ja) = pl['plugs'][ESC_SIDE]
    print('drive %s: port across %s at x = %.2f, from %s (y = %.2f) to %s (y = %.2f), %s bridged the same way' % (
        pl['drive'], ESC_SIDE, x[ia], b, y[jb], a, y[ja], MOTOR_SIDE))
    for k, s in pl['shunts'].items():
        r = pl['sense'][k]
        print('  %s %s: plane y = %.2f, body x %.2f .. %.2f, pins %s; %s read from (%.2f, %.2f) to (%.2f, %.2f)' % (
            k, s['ref'], y[s['iy']], x[s['ix_body'][0]], x[s['ix_body'][1]],
            ' '.join('%.2f..%.2f' % (x[i0], x[i1]) for i0, i1 in s['pins']), INA[k],
            x[r['start'][0]], y[r['start'][1]], x[r['stop'][0]], y[r['stop'][1]]))
    print('  %d posts tie the rails to ground' % len(pl['posts']))


def report_check(mesh, raster):
    nx, ny, nz = len(mesh['x']), len(mesh['y']), len(mesh['z'])
    d = [np.diff(mesh[a]).min() for a in 'xyz']
    print('mesh %d x %d x %d = %.2f M cells, smallest cell %.3f x %.3f x %.3f mm' % (
        nx, ny, nz, nx * ny * nz / 1e6, d[0], d[1], d[2]))
    print('%d edges given up where two nets met' % raster.removed)
    ok = True
    print('nets after meshing:')
    for net in [GND] + list(RAILS) + [n for k in PHASES for n in POWER[k] + KELVIN[k]]:
        comps = raster.components_of(net)
        stray = sum(c for _, c in comps[1:])
        # A lost crumb of the ground plane (sliver between two antipads) is harmless, a cut track is not.
        # The rails only matter as AC ground: crumbs cut off them around the fine-pitch LDOs and
        # references, outside the fine mesh window and 8 mm or more from the shunts, are reported only.
        good = stray <= 0.005 * comps[0][1] if net == GND else True if net in RAILS else len(comps) == 1
        ok &= good
        print('  %-8s %6d edges  %s' % (net, comps[0][1], 'one piece' if len(comps) == 1 else
                                       '%s, %d stray edges in %d crumbs' % ('ok' if good else 'SPLIT', stray, len(comps) - 1)))
    shorts = raster.shorts()
    ok &= not shorts
    print('shorts between nets: %d%s' % (len(shorts), ''.join('\n  ' + ' = '.join(s) for s in shorts)))
    return ok


# ----------------------------------------------------------------------------- openEMS model

def build_model(geom, mesh, raster, pl, case, polygons=False, fields=False):
    """polygons=True draws the KiCad copper as is (for viewing); otherwise the verified mesh edges.

    fields=True also stores the H field at F_FIELD in the planes of the shunts, on L6 and above the board.
    """
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    x, y, z, zl = mesh['x'], mesh['y'], mesh['z'], mesh['zl']
    z_top = zl[0]
    z_body = (z[snap(z, z_top + PBV_STANDOFF)], z[snap(z, z_top + PBV_STANDOFF + PBV_HEIGHT)])

    fdtd = openEMS(EndCriteria=1e-9, MaxTime=2 * 9 / (2 * np.pi * FC) + T_SETTLE, OverSampling=OVERSAMPLING)
    fdtd.SetGaussExcite(F0, FC)
    fdtd.SetBoundaryCond(['MUR'] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    grid = csx.GetGrid()
    grid.SetDeltaUnit(1e-3)
    for a in 'xyz':
        grid.AddLine(a, mesh[a])

    w, h = geom['size_mm']
    for d, zb, zt in zip(geom['dielectrics'], zl[1:], zl[:-1]):
        fr4 = csx.AddMaterial('FR4 ' + d['name'], epsilon=d['epsilon_r'],
                              kappa=2 * np.pi * F_FIELD * EPS0 * d['epsilon_r'] * d['loss_tangent'])
        fr4.AddBox([-w / 2, -h / 2, zb], [w / 2, h / 2, zt], priority=0)

    metal, nprim = {}, 0
    for net, per_layer in geom['nets'].items():
        metal[net] = csx.AddMetal(re.sub(r'[^A-Za-z0-9+-]+', '_', net).strip('_') or 'no_net')
        for l in range(4):
            if polygons:
                for o in per_layer[l]:
                    metal[net].AddPolygon(np.asarray(o).T, 'z', zl[l], priority=10)
            else:
                for (x0, y0), (x1, y1) in edge_runs(raster, l, net):
                    metal[net].AddBox([x0, y0, zl[l]], [x1, y1, zl[l]], priority=10)
                    nprim += 1
    for b, (ix, iy) in zip(geom['barrels'], raster.barrels):
        metal[b['net']].AddBox([x[ix], y[iy], zl[3]], [x[ix], y[iy], z_top], priority=10)

    decoupling = csx.AddMetal('rail_decoupling')
    for ix, iy, upper, lower in pl['posts']:
        decoupling.AddBox([x[ix], y[iy], zl[lower]], [x[ix], y[iy], zl[upper]], priority=10)

    # PBV shunts: the body and the four pins as sheets in the plane of the pins, the pins running
    # through the board from L6 to the body
    for k, s in pl['shunts'].items():
        part = csx.AddMetal('PBV_' + s['ref'])
        yp, (i0, i1) = y[s['iy']], s['ix_body']
        part.AddBox([x[i0], yp, z_body[0]], [x[i1], yp, z_body[1]], priority=10)
        for p0, p1 in s['pins']:
            part.AddBox([x[p0], yp, zl[3]], [x[p1], yp, z_body[0]], priority=10)
        if case == 'backed':
            yb = y[s['iy_back']]
            csx.AddMetal('PBV_%s_back' % s['ref']).AddBox([x[i0], yb, z_body[0]], [x[i1], yb, z_body[1]], priority=10)

    # plugs: up from each pin to CONN_HEIGHT, across from one pin to the other. J1 keeps a one-cell gap
    # in the middle for the drive port.
    zc = z[snap(z, z_top + CONN_HEIGHT)]
    plug = csx.AddMetal('plugs')
    ports = []
    for ref, ((ix, jb), (_, ja)) in pl['plugs'].items():
        for j in (jb, ja):
            plug.AddBox([x[ix], y[j], z_top], [x[ix], y[j], zc], priority=10)
        if ref == MOTOR_SIDE:
            plug.AddBox([x[ix], y[jb], zc], [x[ix], y[ja], zc], priority=10)
            continue
        s = 1 if ja > jb else -1
        g = (jb + ja) // 2                                   # the gap runs from g to g + s
        plug.AddBox([x[ix], y[jb], zc], [x[ix], y[g], zc], priority=10)
        plug.AddBox([x[ix], y[g + s], zc], [x[ix], y[ja], zc], priority=10)
        ports.append(fdtd.AddLumpedPort(1, R_DRIVE, [x[ix], y[g], zc], [x[ix], y[g + s], zc], 'y', excite=1.0))

    # INA241 inputs: down the two leads, the port across under the package from IN+ to IN-
    zp = z[snap(z, -PKG_DEPTH)]
    leads = csx.AddMetal('INA241_leads')
    for n, k in enumerate(PHASES):
        r = pl['sense'][k]
        (i8, j), (i1, _) = r['start'], r['stop']
        for i in (i8, i1):
            leads.AddBox([x[i], y[j], zl[3]], [x[i], y[j], zp], priority=10)
        ports.append(fdtd.AddLumpedPort(n + 2, R_SENSE, [x[i8], y[j], zp], [x[i1], y[j], zp], 'x'))

    # current up the two I pins of each shunt, in the standoff
    zi = z[snap(z, z_top + I_PROBE_Z)]
    for k, s in pl['shunts'].items():
        for (p0, p1), n in zip([s['pins'][0], s['pins'][3]], ('1', '4')):
            box = [[x[p0 - 2], y[s['iy'] - 3], zi], [x[p1 + 2], y[s['iy'] + 3], zi]]
            csx.AddProbe('I_%s_%s' % (s['ref'], n), p_type=1, weight=1, norm_dir=2).AddBox(*box)

    if fields:
        xs = [s['x_pads'] for s in pl['shunts'].values()]
        x_lo, x_hi = min(v[0] for v in xs) - PBV_OVERHANG - 3, max(v[3] for v in xs) + PBV_OVERHANG + 3
        for k, s in pl['shunts'].items():
            yp = y[s['iy']]
            csx.AddDump('H_plane_%s' % k, dump_type=11, dump_mode=2, file_type=1, frequency=[F_FIELD]).AddBox(
                [x_lo, yp, -2.0], [x_hi, yp, z_body[1] + 3.0])
        ys = [s['y_pin'] for s in pl['shunts'].values()]
        csx.AddDump('H_L6', dump_type=11, dump_mode=2, file_type=1, frequency=[F_FIELD]).AddBox(
            [x_lo, min(ys) - 3, zl[3]], [x_hi, max(ys) + 4, zl[3]])
        csx.AddDump('H_above', dump_type=11, dump_mode=2, file_type=1, frequency=[F_FIELD]).AddBox(
            [FINE_X[0], FINE_Y[0], zi], [FINE_X[1], FINE_Y[1], zi])
    if not polygons:
        print('%s %s: %d metal runs handed to openEMS' % (case, pl['drive'], nprim))
    return fdtd, csx, ports


# ----------------------------------------------------------------------------- results

def read_probe(sim, name, f):
    from openEMS import utilities
    d = np.loadtxt(os.path.join(sim, name), comments='%')
    return utilities.DFT_time2freq(d[:, 0], d[:, 1], f)


def postprocess(sim, ports, pl, mesh, case):
    """V / I of the three INA241 inputs against the drive current, and the current in the shunt pins."""
    f = np.linspace(5e6, 200e6, 391)
    for p in ports:
        p.CalcPort(sim, f)
    w = 2 * np.pi * f
    band = (f >= F_FIT[0]) & (f <= F_FIT[1])
    i = ports[0].if_tot
    a, b = pl['drive']
    res = {'case': case, 'drive': pl['drive'], 'f': f.tolist(), 'f_fit': F_FIT, 'res_mm': RES,
           'z_drive': [(ports[0].uf_tot / i).real.tolist(), (ports[0].uf_tot / i).imag.tolist()],
           'i_drive': [i.real.tolist(), i.imag.tolist()],
           'sense': {}, 'pins': {}, 'geometry': {}}
    print('\n%s, drive %s (in on %s at %s, back on %s): induced voltage at the INA241 inputs' % (case, pl['drive'], a, ESC_SIDE, b))
    print('  %-6s %10s %10s %10s %12s' % ('input', 'M [nH]', 'spread', 'Re/Im', 'end/peak'))
    for k, p in zip(PHASES, ports[1:]):
        h = p.uf_tot / i
        m = h.imag / w
        mb = float(np.median(m[band]))
        tail = float(np.abs(p.ut_tot[-50:]).max() / np.abs(p.ut_tot).max())
        res['sense'][k] = {'re': h.real.tolist(), 'im': h.imag.tolist(), 'm_nH': mb * 1e9,
                           'spread': float(np.ptp(m[band]) / max(abs(mb), 1e-15)),
                           're_over_im': float(np.median(np.abs(h.real[band] / h.imag[band]))), 'tail': tail}
        print('  %-6s %10.4f %9.1f%% %10.3f %12.1e' % (k, mb * 1e9, 100 * res['sense'][k]['spread'], res['sense'][k]['re_over_im'], tail))
    # The drive current should all go through the shunts of the two driven phases: up pin 1 and down
    # pin 4 of the first one, the other way round in the second.
    print('  current in the I pins / drive current, %g-%g MHz:' % F_FIT)
    for k, s in pl['shunts'].items():
        ratio = []
        for n in ('1', '4'):
            ip = read_probe(sim, 'I_%s_%s' % (s['ref'], n), f) / i
            res['pins']['%s.%s' % (s['ref'], n)] = [ip.real.tolist(), ip.imag.tolist()]
            ratio.append(float(np.median(ip.real[band])))
        print('    %s %s: up pin 1 %+.3f, up pin 4 %+.3f' % (k, s['ref'], *ratio))
    # what the flux integral of report.py needs: the window of each shunt and its Kelvin tracks
    zl = mesh['zl']
    for k, s in pl['shunts'].items():
        res['geometry'][k] = {'x_pads': s['x_pads'], 'y_pin': float(mesh['y'][s['iy']]), 'xy_ina': pl['sense'][k]['xy_ina'],
                              'z_top': zl[0], 'z_body': float(mesh['z'][snap(mesh['z'], zl[0] + PBV_STANDOFF)])}
    with open(os.path.join(sim, 'results.json'), 'w') as fo:
        json.dump(res, fo)
    return res


def run_name(case, drive, res):
    return '%s_%s%s' % (case, drive, '' if res == 0.2 else '_%gmm' % res)


def main():
    global RES
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--drive', choices=DRIVES + ('all',), default='all')
    ap.add_argument('--case', choices=CASES + ('all',), default='all')
    ap.add_argument('--check', action='store_true', help='mesh and verify only')
    ap.add_argument('--view', action='store_true', help='open the model in AppCSXCAD')
    ap.add_argument('--post-only', action='store_true', help='reuse the data in run/')
    ap.add_argument('--threads', type=int, default=0)
    ap.add_argument('--res', type=float, default=RES, help='mesh step in the fine window, mm (convergence check)')
    args = ap.parse_args()
    RES = args.res

    geom = load_geometry()
    mesh = build_mesh(geom)
    raster = Raster(geom, mesh)
    ok = report_check(mesh, raster)
    plans = [plan(geom, mesh, raster, d) for d in (DRIVES if args.drive == 'all' else (args.drive,))]
    for pl in plans:
        report_plan(mesh, pl)
    if args.check:
        return 0 if ok else 1
    if not ok:
        print('the mesh does not reproduce the key nets, aborting')
        return 1

    for case in (CASES if args.case == 'all' else (args.case,)):
        for pl in plans:
            name = run_name(case, pl['drive'], RES)
            sim = os.path.join(RUN, name)
            fields = case == 'foil' and pl['drive'] == 'UV' and RES == 0.2
            fdtd, csx, ports = build_model(geom, mesh, raster, pl, case, polygons=args.view, fields=fields)
            if args.view:
                from CSXCAD import AppCSXCAD_BIN
                os.makedirs(RUN, exist_ok=True)
                xml = os.path.join(RUN, 'model_%s.xml' % name)
                csx.Write2XML(xml)
                os.system('"%s" "%s"' % (AppCSXCAD_BIN, xml))
                continue
            if not args.post_only:
                t0 = time.time()
                fdtd.Run(sim, cleanup=True, verbose=1, numThreads=args.threads)
                print('%s: simulated in %.1f min' % (name, (time.time() - t0) / 60), flush=True)
            postprocess(sim, ports, pl, mesh, case)
            sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
