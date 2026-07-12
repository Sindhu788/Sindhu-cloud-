from fastapi import APIRouter

from sindhu_web import devices, network

router = APIRouter()


@router.get("/api/network")
def get_network():
    ip = network.get_local_ip()
    url = f"http://{ip}:{network.DEFAULT_PORT}"
    return {
        "local_ip": ip,
        "port": network.DEFAULT_PORT,
        "url": url,
        "qr_svg": network.make_qr_svg(url),
        "connected_devices": devices.list_devices(),
    }
