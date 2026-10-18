"""Checks of the current and heat discretisation of power_paths.py against closed-form solutions.

    current  a copper ring of 70 um fed by a pin of the J1 size (r = 1.45 mm) at its centre and held
             at 10 mm, the pin tied to the cells of its hole as in power_paths.py:
                 R = rho ln(b / a) / (2 pi t)
    heat     an endless copper sheet of 70 um losing heat on both faces (h each), 1 W spread over a
             disc of 1.5 mm:
                 T(r) = q / (2 h) * (a / L) I1(a / L) K0(r / L),   L = sqrt(k t / (2 h)),  q = P / (pi a^2)

    C:\\openEMS\\venv\\Scripts\\python.exe validate_solver.py      (about 1 min)
"""
import sys

import numpy as np
from scipy.sparse.linalg import spsolve
from scipy.special import i1, k0

import power_paths as pp


def ring(d):
    a, b, t = 1.45, 10.0, 70e-6
    grid = pp.Grid(-b - 1, b + 1, -b - 1, b + 1, d)
    X, Y = np.meshgrid(grid.x, grid.y, indexing='ij')
    r = np.hypot(X, Y)
    idx = np.arange(grid.nx * grid.ny).reshape(grid.nx, grid.ny)
    pin = idx.size
    a_, b_, g_ = [], [], []
    for axis in (0, 1):
        i1_, i2_ = pp.pairs(idx, axis)
        a_.append(i1_.ravel()); b_.append(i2_.ravel()); g_.append(np.full(i1_.size, t / pp.RHO_20))
    inner = idx[r <= a]
    a_.append(inner); b_.append(np.full(len(inner), pin)); g_.append(np.full(len(inner), pp.G_PIN_E))
    ground = np.zeros(idx.size + 1)
    ground[idx[r >= b]] = pp.G_GROUND_E
    rhs = np.zeros(idx.size + 1)
    rhs[pin] = 1.0
    m = pp.network(idx.size + 1, np.concatenate(a_), np.concatenate(b_), np.concatenate(g_), ground)
    return spsolve(m, rhs)[pin]


def sheet(d, h=100.0):
    k, t, a, p = pp.K_CU, 70e-6, 1.5e-3, 1.0
    length = np.sqrt(k * t / (2 * h))
    half = 6 * length * 1e3
    grid = pp.Grid(-half, half, -half, half, d)
    X, Y = np.meshgrid(grid.x, grid.y, indexing='ij')
    r = np.hypot(X, Y) * 1e-3
    idx = np.arange(grid.nx * grid.ny).reshape(grid.nx, grid.ny)
    a_, b_, g_ = [], [], []
    for axis in (0, 1):
        i1_, i2_ = pp.pairs(idx, axis)
        a_.append(i1_.ravel()); b_.append(i2_.ravel()); g_.append(np.full(i1_.size, k * t))
    cell = (d * 1e-3) ** 2
    rhs = np.where(r <= a, p / (r <= a).sum(), 0.0).ravel()
    m = pp.network(idx.size, np.concatenate(a_), np.concatenate(b_), np.concatenate(g_), np.full(idx.size, 2 * h * cell))
    temp = spsolve(m, rhs).reshape(grid.nx, grid.ny)
    q = p / (np.pi * a * a)
    exact = lambda rr: q / (2 * h) * (a / length) * i1(a / length) * k0(rr / length)
    out = []
    for rr in (3e-3, 6e-3, 12e-3, 24e-3):
        j = int(np.argmin(np.abs(grid.y * 1e-3 - 0)))
        i = int(np.argmin(np.abs(grid.x * 1e-3 - rr)))
        out.append((rr, temp[i, j], exact(np.hypot(grid.x[i], grid.y[j]) * 1e-3)))
    return length, out


def main():
    exact = pp.RHO_20 * np.log(10.0 / 1.45) / (2 * np.pi * 70e-6)
    print('current: ring 1.45 / 10 mm, 70 um copper, exact R = %.4f mOhm' % (exact * 1e3))
    for d in (0.1, 0.05):
        r = ring(d)
        print('  grid %.2f mm: %.4f mOhm (%+.2f %%)' % (d, r * 1e3, 100 * (r / exact - 1)))
    for d in (0.2, 0.1):
        length, rows = sheet(d)
        print('heat: copper sheet 70 um, h = 100 W/m2K per face (L = %.1f mm), 1 W on a 1.5 mm disc, grid %.1f mm'
              % (length * 1e3, d))
        for rr, got, ex in rows:
            print('  r = %4.0f mm: %.4f K, exact %.4f K (%+.2f %%)' % (rr * 1e3, got, ex, 100 * (got / ex - 1)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
