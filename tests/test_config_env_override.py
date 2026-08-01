"""Config.load() must work identically whether settings come from a local
.env file (laptop) or from real OS environment variables (GitHub Actions /
any cloud runner injects secrets this way, never as a .env file on disk).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import config  # noqa: E402


def test_env_vars_used_when_no_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-from-env")
    monkeypatch.setenv("SYMBOLS", "WTIUSD")
    monkeypatch.setenv("MAX_DAILY_LOSS_R", "3")
    missing_path = tmp_path / "does_not_exist.env"

    s = config.load(missing_path)
    assert s.telegram_bot_token == "tok-from-env"
    assert s.symbols == "WTIUSD"
    assert s.max_daily_loss_r == 3  # int coercion preserved


def test_env_vars_override_file(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("TELEGRAM_BOT_TOKEN=tok-from-file\nSYMBOLS=XAUUSD\n")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-from-env-wins")

    s = config.load(envf)
    assert s.telegram_bot_token == "tok-from-env-wins"
    assert s.symbols == "XAUUSD"  # untouched field still comes from the file


def test_telegram_channel_per_symbol_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_WTIUSD", "@us_oil_channel")
    missing_path = tmp_path / "does_not_exist.env"

    s = config.load(missing_path)
    assert s.symbol_channels.get("WTIUSD") == "@us_oil_channel"
