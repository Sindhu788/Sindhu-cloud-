import os

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sindhu_web", "static")


def _read(rel):
    return open(os.path.join(STATIC, rel), encoding="utf-8").read()


def test_lite_layer_loads_before_app_js_and_has_the_documented_controls():
    html = _read("index.html")
    assert html.index("/static/js/lite_mode.js") < html.index("/static/js/app.js")
    js = _read("js/lite_mode.js")
    for needle in ("MAX_PARALLEL", "TTL_MS", "Server waking up, retrying", "sindhu_lite", "cache = Object.create(null)"):
        assert needle in js


def test_non_critical_polling_is_slowed_and_waking_state_replaces_offline():
    app = _read("js/app.js")
    assert "setInterval(refreshTopbarStatus, 30000)" in app
    assert "refreshNotifications(false), 45000)" in app
    assert "server waking up, retrying" in app and '"\u25cf offline"' not in app
    assert "timeoutMs = 40000" in app


def test_version_history_handler_survives_leaving_the_page_while_loading():
    app = _read("js/app.js")
    i = app.index('document.getElementById("versionHistoryTitle").textContent')
    assert 'if (!document.getElementById("versionHistoryTitle")' in app[i - 400:i]


def test_settings_loaders_tolerate_the_page_being_left_while_loading():
    app = _read("js/app.js")
    for needle in ('(document.getElementById("tgLogBody") || {}).innerHTML', 'getElementById("tgChannelOverridesBox") || {}',
                   'getElementById("syncBandwidthStats") || {}', 'if (!document.getElementById("healthRestartCount")) return;'):
        assert needle in app
