"""paper_trading/config.py's coin_filter_top_n default and
data_engine/config.py's num_coins default must agree -- otherwise a
brand-new installation (a fresh local dev setup, or the lightweight cloud
runner, which starts with none of the CEO's real saved settings) would
fetch a full 50-coin pool but then narrow it down to a much smaller
real-time shortlist for no reason, silently scanning far fewer coins than
"the standard for the rest of the system" (the CEO's own real, already-
configured local value, which lives in a plain settings file never
migrated to the cloud database).

This only pins the DEFAULT used when no settings file exists yet -- an
existing installation's own saved value (data/config/paper_trading_
settings.json) is untouched by this default either way, since
data_engine.config.load_or_seed only ever applies a default once, before
that file exists.
"""

import tempfile

from data_engine import config as base_config
from paper_trading import config as pt_config


def test_fresh_install_coin_filter_top_n_matches_the_full_coin_universe(monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", tempfile.mkdtemp())
    settings = pt_config.load()
    assert settings["coin_filter_top_n"] == base_config.NUM_COINS == 50
