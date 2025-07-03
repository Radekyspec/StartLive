import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import QThread, Signal, QObject

from models.log import get_logger


class SignalEmitter(QObject):
    startLive = Signal()
    stopLive = Signal()


class HttpServerWorker(QThread):
    signals = SignalEmitter()

    def __init__(self, host="localhost", port=8080):
        super().__init__()
        self.host = host
        self.port = port
        self.logger = get_logger(self.__class__.__name__)

    def run(self):
        handler = self.make_handler()
        self.httpd = HTTPServer((self.host, self.port), handler)
        self.logger.info(f"HTTP Server running on http://{self.host}:{self.port}")
        self.httpd.serve_forever()

    def make_handler(self):
        signals = self.signals
        logger = self.logger

        class EmitSignalHandler(BaseHTTPRequestHandler):
            triggers: dict[str, str] = {
                "/api/startLive": "startLive",
                "/api/stopLive": "stopLive",
            }

            def do_POST(self):
                signal_name = self.triggers.get(self.path)
                if signal_name and hasattr(signals, signal_name):
                    logger.info(f"Server received signal {signal_name}")
                    getattr(signals, signal_name).emit()
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'OK')
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not Found.")

            def log_message(self, format, *args):
                logger.info(format % args)

        return EmitSignalHandler

    def stop(self):
        if hasattr(self, 'httpd'):
            self.httpd.shutdown()
            self.httpd.server_close()
