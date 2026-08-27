# -*- coding: utf-8 -*-
"""Rig bound split and cadence, per cell.

CLAUDE.md carried this table for cislunar only, where beneficiation swaps the
two bounds over. This extended it to every destination; the result is now in
CLAUDE.md under "The rig's two bounds, and the cadence, at every destination",
where mars_surface inverts both splits.
"""
import glob, gzip, os
import pandas as pd

print(f"{'cell':42s} {'cycle%':>8s} {'cal%':>8s} {'window%':>9s} {'dig%':>7s} "
      f"{'cadence med':>12s} {'span med':>9s} {'W<trips':>9s}")
for p in sorted(glob.glob(os.path.join('campaign', 'cells', '*.csv.gz'))):
    cell = os.path.basename(p)[:-7]
    cols = ['rig_trip_limit_binds', 'cadence_window_bound', 'campaign_cadence_yr',
            'programme_span_yr', 'missions_per_ship', 'trips_per_ship']
    with gzip.open(p, 'rb') as fh:
        head = pd.read_csv(fh, nrows=0)
    use = [c for c in cols if c in head.columns]
    with gzip.open(p, 'rb') as fh:
        d = pd.read_csv(fh, low_memory=False, usecols=use)

    def pct(col, val):
        if col not in d.columns:
            return float('nan')
        s = d[col]
        if s.dtype == object:
            return 100.0 * s.astype(str).str.lower().isin(['true', '1', '1.0']).mean()
        return 100.0 * (s == val).mean()

    cyc = pct('rig_trip_limit_binds', True)
    win = pct('cadence_window_bound', True)
    cad = d['campaign_cadence_yr'].median() if 'campaign_cadence_yr' in d else float('nan')
    spn = d['programme_span_yr'].median() if 'programme_span_yr' in d else float('nan')
    wlt = (100.0 * (d['missions_per_ship'] < d['trips_per_ship']).mean()
           if {'missions_per_ship', 'trips_per_ship'} <= set(d.columns) else float('nan'))
    print(f"{cell:42s} {cyc:7.2f}% {100-cyc:7.2f}% {win:8.2f}% {100-win:6.2f}% "
          f"{cad:11.4f} {spn:8.4f} {wlt:8.3f}%")
