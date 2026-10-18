"""Runtime identity for diagnosing RTC failures in packaged applications."""
import platform
import ssl
from importlib.metadata import PackageNotFoundError, version

from OpenSSL import SSL


def runtime_details():
    compiler = globals().get("__compiled__")
    compiler_version = (
        ".".join(str(getattr(compiler, part)) for part in
                 ("major", "minor", "micro"))
        if compiler is not None else None)
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
        "nuitka": compiler_version,
        "versions": versions,
        "tls_openssl": ssl.OPENSSL_VERSION,
        "dtls_openssl": SSL.SSLeay_version(SSL.SSLEAY_VERSION).decode("ascii"),
    }
