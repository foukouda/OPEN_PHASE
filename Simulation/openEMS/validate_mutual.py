"""Check of the extraction used by shunt_coupling.py on a case with a known answer.

Two thin rectangular loops in the same vertical plane, the small one inside the large one, like the
Kelvin window of a PBV shunt under its current path. The large loop is driven through a 50 ohm
lumped port, the small one is read through a 1 Mohm lumped port, exactly as in shunt_coupling.py.
openEMS gives M = Im(V / I) / w; the Neumann double integral over the same two paths gives the
reference. This validates the sign conventions of the ports and the accuracy of the mesh step. The
flux of the H field through the small loop, which report.py uses to split the flux of a Kelvin loop
into its parts, is checked against the same M.

    C:\\openEMS\\venv\\Scripts\\python.exe validate_mutual.py            (about 3 min)
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, 'run', 'validate')
MU0 = 4e-7 * np.pi
F0 = FC = 200e6
RES = 0.2
DRIVE = (-9.0, 9.0, 0.0, 5.0)        # x0, x1, z0, z1 of the driven loop, mm (port in its bottom side)
SENSE = (-4.0, 4.0, 1.0, 3.6)        # the read loop (port in its bottom side), mm
F_FIT = (10e6, 100e6)
F_FLUX = 50e6


def neumann(a, b, n=4000):
    """Mutual inductance of two closed rectangular filaments in the plane y = 0, H."""
    def path(r):
        x0, x1, z0, z1 = r
        c = np.array([[x0, z0], [x1, z0], [x1, z1], [x0, z1], [x0, z0]]) * 1e-3
        t = np.linspace(0, 1, n, endpoint=False)
        seg = [c[i] + np.outer(t, c[i + 1] - c[i]) for i in range(4)]
        d = [np.tile(c[i + 1] - c[i], (n, 1)) / n for i in range(4)]
        return np.vstack(seg) + np.vstack(d) / 2, np.vstack(d)
    p1, d1 = path(a)
    p2, d2 = path(b)
    m = 0.0
    for k in range(0, len(p1), 500):
        r = np.linalg.norm(p1[k:k + 500, None, :] - p2[None, :, :], axis=2)
        m += np.sum((d1[k:k + 500] @ d2.T) / r)
    return MU0 / (4 * np.pi) * m


def main():
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    fdtd = openEMS(EndCriteria=1e-9, MaxTime=2 * 9 / (2 * np.pi * FC) + 3e-9, OverSampling=1000)
    fdtd.SetGaussExcite(F0, FC)
    fdtd.SetBoundaryCond(['MUR'] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    grid = csx.GetGrid()
    grid.SetDeltaUnit(1e-3)
    # exact values: a box of zero width only becomes metal on a mesh line that it hits exactly
    fine = np.round(np.arange(-12, 12 + RES / 2, RES), 6)
    grid.AddLine('x', np.r_[-40, -30, -22, -17, -14, fine, 14, 17, 22, 30, 40])
    grid.AddLine('y', np.r_[-40, -30, -22, -15, -10, -6, -3.5, -2, -1, -0.4, 0, 0.4, 1, 2, 3.5, 6, 10, 15, 22, 30, 40])
    grid.AddLine('z', np.r_[-40, -30, -22, -15, -10, -6, -3.5, -2, -1, -0.4, np.round(np.arange(0, 8 + RES / 2, RES), 6), 9, 11, 14, 19, 26, 34, 45])

    ports = []
    for n, (r, rp, ex) in enumerate(((DRIVE, 50.0, 1.0), (SENSE, 1e6, 0.0))):
        x0, x1, z0, z1 = r
        wire = csx.AddMetal('loop%d' % n)
        # the bottom side has a one-cell gap at x = 0 .. RES for the port, read from -x to +x
        for a, b in (((RES, z0), (x1, z0)), ((x1, z0), (x1, z1)), ((x1, z1), (x0, z1)),
                     ((x0, z1), (x0, z0)), ((x0, z0), (0, z0))):
            wire.AddBox([a[0], 0, a[1]], [b[0], 0, b[1]], priority=10)
        ports.append(fdtd.AddLumpedPort(n + 1, rp, [0, 0, z0], [RES, 0, z0], 'x', excite=ex))
    # H in the plane of the loops, to check the flux integral used by shunt_coupling.py
    x0, x1, z0, z1 = SENSE
    csx.AddDump('H_plane', dump_type=11, dump_mode=2, file_type=1,
                frequency=[F_FLUX]).AddBox([x0 - 1, 0, z0 - 1], [x1 + 1, 0, z1 + 1])

    os.makedirs(RUN, exist_ok=True)
    fdtd.Run(RUN, cleanup=True, verbose=0)
    f = np.linspace(5e6, 150e6, 59)
    for p in ports:
        p.CalcPort(RUN, f)
    # A lumped port reads u = V(stop) - V(start) and its current i leaves it at the stop terminal.
    # The drive current therefore runs +x along the bottom of the large loop, and the small loop is
    # read the same way round: around the open loop the EMF -jw.M.i equals -u, so u = +jw.M.i.
    h = ports[1].uf_tot / ports[0].if_tot
    w = 2 * np.pi * f
    band = (f >= F_FIT[0]) & (f <= F_FIT[1])
    m_fdtd = np.median(h.imag[band] / w[band])
    m_ref = neumann(DRIVE, SENSE)
    print('Neumann integral : M = %.4f nH' % (m_ref * 1e9))
    print('openEMS          : M = %.4f nH  (median of Im(V/I)/w, %g-%g MHz, spread %.2f %%)' % (
        m_fdtd * 1e9, F_FIT[0] / 1e6, F_FIT[1] / 1e6,
        100 * np.ptp(h.imag[band] / w[band]) / abs(m_fdtd)))
    print('real part / imaginary part at 50 MHz: %.3f' % (np.interp(50e6, f, h.real) / np.interp(50e6, f, h.imag)))
    print('difference       : %+.2f %%' % (100 * (m_fdtd / m_ref - 1)))
    # The same M from the flux of H through the small loop. The plane dump comes out about 2 % low (its
    # values sit at the cell centres, half a cell off the plane of the wires): good enough to share the
    # flux between regions, as shunt_coupling.py does, not to replace the port reading.
    import h5py
    i_flux = np.interp(F_FLUX, f, ports[0].if_tot.real) + 1j * np.interp(F_FLUX, f, ports[0].if_tot.imag)
    with h5py.File(os.path.join(RUN, 'H_plane.h5'), 'r') as h5:
        xc, zc = h5['Mesh']['x'][...] * 1e3, h5['Mesh']['z'][...] * 1e3
        hy = (h5['FieldData/FD/f0_real'][...] + 1j * h5['FieldData/FD/f0_imag'][...])[1, :, 0, :]   # (z, x)
    inside = np.outer((zc > z0) & (zc < z1), (xc > x0) & (xc < x1))
    # the small loop runs +x along its bottom and +z up its right side: its normal is -y
    m_flux = (-4e-7 * np.pi * np.sum(hy[inside]) * (RES * 1e-3) ** 2 / i_flux).real
    print('flux of H        : M = %.4f nH (%+.2f %% from the port)' % (m_flux * 1e9, 100 * (m_flux / m_fdtd - 1)))
    return 0 if abs(m_fdtd / m_ref - 1) < 0.05 and abs(m_flux / m_fdtd - 1) < 0.05 else 1


if __name__ == '__main__':
    sys.exit(main())
