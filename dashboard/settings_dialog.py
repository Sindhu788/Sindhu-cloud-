from PySide6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QSpinBox, QLineEdit, QDialogButtonBox,
    QGroupBox, QGridLayout, QCheckBox, QVBoxLayout,
)

from data_engine import config
from data_engine.exchanges.registry import ALL_EXCHANGE_IDS

_ALL_TIMEFRAMES = [
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
]


class SettingsDialog(QDialog):
    """Lets the CEO edit exchange, coin count, quote asset, history depth
    and enabled timeframes. Reads/writes data/config/*.json directly so
    changes take effect the next time SINDHU is started -- no code edits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SINDHU Settings")
        self.setMinimumWidth(420)

        exchanges_cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
        coins_cfg = config.load_or_seed("coins.json", config.DEFAULTS["coins.json"])
        timeframes_cfg = config.load_or_seed("timeframes.json", config.DEFAULTS["timeframes.json"])
        app_cfg = config.load_or_seed("app_settings.json", config.DEFAULTS["app_settings.json"])

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(ALL_EXCHANGE_IDS)
        self.exchange_combo.setCurrentText(exchanges_cfg["default"])
        form.addRow("Default Exchange:", self.exchange_combo)

        self.num_coins_spin = QSpinBox()
        self.num_coins_spin.setRange(1, 200)
        self.num_coins_spin.setValue(coins_cfg["num_coins"])
        form.addRow("Number of Coins:", self.num_coins_spin)

        self.quote_asset_edit = QLineEdit(coins_cfg["quote_asset"])
        form.addRow("Quote Asset:", self.quote_asset_edit)

        self.history_days_spin = QSpinBox()
        self.history_days_spin.setRange(1, 3650)
        self.history_days_spin.setValue(app_cfg["history_days"])
        form.addRow("History (days):", self.history_days_spin)

        layout.addLayout(form)

        tf_box = QGroupBox("Timeframes")
        tf_grid = QGridLayout(tf_box)
        self._tf_checks = {}
        enabled_tfs = set(timeframes_cfg["supported"])
        for i, tf in enumerate(_ALL_TIMEFRAMES):
            cb = QCheckBox(tf)
            cb.setChecked(tf in enabled_tfs)
            self._tf_checks[tf] = cb
            tf_grid.addWidget(cb, i // 4, i % 4)
        layout.addWidget(tf_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self):
        config.save_config("exchanges.json", {
            **config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"]),
            "default": self.exchange_combo.currentText(),
        })
        config.save_config("coins.json", {
            "num_coins": self.num_coins_spin.value(),
            "quote_asset": self.quote_asset_edit.text().strip().upper(),
        })
        config.save_config("timeframes.json", {
            "base_interval": "1m",
            "supported": [tf for tf, cb in self._tf_checks.items() if cb.isChecked()],
        })
        config.save_config("app_settings.json", {
            **config.load_or_seed("app_settings.json", config.DEFAULTS["app_settings.json"]),
            "history_days": self.history_days_spin.value(),
        })
        self.accept()
