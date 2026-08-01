"""Full-system audit — runs on the laptop (real runtime) and writes
verify_all.txt so results sync back for review. Checks every layer.
"""
import ast
import glob
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
out = []
def w(x): out.append(str(x))

w("PYTHON: " + sys.version.split()[0])

w("\n[1] SYNTAX")
files = ["main.py", "hourly_briefing.py", "send_test_alert.py"] + sorted(glob.glob("engine/*.py"))
bad = 0
for f in files:
    try:
        ast.parse(open(f, encoding="utf-8").read()); w(f"  OK   {f}")
    except Exception as e:  # noqa: BLE001
        bad += 1; w(f"  FAIL {f}: {e}")
w(f"  -> syntax_failures={bad}")

w("\n[2] IMPORTS")
try:
    from engine import (config, data_loader, signals, technicals,  # noqa: F401
                        journal, news_guard, backtest, ict, ltf, markets)
    import hourly_briefing  # noqa: F401
    import alert_signals    # noqa: F401
    w("  all engine modules import OK")
    ok_import = True
except Exception as e:  # noqa: BLE001
    w(f"  IMPORT FAIL: {e}"); ok_import = False

w("\n[3] UNIT TESTS")
r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                   capture_output=True, text=True)
tail = (r.stdout.strip().splitlines() or [r.stderr[-160:]])[-1]
w("  " + tail)

if ok_import:
    cfg = config.load()

    w("\n[4] CONFIG / ENV (no secrets shown)")
    w(f"  token_set={bool(cfg.telegram_bot_token)} "
      f"chat_set={bool(cfg.telegram_chat_id)} "
      f"channel={cfg.telegram_channel or 'MISSING'}")

    w("\n[5] HISTORICAL LOAD + BRIEFING BUILD")
    try:
        df = data_loader.load_csv(cfg.data_csv)
        m = hourly_briefing.build_message("XAUUSD", df)
        w(f"  csv_bars={len(df)} briefing_lines={len(m.splitlines())} "
          f"track={'TRACK RECORD' in m} tech={'TECHNICALS' in m} "
          f"news_line={'NEWS' in m or 'NEXT HIGH' in m}")
    except Exception as e:  # noqa: BLE001
        w(f"  FAIL: {e}"); df = None

    w("\n[6] NEWS GUARD (live calendar)")
    try:
        s = news_guard.evaluate()
        w(f"  ok={s.get('ok')} blackout={s.get('blackout')} next={s.get('next')}")
    except Exception as e:  # noqa: BLE001
        w(f"  FAIL: {e}")

    w("\n[7] JOURNAL STATE")
    try:
        w("  " + str(journal.stats()))
    except Exception as e:  # noqa: BLE001
        w(f"  FAIL: {e}")

    w("\n[8] LIVE DATA FETCH")
    try:
        dfl = data_loader.fetch_live(cfg)
        w(f"  live_bars={len(dfl)} last={dfl.index[-1]} "
          f"px={float(dfl['Close'].iloc[-1]):.2f}")
    except Exception as e:  # noqa: BLE001
        w(f"  FAIL: {e}")

    w("\n[9] BACKTEST SANITY (2025-05..06, after costs)")
    try:
        if df is not None:
            st = backtest.run(df, start="2025-05-01", end="2025-06-30")
            st.pop("trade_list", None)
            w("  " + str(st))
    except Exception as e:  # noqa: BLE001
        w(f"  FAIL: {e}")

w("\nDONE")
(ROOT / "verify_all.txt").write_text("\n".join(out), encoding="utf-8")
print("audit complete")
