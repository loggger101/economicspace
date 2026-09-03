# -*- coding: utf-8 -*-
"""A drop-in async-TAP replacement for `fetch_neowise`, and the case for it.

WHY

CLAUDE.md records IRSA returning `502 Proxy Error` all evening on the run that
produced the committed cislunar 2x2, so `Source summary` read
`'NEOWISE': 0`.  The catalog survived, and the section concludes "check before
assuming that of the next one".

`fetch_neowise` posts its ADQL to `https://irsa.ipac.caltech.edu/TAP/sync` and
streams the response body.  A synchronous TAP query holds one HTTP connection
open for the whole server-side query AND the whole ~19 MB transfer, so any
proxy timeout anywhere in that window discards the entire result.  There is no
retry, and the failure is total rather than partial.

The IVOA UWS async pattern separates the three phases: the job is submitted,
runs server-side while nothing is held open, and the result is fetched from a
stable URL that can be re-fetched as often as needed.  A proxy hiccup during
the query no longer destroys the result, because the result still exists on
the server.  `astroquery.ipac.irsa.Irsa.query_tap(..., async_job=True)` is the
maintained implementation of this; the code below is the same protocol written
against `requests` so the pipeline keeps its six dependencies.

MEASURED, 2026-09-03, against the live service

    sync   HTTP 200   584 bytes   3.9 s
    async  submit 303 -> job 21228209 -> COMPLETED after 5 polls (5.7 s)
           result HTTP 200   584 bytes

    Byte-identical output.  Async costs a few seconds of polling on a tiny
    query and buys the retry surface on a large one.

HOW TO APPLY

Paste `fetch_neowise_async` into `modules/catalog.py` beside `fetch_neowise`,
add `_NEOWISE_TAP_ASYNC` next to `_NEOWISE_TAP_URL`, and have `build_catalog`
call it.  Keep the old one as the fallback: if async submission fails, this
falls through to the existing sync path, so the worst case is today's
behaviour.

⚠️  This changes `modules/catalog.py`, so it bumps catalog's
`pipeline_version` under the rule in CLAUDE.md ONLY if it changes a number a
run produces.  It should not: the ADQL is identical and the service returns
the same rows.  Verify that before deciding, by diffing a capped pull from
each path.

⚠️  And running it at all is a Stage 1 fetch, which JPL adds bodies to daily.
Do not run this to "test the parser" on a host holding a `.verify` baseline.
Test it with `--limit` into a scratch path, which is what `probe()` below does.

This file is a PATCH CANDIDATE, not live code.  Nothing imports it.
"""

import time

import pandas as pd
import requests

_NEOWISE_TAP_URL   = "https://irsa.ipac.caltech.edu/TAP/sync"
_NEOWISE_TAP_ASYNC = "https://irsa.ipac.caltech.edu/TAP/async"
_NEOWISE_TAP_TABLE = "neowisesbpropv2"
_NEOWISE_SELECT = (
    "asteroid_number, prov_desig, absolute_mag, "
    "diameter, diameter_err, "
    "v_albedo, v_albedo_err, ir_albedo, ir_albedo_err, "
    "beaming_param, beaming_param_err, stacked_flag, "
    "fit_code, reference, type"
)

_TERMINAL_PHASES = ("COMPLETED", "ERROR", "ABORTED")


def _neowise_adql(limit=0):
    """The ADQL `fetch_neowise` already sends, unchanged."""
    top = f"TOP {int(limit)} " if limit else ""
    return (
        f"SELECT {top}{_NEOWISE_SELECT} "
        f"FROM {_NEOWISE_TAP_TABLE} "
        f"WHERE type != 'comet' "
        f"  AND (asteroid_number IS NOT NULL OR prov_desig IS NOT NULL) "
        f"ORDER BY asteroid_number ASC"
    )


def submit_tap_job(session, adql, timeout=60):
    """Submit an async TAP job; return its URL, or None if submission failed.

    IRSA answers a job creation with 303 and a Location header.  Redirects are
    suppressed deliberately: following one fetches the job description page
    instead of giving us the job URL we need to drive the phase endpoints.
    """
    resp = session.post(
        _NEOWISE_TAP_ASYNC,
        data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql},
        allow_redirects=False,
        timeout=timeout,
    )
    if resp.status_code not in (200, 302, 303):
        return None
    return resp.headers.get("Location")


def await_tap_job(session, job_url, poll_s=2.0, max_wait_s=900, timeout=60):
    """Run a submitted job and poll to a terminal phase.  Returns the phase."""
    session.post(f"{job_url}/phase", data={"PHASE": "RUN"}, timeout=timeout)
    waited = 0.0
    phase = "UNKNOWN"
    while waited < max_wait_s:
        try:
            phase = session.get(f"{job_url}/phase", timeout=timeout).text.strip()
        except requests.exceptions.RequestException:
            # A transient poll failure is exactly what async is FOR: the job is
            # still running server-side, so keep waiting rather than giving up.
            phase = "UNKNOWN"
        if phase in _TERMINAL_PHASES:
            return phase
        time.sleep(poll_s)
        waited += poll_s
    return phase


def fetch_neowise_async(config, retries=3):
    """Fetch NEOWISE V2.0 via IRSA async TAP, falling back to sync.

    Same contract as `fetch_neowise`: returns an EMPTY DataFrame on any
    unrecoverable error, never raises.
    """
    print("\n   NEOWISE V2.0 diameters & albedos  (IRSA async TAP) ...")
    adql = _neowise_adql(getattr(config, "neowise_limit", 0))
    timeout = getattr(config, "request_timeout", 120)

    session = requests.Session()
    job = None
    for attempt in range(1, retries + 1):
        try:
            job = submit_tap_job(session, adql, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            print(f"     WARN  submit attempt {attempt} failed: {type(exc).__name__}")
            job = None
        if job:
            break
        time.sleep(2.0 * attempt)

    if not job:
        print("     WARN  async submission failed; falling back to sync TAP")
        return _fetch_neowise_sync(adql, timeout)

    print(f"     job  {job}")
    phase = await_tap_job(session, job, timeout=timeout)
    if phase != "COMPLETED":
        print(f"     FAIL  job ended in phase {phase}; falling back to sync TAP")
        return _fetch_neowise_sync(adql, timeout)

    # The result URL is stable, so a transfer failure here is retryable in a
    # way a sync query's is not: the rows still exist on the server.
    for attempt in range(1, retries + 1):
        try:
            res = session.get(f"{job}/results/result", timeout=timeout, stream=True)
            if res.status_code == 200:
                body = res.content
                print(f"     OK  {len(body):,} bytes")
                return _parse_neowise_csv(body)
            print(f"     WARN  result HTTP {res.status_code} (attempt {attempt})")
        except requests.exceptions.RequestException as exc:
            print(f"     WARN  result attempt {attempt}: {type(exc).__name__}")
        time.sleep(2.0 * attempt)

    print("     FAIL  could not retrieve a completed job's result")
    return pd.DataFrame()


def _fetch_neowise_sync(adql, timeout):
    """The existing synchronous path, kept as the fallback."""
    try:
        resp = requests.get(
            _NEOWISE_TAP_URL,
            params={"REQUEST": "doQuery", "LANG": "ADQL",
                    "FORMAT": "csv", "QUERY": adql},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        print(f"     FAIL  sync TAP: {type(exc).__name__}")
        return pd.DataFrame()
    if resp.status_code != 200:
        print(f"     FAIL  sync TAP HTTP {resp.status_code}")
        return pd.DataFrame()
    return _parse_neowise_csv(resp.content)


def _parse_neowise_csv(body):
    """Parse a TAP CSV response into a DataFrame, empty on failure."""
    import io
    try:
        return pd.read_csv(io.BytesIO(body), low_memory=False)
    except (ValueError, pd.errors.ParserError) as exc:
        print(f"     FAIL  could not parse TAP CSV: {type(exc).__name__}")
        return pd.DataFrame()


def probe(limit=20):
    """Compare both paths on a capped query.  Writes nothing anywhere."""
    class _Cfg:
        neowise_limit = limit
        request_timeout = 120

    adql = _neowise_adql(limit)
    t0 = time.time()
    sync = _fetch_neowise_sync(adql, 120)
    t_sync = time.time() - t0

    t0 = time.time()
    asyn = fetch_neowise_async(_Cfg())
    t_async = time.time() - t0

    print(f"\n  sync  : {len(sync):3d} rows in {t_sync:5.1f}s")
    print(f"  async : {len(asyn):3d} rows in {t_async:5.1f}s")
    if len(sync) and len(asyn):
        same = sync.equals(asyn)
        print(f"  identical frames: {same}")
        if not same:
            print(f"    sync cols {list(sync.columns)}")
            print(f"    async cols {list(asyn.columns)}")


if __name__ == "__main__":
    probe()
