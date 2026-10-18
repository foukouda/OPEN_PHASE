"""Current and temperature of the motor phase paths of OPEN_PHASE, on the routed copper.

Each phase current enters the board at J1 (MR60PW, ESC side), spreads over the IN-k pour of the four
layers, goes up pin 1 of its PBV shunt, through the 1 mOhm, down pin 4 and over the OUT-k pour to J2
(MR60PW, motor side). Two problems are solved on the copper of ../openEMS/geometry.json (written from
the board by ../openEMS/export_kicad_geometry.py):

    current  DC conduction in the six phase pours, 0.1 mm grid. The four layers are joined by the
             vias (plated barrel) and by the soldered pins of J1, J2 and the shunts (a pin holds its
             hole at one potential on all layers). The shunt is a 1 mOhm resistor from pin 1 to pin 4.
    heat     steady conduction in the whole board, 0.2 mm grid: the copper of every net on the four
             layers, the FR4 between them, the via barrels; natural convection and radiation from
             both faces in still air; each PBV body stands on its four pins and loses a little heat
             to the air itself.

The copper resistivity follows the temperature, so the two problems are iterated until the
temperature settles. The currents are RMS values: the heat of a path goes with I_rms^2 whatever the
waveform, and the board takes minutes to warm up, far longer than an electrical period. At the PWM
and motor frequencies the skin depth (0.4 mm at 24 kHz) exceeds the copper (70 um): the DC
distribution holds.

Two cases:
    board     heat from the copper and the shunts only; nothing crosses the cables
    contacts  the same plus the MR60PW contacts at their datasheet maximum (1.0 mOhm), half of that
              heat entering the board through the pin (the other half goes to the plug and cable)

Run with a Python that has numpy, scipy and matplotlib (the openEMS one works):
    C:\\openEMS\\venv\\Scripts\\python.exe power_paths.py              35 A, current sweep, grid check, figures, results.md
    ... --current 35 --case board                                         one point, printed only
    ... --res 0.05 0.2                                                    other grid steps (current, heat) in mm

Not modelled: the battery line (J3, R9, J5); the cables beyond J1 / J2 (no heat flows into them);
the parts other than the shunts (the analog front end dissipates well under 1 W); the shade of the
connectors and shunts on the board faces; the board edges (4 % of its surface).
"""
import argparse
import json
import os
import re
import sys
import time

import numpy as np
from matplotlib.path import Path
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import LinearOperator, cg, splu

HERE = os.path.dirname(os.path.abspath(__file__))
GEOM = os.path.normpath(os.path.join(HERE, '..', 'openEMS', 'geometry.json'))
BOARD = os.path.normpath(os.path.join(HERE, '..', '..', 'OPEN_PHASE.kicad_pcb'))
RESULTS = os.path.join(HERE, 'results.json')
FIELDS = os.path.join(HERE, 'fields.npz')

# grids (mm): the current in a window holding the phase paths, the heat over the whole board
RES_E, RES_T = 0.1, 0.2
WINDOW_X, WINDOW_Y = (-22.0, 22.0), (-40.0, -13.0)

# copper
RHO_20, ALPHA = 1.724e-8, 0.00393        # ohm.m at 20 C (IACS), 1/K
K_CU = 390.0                             # W/(m.K)
PLATING = 20e-6                          # via barrel copper, m (IPC-6012 class 2 average)
# FR4: through the thickness, in the plane
K_FR4_Z, K_FR4_XY = 0.30, 0.80
# air and surfaces
T_AMB = 25.0
EPS_MASK = 0.90                          # solder mask emissivity
SIGMA_SB, G0 = 5.670e-8, 9.81

PHASES = ('U', 'V', 'W')
SHUNT = {'U': 'R1', 'V': 'R4', 'W': 'R7'}
INA = {'U': 'IC2', 'V': 'IC4', 'W': 'IC6'}
IN_NET = {k: 'IN-' + k for k in PHASES}      # J1 side of the shunt
OUT_NET = {k: 'OUT-' + k for k in PHASES}    # J2 side
ESC_SIDE, MOTOR_SIDE = 'J1', 'J2'

# PBV-R001-F1-1.0 (Isabellenhuette datasheet issue 12-Feb-2026, drawing Z-DW-132b)
R_SHUNT = 1e-3
PBV_P_FREE = 3.0                         # W without heatsink: full power up to 80 C terminal, 0 at 125 C
PBV_DERATE = (80.0, 125.0)
PBV_SHOULDER = {'1': 3.0e-3, '2': 2.0e-3, '3': 2.0e-3, '4': 3.0e-3}   # pin width above the board: I, U, U, I
PBV_PIN_T, PBV_STANDOFF = 0.8e-3, 3.0e-3
PBV_BODY = (22.5e-3, 17.5e-3, 2.55e-3)   # width, height, thickness
PBV_EPS = 0.5                            # half metal, half insulated back
# inside not published: from the resistive strip to an I pin through 5.1 mm of terminal copper,
# 13.75 mm x 0.8 mm in section (assumed)
PBV_SPREAD = (5.1e-3, 13.75e-3 * 0.8e-3)
# MR60PW (Amass spec 2021V1): 35 A max (temperature rise < 85 C), contact resistance <= 1.0 mOhm,
# -20 to 120 C
I_MR60 = 35.0
R_CONTACT = 1.0e-3
CONTACT_SHARE = 0.5
T_MR60_MAX = 120.0
CASES = {'board': 'Copper and shunts', 'contacts': 'Plus MR60PW contacts at 1.0 mOhm'}

G_PIN_E, G_GROUND_E = 1e7, 1e9           # S: a soldered pin, the reference at J2
G_PIN_T = 5.0                            # W/K from a pin to each cell of its hole
VIA_R = 0.3                              # mm: radius of a via pad

I_MAIN = 35.0
SWEEP = (10.0, 20.0, 30.0, 35.0, 40.0, 50.0)


# ----------------------------------------------------------------------------- inputs

def load_geometry():
    with open(GEOM, encoding='utf-8') as f:
        geom = json.load(f)
    w, h = geom['size_mm']
    on = lambda xy: abs(xy[0]) <= w / 2 and abs(xy[1]) <= h / 2
    geom['barrels'] = [b for b in geom['barrels'] if on(b['xy'])]
    geom['pads'] = [p for p in geom['pads'] if on(p['xy'])]
    geom['parts'] = [p for p in geom['parts'] if on(p['xy'])]
    return geom


def copper_thickness():
    """F.Cu, In1.Cu, In2.Cu, B.Cu thickness from the stackup of the board file, m."""
    with open(BOARD, encoding='utf-8') as f:
        txt = f.read()
    block = txt[txt.index('(stackup'):]
    out = []
    for name in ('F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'):
        m = re.search(r'\(layer "%s"[^()]*\(type "copper"\)\s*\(thickness ([0-9.]+)\)' % re.escape(name), block)
        out.append(float(m.group(1)) * 1e-3)
    return out


class Grid:
    """Square cells of side d (mm), cell (i, j) centred at (x[i], y[j])."""

    def __init__(self, x0, x1, y0, y1, d):
        self.d, self.x0, self.y0 = d, x0, y0
        self.nx, self.ny = int(round((x1 - x0) / d)), int(round((y1 - y0) / d))
        self.x = x0 + d * (np.arange(self.nx) + 0.5)
        self.y = y0 + d * (np.arange(self.ny) + 0.5)

    def cell(self, xy):
        return (int(np.clip((xy[0] - self.x0) // self.d, 0, self.nx - 1)),
                int(np.clip((xy[1] - self.y0) // self.d, 0, self.ny - 1)))

    def disc(self, xy, r):
        """Cells whose centre lies within r of xy, as (i, j) arrays."""
        i0, i1 = np.searchsorted(self.x, [xy[0] - r, xy[0] + r])
        j0, j1 = np.searchsorted(self.y, [xy[1] - r, xy[1] + r])
        X, Y = np.meshgrid(self.x[i0:i1], self.y[j0:j1], indexing='ij')
        ii, jj = np.nonzero(np.hypot(X - xy[0], Y - xy[1]) <= r)
        return ii + i0, jj + j0


def rasterize(geom, grid, nets):
    """owner[l, i, j]: index in nets of the copper holding the centre of the cell, -1 if none."""
    owner = -np.ones((4, grid.nx, grid.ny), np.int32)
    for n, name in enumerate(nets):
        for l, outlines in enumerate(geom['nets'][name]):
            for o in outlines:
                p = np.asarray(o)
                lo, hi = p.min(0), p.max(0)
                i0, i1 = np.searchsorted(grid.x, [lo[0], hi[0]])
                j0, j1 = np.searchsorted(grid.y, [lo[1], hi[1]])
                if i1 <= i0 or j1 <= j0:
                    continue
                X, Y = np.meshgrid(grid.x[i0:i1], grid.y[j0:j1], indexing='ij')
                inside = Path(np.vstack([p, p[:1]])).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
                owner[l, i0:i1, j0:j1][inside] = n
    return owner


def pairs(a, axis):
    """The two cells of every face along an axis: (first, second)."""
    return (a[:-1, :], a[1:, :]) if axis == 0 else (a[:, :-1], a[:, 1:])


def network(n, a, b, g, ground):
    """Nodal matrix of a network: edges (a, b) of conductance g, conductances to the reference."""
    rows = np.concatenate([a, b, a, b, np.arange(n)])
    cols = np.concatenate([a, b, b, a, np.arange(n)])
    vals = np.concatenate([g, g, -g, -g, ground])
    return coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsc()


class Solver:
    """A x = b for a series of symmetric positive definite matrices that change little from one call
    to the next (copper resistivity, surface losses): conjugate gradients preconditioned by the LU
    factors of an earlier matrix, factorised again when they stop helping."""

    def __init__(self, rtol=1e-12, max_iter=60):
        self.lu, self.x, self.rtol, self.max_iter = None, None, rtol, max_iter
        self.factorisations = 0

    def __call__(self, a, b):
        if self.lu is not None and self.lu.shape == a.shape:
            m = LinearOperator(a.shape, self.lu.solve)
            x, info = cg(a, b, x0=self.x, rtol=self.rtol, maxiter=self.max_iter, M=m)
            if info == 0:
                self.x = x
                return x
        self.lu = splu(a.tocsc(), permc_spec='MMD_AT_PLUS_A')
        self.factorisations += 1
        self.x = self.lu.solve(b)
        return self.x


# ----------------------------------------------------------------------------- air

def air(t):
    """Thermal conductivity, kinematic viscosity, Prandtl number of air at t (C), 0-150 C."""
    return 0.02414 + 7.4e-5 * t, 1.33e-5 + 8.8e-8 * t + 1.0e-10 * t * t, 0.71


def h_natural(dt, length, face):
    """Natural convection coefficient (W/m2K) of a plate dt above the air: 'up', 'down' or 'vertical'."""
    dt = max(dt, 0.1)
    tf = T_AMB + dt / 2
    k, nu, pr = air(tf)
    ra = G0 / (tf + 273.15) * dt * length ** 3 / (nu * nu / pr)
    return {'up': 0.54, 'down': 0.27, 'vertical': 0.59}[face] * ra ** 0.25 * k / length


def h_radiation(t, eps):
    """Linearised radiation to surroundings at T_AMB, W/m2K, t in C (array or scalar)."""
    tk, ta = np.asarray(t) + 273.15, T_AMB + 273.15
    return eps * SIGMA_SB * (tk * tk + ta * ta) * (tk + ta)


# ----------------------------------------------------------------------------- model

class PhasePaths:
    def __init__(self, res_e=RES_E, res_t=RES_T, verbose=True):
        t0 = time.time()
        geom = self.geom = load_geometry()
        self.tcu = copper_thickness()
        self.tdiel = [d['thickness'] * 1e-3 for d in geom['dielectrics']]
        w, h = geom['size_mm']
        tg = self.tg = Grid(-w / 2, w / 2, -h / 2, h / 2, res_t)
        self.r = int(round(res_t / res_e))
        assert abs(self.r * res_e - res_t) < 1e-9, 'the heat grid step must be a multiple of the current one'
        i0 = max(0, int(np.floor((WINDOW_X[0] - tg.x0) / res_t))); i1 = min(tg.nx, int(np.ceil((WINDOW_X[1] - tg.x0) / res_t)))
        j0 = max(0, int(np.floor((WINDOW_Y[0] - tg.y0) / res_t))); j1 = min(tg.ny, int(np.ceil((WINDOW_Y[1] - tg.y0) / res_t)))
        self.win = (i0, i1, j0, j1)
        eg = self.eg = Grid(tg.x0 + i0 * res_t, tg.x0 + i1 * res_t, tg.y0 + j0 * res_t, tg.y0 + j1 * res_t, res_e)
        self.pads = {(p['ref'], p['pad']): p for p in geom['pads']}
        self.parts = {p['ref']: p for p in geom['parts']}
        self.power = [IN_NET[k] for k in PHASES] + [OUT_NET[k] for k in PHASES]
        self.own_e = rasterize(geom, eg, self.power)
        self.names = list(geom['nets'])
        self.own_t = rasterize(geom, tg, self.names)
        self._current_static()
        self._heat_static()
        self.solver_e, self.solver_t = Solver(), Solver()
        self.body_loss = 1.0                 # 0: the PBV bodies lose nothing to the air themselves (bound)
        if verbose:
            print('grids: current %d x %d x 4 at %.3f mm (%d copper cells), heat %d x %d x 4 at %.3f mm; set up in %.0f s'
                  % (eg.nx, eg.ny, res_e, self.n_e, tg.nx, tg.ny, res_t, time.time() - t0))
            self.report_raster()

    # --- which pin is which
    def pin_pad(self, k, side):
        """Pad of phase k: side 'J1', 'R.1', 'R.4' or 'J2'."""
        if side == ESC_SIDE:
            return next(p for p in self.geom['pads'] if p['ref'] == ESC_SIDE and p['net'] == IN_NET[k])
        if side == MOTOR_SIDE:
            return next(p for p in self.geom['pads'] if p['ref'] == MOTOR_SIDE and p['net'] == OUT_NET[k])
        return self.pads[(SHUNT[k], side[-1])]

    # --- current
    def _current_static(self):
        own, eg = self.own_e, self.eg
        active = own >= 0
        self.n_e = int(active.sum())
        idx = self.idx_e = -np.ones(own.shape, np.int64)
        idx[active] = np.arange(self.n_e)
        # vias of the phase nets, one node per layer, moved to the nearest cell of the net if needed
        # the current density is not read within VIA_R of a via: the via feeds a single cell there
        self.vias_e, lost = [], 0
        self.j_mask = np.ones(own.shape, bool)
        for b in self.geom['barrels']:
            if b['kind'] != 'via' or b['net'] not in self.power:
                continue
            n = self.power.index(b['net'])
            cells = []
            ii, jj = eg.disc(b['xy'], VIA_R)
            self.j_mask[:, ii, jj] = False
            for l in range(4):
                ok = own[l, ii, jj] == n
                if not ok.any():
                    cells.append(None); continue
                d = np.hypot(eg.x[ii[ok]] - b['xy'][0], eg.y[jj[ok]] - b['xy'][1])
                k = int(np.argmin(d))
                cells.append(int(idx[l, ii[ok][k], jj[ok][k]]))
            lost += sum(c is None for c in cells)
            self.vias_e.append({'net': b['net'], 'xy': b['xy'], 'drill': b['drill'] * 1e-3, 'nodes': cells})
        self.vias_lost = lost
        # pins: every cell of the net in the hole, on all layers
        self.pins_e = {}
        for k in PHASES:
            for side in (ESC_SIDE, 'R.1', 'R.4', MOTOR_SIDE):
                p = self.pin_pad(k, side)
                n = self.power.index(p['net'])
                ii, jj = eg.disc(p['xy'], p['drill'] / 2)
                nodes = [idx[l, ii, jj][own[l, ii, jj] == n] for l in range(4)]
                self.pins_e[(k, side)] = np.concatenate(nodes)

    def solve_current(self, currents, t_e):
        """currents: {phase: A}; t_e: temperature of the current cells (4, nx, ny). Fields and figures."""
        own, eg, idx = self.own_e, self.eg, self.idx_e
        n = self.n_e
        pin_node = {key: n + i for i, key in enumerate(self.pins_e)}
        npin = len(pin_node)
        rho = RHO_20 * (1 + ALPHA * (t_e - 20.0))
        a, b, g, faces = [], [], [], {}
        for l in range(4):
            for axis in (0, 1):
                o1, o2 = pairs(own[l], axis)
                r1, r2 = pairs(rho[l], axis)
                m = (o1 >= 0) & (o1 == o2)
                gf = np.where(m, self.tcu[l] / ((r1 + r2) / 2), 0.0)         # square cells: G = t / rho
                faces[l, axis] = gf
                i1, i2 = pairs(idx[l], axis)
                a.append(i1[m]); b.append(i2[m]); g.append(gf[m])
        flat_rho = rho[own >= 0]
        va, vb, vg, vid = [], [], [], []
        for v, via in enumerate(self.vias_e):
            for l in range(3):
                c1, c2 = via['nodes'][l], via['nodes'][l + 1]
                if c1 is None or c2 is None:
                    continue
                length = self.tdiel[l] + (self.tcu[l] + self.tcu[l + 1]) / 2
                va.append(c1); vb.append(c2); vid.append(v)
                vg.append(np.pi * via['drill'] * PLATING / (length * (flat_rho[c1] + flat_rho[c2]) / 2))
        va, vb, vg, vid = np.array(va), np.array(vb), np.array(vg), np.array(vid)
        a += [va]; b += [vb]; g += [vg]
        for key, cells in self.pins_e.items():
            a.append(cells); b.append(np.full(len(cells), pin_node[key])); g.append(np.full(len(cells), G_PIN_E))
        rhs = np.zeros(n + npin)
        ground = np.zeros(n + npin)
        for k, i in currents.items():
            a.append([pin_node[(k, 'R.1')]]); b.append([pin_node[(k, 'R.4')]]); g.append([1 / R_SHUNT])
            rhs[pin_node[(k, ESC_SIDE)]] = i
            ground[pin_node[(k, MOTOR_SIDE)]] = G_GROUND_E
        a, b, g = np.concatenate(a).astype(np.int64), np.concatenate(b).astype(np.int64), np.concatenate(g)
        v = self.solver_e(network(n + npin, a, b, g, ground), rhs)

        vg_ = np.zeros(own.shape)
        vg_[own >= 0] = v[:n]
        p_cell = np.zeros(own.shape)
        jx, jy = np.zeros(own.shape), np.zeros(own.shape)
        cut_x = {}
        for l in range(4):
            for axis, jarr in ((0, jx), (1, jy)):
                gf = faces[l, axis]
                v1, v2 = pairs(vg_[l], axis)
                cur = gf * (v1 - v2)
                p = gf * (v1 - v2) ** 2
                s1, s2 = pairs(p_cell[l], axis)
                s1 += p / 2; s2 += p / 2
                # current density at the cell: mean of the currents through its faces on this axis
                q1, q2 = pairs(jarr[l], axis)
                q1 += cur; q2 += cur
                cnt = np.zeros(own.shape[1:])
                k1, k2 = pairs(cnt, axis)
                k1 += gf > 0; k2 += gf > 0
                jarr[l] /= np.maximum(cnt, 1) * eg.d * 1e-3 * self.tcu[l]
                if axis == 0:
                    cut_x[l] = cur
        jmag = np.hypot(jx, jy) / 1e6                        # A/mm2
        # vias: current per barrel segment, heat to the two cells
        vcur = vg * (v[va] - v[vb])
        vpow = vg * (v[va] - v[vb]) ** 2
        flat = np.zeros(n)
        np.add.at(flat, va, vpow / 2); np.add.at(flat, vb, vpow / 2)
        p_cell[own >= 0] += flat
        via_max = np.zeros(len(self.vias_e))
        np.maximum.at(via_max, vid, np.abs(vcur))
        out = {'p_cell': p_cell, 'j': jmag, 'paths': {}, 'via_max': via_max}
        for k, i in currents.items():
            vp = {s: v[pin_node[(k, s)]] for s in (ESC_SIDE, 'R.1', 'R.4', MOTOR_SIDE)}
            i_sh = (vp['R.1'] - vp['R.4']) / R_SHUNT
            shares = {}
            for net, s0, s1 in ((IN_NET[k], ESC_SIDE, 'R.1'), (OUT_NET[k], 'R.4', MOTOR_SIDE)):
                xc = (self.pin_pad(k, s0)['xy'][0] + self.pin_pad(k, s1)['xy'][0]) / 2
                ic = int(np.searchsorted(eg.x, xc)) - 1
                m = own[:, ic, :] == self.power.index(net)
                shares[net] = [float(np.sum(cut_x[l][ic, :][m[l]]) / i) for l in range(4)]
            nets = [self.power.index(IN_NET[k]), self.power.index(OUT_NET[k])]
            pn = [float(p_cell[own == q].sum()) for q in nets]
            vm = [float(via_max[[j for j, vv in enumerate(self.vias_e) if vv['net'] == net]].max())
                  for net in (IN_NET[k], OUT_NET[k])]
            out['paths'][k] = {'I': i, 'i_shunt': float(i_sh),
                               'R_in': float((vp[ESC_SIDE] - vp['R.1']) / i), 'R_out': float((vp['R.4'] - vp[MOTOR_SIDE]) / i),
                               'P_in': pn[0], 'P_out': pn[1], 'P_shunt': float(i_sh ** 2 * R_SHUNT),
                               'shares': shares, 'via_max': vm,
                               'j_max': [float(jmag[l][((own[l] == nets[0]) | (own[l] == nets[1])) & self.j_mask[l]].max())
                                         for l in range(4)]}
        return out

    # --- heat
    def _heat_static(self):
        tg, own = self.tg, self.own_t
        nx, ny = tg.nx, tg.ny
        self.n_t = 4 * nx * ny
        cell = lambda l, i, j: (l * nx + i) * ny + j
        idx = np.arange(self.n_t).reshape(4, nx, ny)
        d = tg.d * 1e-3
        share = [self.tdiel[0] / 2, (self.tdiel[0] + self.tdiel[1]) / 2, (self.tdiel[1] + self.tdiel[2]) / 2, self.tdiel[2] / 2]
        a, b, g = [], [], []
        for l in range(4):
            for axis in (0, 1):
                o1, o2 = pairs(own[l], axis)
                gf = K_FR4_XY * share[l] + np.where((o1 >= 0) & (o1 == o2), K_CU * self.tcu[l], 0.0)
                i1, i2 = pairs(idx[l], axis)
                a.append(i1.ravel()); b.append(i2.ravel()); g.append(gf.ravel())
        gz = [np.full((nx, ny), K_FR4_Z * d * d / self.tdiel[l]) for l in range(3)]
        # pins of the connectors and shunts: one node each, tied to every cell of the hole
        refs = (ESC_SIDE, MOTOR_SIDE) + tuple(SHUNT.values())
        pin_pads = [p for p in self.geom['pads'] if p['ref'] in refs and p['drill'] > 0]
        self.pin_t = {(p['ref'], p['pad']): self.n_t + i for i, p in enumerate(pin_pads)}
        for p in pin_pads:
            ii, jj = tg.disc(p['xy'], p['drill'] / 2)
            for l in range(4):
                c = idx[l, ii, jj]
                a.append(c); b.append(np.full(len(c), self.pin_t[(p['ref'], p['pad'])])); g.append(np.full(len(c), G_PIN_T))
        # other plated holes: their barrel
        for bar in self.geom['barrels']:
            if bar['kind'] != 'via' and tuple(bar['kind'][4:].split('.')) in self.pin_t:
                continue
            i, j = tg.cell(bar['xy'])
            for l in range(3):
                length = self.tdiel[l] + (self.tcu[l] + self.tcu[l + 1]) / 2
                gz[l][i, j] += K_CU * np.pi * bar['drill'] * 1e-3 * PLATING / length
        for l in range(3):
            a.append(idx[l].ravel()); b.append(idx[l + 1].ravel()); g.append(gz[l].ravel())
        # PBV bodies on their pins
        self.body_t = {k: self.n_t + len(self.pin_t) + n for n, k in enumerate(PHASES)}
        g_spread = K_CU * PBV_SPREAD[1] / PBV_SPREAD[0]
        self.g_pin = {}
        for pad, wid in PBV_SHOULDER.items():
            gp = K_CU * wid * PBV_PIN_T / PBV_STANDOFF
            self.g_pin[pad] = 1 / (1 / gp + 1 / g_spread) if pad in '14' else gp
        for k in PHASES:
            for pad, gp in self.g_pin.items():
                a.append([self.body_t[k]]); b.append([self.pin_t[(SHUNT[k], pad)]]); g.append([gp])
        self.n_tot = self.n_t + len(self.pin_t) + len(PHASES)
        a, b, g = np.concatenate(a).astype(np.int64), np.concatenate(b).astype(np.int64), np.concatenate(g)
        self.heat_a0 = network(self.n_tot, a, b, g, np.zeros(self.n_tot))
        # The bodies stand side by side about 5.5 mm apart: the channel between two of them still
        # convects about as a free plate (Elenbaas: 9.8 instead of 10.2 W/m2K at 40 K), but two faces
        # looking at each other at the same temperature exchange almost no radiation. A body radiates
        # from its edges and from the faces that see the room.
        w, h, th = PBV_BODY
        self.body_area = 2 * w * h + 2 * h * th + w * th
        y = {k: self.pads[(SHUNT[k], '1')]['xy'][1] for k in PHASES}
        self.body_seen = {k: 2 * h * th + w * th + w * h * sum(
            not any(0 < s * (y[q] - y[k]) < 10 for q in PHASES if q != k) for s in (1, -1)) for k in PHASES}
        self.face_length = (self.geom['size_mm'][0] * self.geom['size_mm'][1]) / (2 * sum(self.geom['size_mm'])) * 1e-3

    def solve_heat(self, p_cells, p_nodes, rise):
        """Temperature rise above the air of every node; the surface losses use the previous rise."""
        nx, ny, d = self.tg.nx, self.tg.ny, self.tg.d * 1e-3
        cells = rise[:self.n_t].reshape(4, nx, ny)
        h = {'up': h_natural(float(cells[0].mean()), self.face_length, 'up'),
             'down': h_natural(float(cells[3].mean()), self.face_length, 'down')}
        ground = np.zeros(self.n_tot)
        top = (h['up'] + h_radiation(T_AMB + cells[0], EPS_MASK)) * d * d
        bot = (h['down'] + h_radiation(T_AMB + cells[3], EPS_MASK)) * d * d
        ground[:nx * ny] = top.ravel()
        ground[3 * nx * ny:4 * nx * ny] = bot.ravel()
        for k, node in self.body_t.items():
            dt = rise[node]
            ground[node] = (h_natural(dt, PBV_BODY[1], 'vertical') * self.body_area
                            + h_radiation(T_AMB + dt, PBV_EPS) * self.body_seen[k]) * self.body_loss
        rhs = np.zeros(self.n_tot)
        rhs[:self.n_t] = p_cells.ravel()
        for node, p in p_nodes.items():
            rhs[node] += p
        new = self.solver_t((self.heat_a0 + diags(ground)).tocsc(), rhs)
        loss = {'top': float(top.ravel() @ new[:nx * ny]), 'bottom': float(bot.ravel() @ new[3 * nx * ny:4 * nx * ny]),
                'bodies': float(sum(ground[nd] * new[nd] for nd in self.body_t.values()))}
        return new, h, loss

    # --- coupling
    def to_heat_grid(self, p_e):
        i0, i1, j0, j1 = self.win
        r = self.r
        p = np.zeros((4, self.tg.nx, self.tg.ny))
        p[:, i0:i1, j0:j1] = p_e.reshape(4, i1 - i0, r, j1 - j0, r).sum(axis=(2, 4))
        return p

    def to_current_grid(self, t_t):
        i0, i1, j0, j1 = self.win
        return np.repeat(np.repeat(t_t[:, i0:i1, j0:j1], self.r, axis=1), self.r, axis=2)

    def solve(self, current, case, rise=None, tol=0.02, max_iter=25, verbose=False):
        """Iterate current and heat for the three phases at the same RMS current."""
        currents = {k: current for k in PHASES}
        if rise is None:
            rise = np.full(self.n_tot, 10.0)
        for it in range(max_iter):
            t_cells = T_AMB + rise[:self.n_t].reshape(4, self.tg.nx, self.tg.ny)
            el = self.solve_current(currents, self.to_current_grid(t_cells))
            nodes = {}
            for k in PHASES:
                nodes[self.body_t[k]] = el['paths'][k]['P_shunt']
                if case == 'contacts':
                    for side in (ESC_SIDE, MOTOR_SIDE):
                        p = self.pin_pad(k, side)
                        nodes[self.pin_t[(p['ref'], p['pad'])]] = CONTACT_SHARE * current ** 2 * R_CONTACT
            p_t = self.to_heat_grid(el['p_cell'])
            new, h, loss = self.solve_heat(p_t, nodes, rise)
            change = float(np.abs(new - rise).max())
            rise = new
            if verbose:
                print('    iteration %d: largest change %.3f K' % (it + 1, change))
            if change < tol:
                break
        p_in = float(p_t.sum() + sum(nodes.values()))
        return self.summary(current, case, el, rise, h, loss, p_in, nodes, it + 1), el, rise

    def summary(self, current, case, el, rise, h, loss, p_in, nodes, iters):
        nx, ny = self.tg.nx, self.tg.ny
        t = T_AMB + rise
        cells = t[:self.n_t].reshape(4, nx, ny)
        s = {'I': current, 'case': case, 'iterations': iters, 'h_up': h['up'], 'h_down': h['down'],
             'P_total': p_in, 'P_lost': sum(loss.values()), 'loss': loss, 'paths': el['paths'],
             'P_contacts': float(sum(v for nd, v in nodes.items() if nd not in self.body_t.values())),
             'layers': [], 'phases': {}}
        for l in range(4):
            i, j = np.unravel_index(int(np.argmax(cells[l])), (nx, ny))
            s['layers'].append({'t_max': float(cells[l, i, j]), 'xy': [float(self.tg.x[i]), float(self.tg.y[j])],
                                't_mean': float(cells[l].mean())})
        for k in PHASES:
            ina = self.parts[INA[k]]['xy']
            i, j = self.tg.cell(ina)
            pins = {side: float(t[self.pin_t[(self.pin_pad(k, side)['ref'], self.pin_pad(k, side)['pad'])]])
                    for side in (ESC_SIDE, 'R.1', 'R.4', MOTOR_SIDE)}
            s['phases'][k] = {'t_body': float(t[self.body_t[k]]), 'pins': pins,
                              't_terminal': max(pins['R.1'], pins['R.4']), 't_ina': float(cells[3, i, j])}
        return s

    def report_raster(self):
        """Copper area of each phase pour after meshing, against the polygons."""
        print('phase pours after meshing (mm2 per layer, polygon area in brackets):')
        a_cell = self.eg.d ** 2
        for n, net in enumerate(self.power):
            ref = []
            for outlines in self.geom['nets'][net]:
                ar = 0.0
                for o in outlines:
                    p = np.asarray(o)
                    ar += 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
                ref.append(ar)
            got = [(self.own_e[l] == n).sum() * a_cell for l in range(4)]
            print('  %-6s %s' % (net, '  '.join('%6.1f (%6.1f)' % gr for gr in zip(got, ref))))
        print('  %d vias in the phase pours, %d via ends without copper of their net nearby' % (len(self.vias_e), self.vias_lost))


# ----------------------------------------------------------------------------- printing

def print_summary(s):
    print('\n%s, %.0f A rms in each phase: %d iterations, h = %.1f W/m2K (top) / %.1f (bottom) + radiation' % (
        CASES[s['case']], s['I'], s['iterations'], s['h_up'], s['h_down']))
    print('  heat %.3f W in, %.3f W out (top %.3f, bottom %.3f, shunt bodies %.3f)' % (
        s['P_total'], s['P_lost'], s['loss']['top'], s['loss']['bottom'], s['loss']['bodies']))
    print('  %-5s %9s %9s %8s %8s %8s %10s %10s' % ('phase', 'R J1-R', 'R R-J2', 'P cu in', 'P cu out', 'P shunt',
                                                    'I shunt', 'via max'))
    for k, p in s['paths'].items():
        print('  %-5s %6.3f mO %6.3f mO %6.3f W %6.3f W %6.3f W %8.3f A %6.2f/%.2f A' % (
            k, p['R_in'] * 1e3, p['R_out'] * 1e3, p['P_in'], p['P_out'], p['P_shunt'], p['i_shunt'], *p['via_max']))
        print('        current per layer L1/L2/L3/L6: J1 side %s, J2 side %s; max density %s A/mm2' % (
            '/'.join('%.0f%%' % (100 * x) for x in p['shares'][IN_NET[k]]),
            '/'.join('%.0f%%' % (100 * x) for x in p['shares'][OUT_NET[k]]),
            '/'.join('%.0f' % x for x in p['j_max'])))
    for l, ly in enumerate(s['layers']):
        print('  layer %d: max %.1f C at (%.1f, %.1f), mean %.1f C' % (l, ly['t_max'], *ly['xy'], ly['t_mean']))
    for k, ph in s['phases'].items():
        print('  %s: PBV body %.1f C, terminals %.1f / %.1f C, J1 pin %.1f C, J2 pin %.1f C, %s %.1f C' % (
            k, ph['t_body'], ph['pins']['R.1'], ph['pins']['R.4'], ph['pins'][ESC_SIDE], ph['pins'][MOTOR_SIDE],
            INA[k], ph['t_ina']))


def pbv_limit(current):
    """Highest terminal temperature the PBV derating allows at this current (no heatsink)."""
    p = current ** 2 * R_SHUNT / PBV_P_FREE
    return PBV_DERATE[1] - (PBV_DERATE[1] - PBV_DERATE[0]) * p if p <= 1 else float('nan')


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--current', type=float, help='one RMS current per phase, A (printed only)')
    ap.add_argument('--case', choices=tuple(CASES), default='board')
    ap.add_argument('--res', type=float, nargs=2, default=(RES_E, RES_T), metavar=('CURRENT', 'HEAT'),
                    help='grid steps in mm')
    args = ap.parse_args()

    model = PhasePaths(*args.res)
    if args.current is not None:
        t0 = time.time()
        s, _, _ = model.solve(args.current, args.case, verbose=True)
        print_summary(s)
        print('solved in %.0f s' % (time.time() - t0))
        return 0

    out = {'res': list(args.res), 'main': {}, 'sweep': {c: [] for c in CASES}}
    fields = {'tx': model.tg.x, 'ty': model.tg.y, 'ex': model.eg.x, 'ey': model.eg.y, 'own_e': model.own_e,
              'j_mask': model.j_mask}
    for case in CASES:
        t0 = time.time()
        s, el, rise = model.solve(I_MAIN, case)
        print_summary(s)
        print('  solved in %.0f s' % (time.time() - t0))
        out['main'][case] = s
        fields['T_' + case] = T_AMB + rise[:model.n_t].reshape(4, model.tg.nx, model.tg.ny)
        fields['J_' + case] = el['j']
        for i in SWEEP:
            si, _, _ = model.solve(i, case, rise=rise * (i / I_MAIN) ** 2)
            out['sweep'][case].append(si)
            print('  sweep %s %4.0f A: PBV terminal %.1f C, J pin %.1f C, board max %.1f C' % (
                case, i, max(p['t_terminal'] for p in si['phases'].values()),
                max(max(p['pins'][ESC_SIDE], p['pins'][MOTOR_SIDE]) for p in si['phases'].values()),
                max(ly['t_max'] for ly in si['layers'])))
    # The three bodies face each other 6 mm apart, so their own loss to the air (radiation especially)
    # is uncertain: bound it by none at all.
    model.body_loss = 0.0
    out['no_body_loss'] = {}
    for case in CASES:
        s, _, _ = model.solve(I_MAIN, case)
        out['no_body_loss'][case] = s
        print('without loss from the PBV bodies, %s: PBV terminal %.1f C, board max %.1f C' % (
            case, max(p['t_terminal'] for p in s['phases'].values()), max(ly['t_max'] for ly in s['layers'])))
    model.body_loss = 1.0
    # grid check: current grid halved, heat grid doubled
    checks = {}
    for res in ((args.res[0] / 2, args.res[1]), (args.res[0], args.res[1] * 2)):
        t0 = time.time()
        m2 = PhasePaths(*res, verbose=False)
        s2, _, _ = m2.solve(I_MAIN, 'board')
        checks['%g/%g' % res] = s2
        print('grid %g / %g mm: R J1-R1 %.4f mO, PBV U terminal %.2f C, board max %.2f C (%.0f s)' % (
            res[0], res[1], s2['paths']['U']['R_in'] * 1e3, s2['phases']['U']['t_terminal'],
            max(ly['t_max'] for ly in s2['layers']), time.time() - t0))
    out['grid_check'] = checks
    with open(RESULTS, 'w') as f:
        json.dump(out, f, indent=1)
    np.savez_compressed(FIELDS, **fields)
    print('%s and %s written; report.py makes the figures and results.md' % (
        os.path.basename(RESULTS), os.path.basename(FIELDS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
