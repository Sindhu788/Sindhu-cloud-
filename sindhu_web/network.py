"""Local network access helpers -- LAN IP detection and a QR code so a
phone on the same WiFi can connect without typing the address in by hand."""

import io
import socket

import qrcode
import qrcode.image.svg

DEFAULT_PORT = 8420


def get_local_ip():
    """The LAN IP other devices on the same WiFi would use to reach this
    machine. Uses a UDP "connect" (no packets actually sent) purely to ask
    the OS which local interface would be used to reach the internet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def make_qr_svg(data):
    """Returns an inline <svg>...</svg> string encoding `data` (the
    dashboard URL) -- no PNG/PIL dependency needed."""
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")
