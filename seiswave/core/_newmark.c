/*
 * Fast Newmark-beta SDOF response spectrum computation.
 * Compiled as shared library, called via ctypes.
 */
#include <math.h>
#include <stdlib.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define TWO_PI (2.0 * M_PI)
#define MPR 20

/*
 * Compute absolute acceleration response spectrum for multiple periods.
 * acc: input acceleration array (n elements)
 * n: number of time steps
 * dt: time step
 * zeta: damping ratio
 * periods: array of periods (nP elements)
 * nP: number of periods
 * spa: output spectral acceleration (nP elements, signed)
 * spi: output peak index (nP elements, 1-based)
 */
void newmark_spectrum(const double *acc, int n, double dt, double zeta,
                      const double *periods, int nP,
                      double *spa, int *spi)
{
    int ip, i, j, r;
    double T, omega, k, c, sub_dt;
    double beta, gamma;
    double b1, b2, b3, b4, b5, b6;
    double keff_inv;
    double rl0, rl1, rl2, al, ac, da, ac_sub, feff, rc0, rc1, rc2;
    double abs_a, max_abs, spa_val;
    int max_idx;

    beta = 0.25;
    gamma = 0.5;

    for (ip = 0; ip < nP; ip++) {
        T = periods[ip];
        omega = TWO_PI / T;
        k = omega * omega;
        c = 2.0 * zeta * omega;

        if (dt * MPR > T) {
            r = (int)ceil(MPR * dt / T);
            sub_dt = dt / r;
        } else {
            r = 1;
            sub_dt = dt;
        }

        b1 = 1.0 / (beta * sub_dt * sub_dt);
        b2 = 1.0 / (beta * sub_dt);
        b3 = 1.0 / (2.0 * beta) - 1.0;
        b4 = gamma / (beta * sub_dt);
        b5 = gamma / beta - 1.0;
        b6 = 0.5 * sub_dt * (gamma / beta - 2.0);
        keff_inv = 1.0 / (k + b1 + b4 * c);

        rl0 = 0.0; rl1 = 0.0; rl2 = 0.0;
        al = 0.0;
        max_abs = 0.0;
        max_idx = 0;
        spa_val = 0.0;

        for (i = 0; i < n; i++) {
            ac = acc[i];
            da = (ac - al) / (double)r;

            for (j = 1; j <= r; j++) {
                ac_sub = al + da * j;
                feff = ac_sub + (b1 * rl0 + b2 * rl1 + b3 * rl2)
                       + c * (b4 * rl0 + b5 * rl1 + b6 * rl2);
                rc0 = feff * keff_inv;
                rc1 = b4 * (rc0 - rl0) - b5 * rl1 - b6 * rl2;
                rc2 = ac_sub - k * rc0 - c * rc1;
                rl0 = rc0; rl1 = rc1; rl2 = rc2;
            }

            abs_a = fabs(-rl2 + acc[i]);
            if (abs_a > max_abs) {
                max_abs = abs_a;
                max_idx = i;
                spa_val = -rl2 + acc[i];
            }
            al = acc[i];
        }

        spa[ip] = spa_val;
        spi[ip] = max_idx + 1;  /* 1-based */
    }
}
