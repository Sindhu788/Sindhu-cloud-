"""One public signal publisher across Main and Cloud.

Cloud owns public delivery by default; Main remains the research interface.
An explicit owner override must agree on both hosts. Private notifications are
outside this guard. This is a process-role guard, not an exactly-once delivery
guarantee for multiple replicas of the same role.
"""
import os


def public_delivery_allowed(settings, channel_id, *, environ=None):
    env=os.environ if environ is None else environ
    private=settings.get('personal_chat_id')
    if private and str(channel_id)==str(private) and str(channel_id)!=str(settings.get('channel_id')):
        return True
    owner=env.get('SINDHU_PUBLIC_SIGNAL_OWNER','cloud').strip().lower()
    cloud=str(env.get('SINDHU_CLOUD_MODE','')).strip().lower() in ('1','true','yes','on')
    role='cloud' if cloud else 'main'
    return owner in ('main','cloud') and role==owner
