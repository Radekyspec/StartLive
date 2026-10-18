"""Runtime identity shared by RTC logs and the packaged application self-test."""
import platform
import ssl
from importlib.metadata import PackageNotFoundError, version

from OpenSSL import SSL


def runtime_details():
    versions = {}
    for name in ("aiortc", "aioice", "pyOpenSSL", "cryptography", "pyee",
                 "certifi"):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "metadata unavailable"
    return {
        "python": platform.python_version(),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "compiled": "__compiled__" in globals(),
        "versions": versions,
        "tls_openssl": ssl.OPENSSL_VERSION,
        "dtls_openssl": SSL.SSLeay_version(SSL.SSLEAY_VERSION).decode("ascii"),
    }
