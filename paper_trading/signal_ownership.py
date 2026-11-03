"""One public signal publisher across Main and Cloud.

Cloud owns public delivery by default; Main remains the research interface.
Private notifications (the personal chat) are never blocked by this guard.

Configuration (environment variable NAMES; values are not secrets):
  SINDHU_PUBLIC_SIGNAL_OWNER  'cloud' (default) | 'main' | 'any' | 'disabled'
      cloud -> only a process started with SINDHU_CLOUD_MODE=1 may publish
      main  -> only a process WITHOUT SINDHU_CLOUD_MODE may publish
      disabled -> nobody publishes (used by the Cloud shared-paper mode, which also
               requires SINDHU_SHARED_PAPER_ENABLED=1 and SINDHU_TELEGRAM_DRY_RUN=1)
      any   -> this process may publish (explicit opt-in; if both Main and Cloud
               run with 'any', every signal is sent twice)
  SINDHU_CLOUD_MODE           1/true/yes/on marks the process role as 'cloud'

This is a process-role guard, not an exactly-once delivery guarantee for
multiple replicas of the same role. Whenever a public signal is withheld the
reason is returned by public_delivery_decision() and logged by the caller.
"""
import os

_TRUE = ('1', 'true', 'yes', 'on')
_OWNERS = ('main', 'cloud', 'any', 'disabled')


def process_role(environ=None):
    env = os.environ if environ is None else environ
    return 'cloud' if str(env.get('SINDHU_CLOUD_MODE', '')).strip().lower() in _TRUE else 'main'


def public_delivery_decision(settings, channel_id, *, environ=None):
    """Return (allowed, reason). `reason` is '' when allowed and a plain-language
    explanation (naming the env vars involved) when the signal is withheld."""
    env = os.environ if environ is None else environ
    private = settings.get('personal_chat_id')
    if private and str(channel_id) == str(private) and str(channel_id) != str(settings.get('channel_id')):
        return True, ''
    owner = env.get('SINDHU_PUBLIC_SIGNAL_OWNER', 'cloud').strip().lower()
    role = process_role(env)
    if owner not in _OWNERS:
        return False, (f"SINDHU_PUBLIC_SIGNAL_OWNER={owner!r} is not one of {'/'.join(_OWNERS)}; "
                       f"public signal withheld (fail closed)")
    if owner == 'disabled':
        return False, "SINDHU_PUBLIC_SIGNAL_OWNER='disabled': public delivery is switched off for every process"
    if owner == 'any' or owner == role:
        return True, ''
    return False, (f"this process has role '{role}' but the configured public signal publisher is '{owner}' "
                   f"(SINDHU_PUBLIC_SIGNAL_OWNER, SINDHU_CLOUD_MODE); public signal withheld")


def public_delivery_allowed(settings, channel_id, *, environ=None):
    return public_delivery_decision(settings, channel_id, environ=environ)[0]


def delivery_blockers(settings, environ=None):
    """Every condition that would currently stop a PUBLIC signal from being sent by this process.
    Empty list = nothing blocks it (the per-signal gates - confluence, Wilson 25, freshness 15 min,
    0.5% drift, group filter - still apply to each individual signal)."""
    env = os.environ if environ is None else environ
    out = []
    if str(env.get('SINDHU_TELEGRAM_DRY_RUN', '')).strip() == '1':
        out.append('SINDHU_TELEGRAM_DRY_RUN=1 (network delivery disabled)')
    if str(env.get('SINDHU_SAFE_START', '')).strip() == '1':
        out.append('SINDHU_SAFE_START=1 (scanning and delivery disabled)')
    allowed, why = public_delivery_decision(settings, settings.get('channel_id'), environ=env)
    if not allowed:
        out.append(why)
    if not settings.get('bot_token'):
        out.append('Telegram bot token not configured (telegram settings / TELEGRAM_BOT_TOKEN)')
    if not settings.get('channel_id'):
        out.append('Telegram channel id not configured (telegram settings / TELEGRAM_CHANNEL_ID)')
    if not settings.get('master_send_enabled', True):
        out.append('master_send_enabled is OFF in Telegram settings')
    if not settings.get('auto_send_enabled', False):
        out.append('auto_send_enabled is OFF in Telegram settings')
    return out


def delivery_report(settings, environ=None):
    """Log lines for the startup banner: either READY or the exact list of blockers."""
    blockers = delivery_blockers(settings, environ)
    if not blockers:
        return ['[telegram] Public signal delivery: READY (per-signal gates still apply)']
    return ['[telegram] WARNING public signal delivery is BLOCKED by:'] + ['[telegram]   - ' + b for b in blockers]
