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


def test_requests_of_a_page_that_was_left_are_dropped_but_global_polls_are_not():
    js = _read("js/lite_mode.js")
    for needle in ("pageEpoch", 'addEventListener("hashchange"', "GLOBAL_POLL", "epoch !== pageEpoch", "never settle"):
        assert needle in js
    glob = js[js.index("var GLOBAL_POLL"):js.index("var pageEpoch")]
    for must_stay in ("activity", "home", "ops", "paper-trading\/status", "dashboard-badge-status", "health"):
        assert must_stay in glob
    assert "system" not in glob and "alert" not in glob      # page data must be droppable


def test_owner_alert_ui_has_validation_and_an_owner_only_test_button():
    app = _read("js/app.js")
    for needle in ('id="btnTestOwnerAlert"', "/api/ops/test-owner-alert", "Send test alert to my chat", "plainApiError", r"/^-?\d{5,16}$/"):
        assert needle in app
    assert app.count("/api/ops/test-owner-alert") == 1            # only the button's handler calls it
