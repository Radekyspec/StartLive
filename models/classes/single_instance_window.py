from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QMainWindow, QMessageBox

from constant import LOCAL_SERVER_NAME


class SingleInstanceWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._server = QLocalServer(self)
        # 清除可能残留的 socket 文件
        QLocalServer.removeServer(LOCAL_SERVER_NAME)

        if not self._server.listen(LOCAL_SERVER_NAME):
            QMessageBox.critical(self, "应用初始化", "启动本地服务失败！")
        else:
            self._server.newConnection.connect(self._handle_new_connection)

    def _handle_new_connection(self):
        socket = self._server.nextPendingConnection()
        socket.readyRead.connect(lambda: self._read_and_activate(socket))

    def _read_and_activate(self, socket):
        data = socket.readAll().data().decode()
        if data == "ACTIVATE":
            self._bring_to_front()
        socket.close()

    def _bring_to_front(self):
        """唤醒窗口"""
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    @staticmethod
    def is_another_instance_running():
        """尝试连接到现有实例"""
        socket = QLocalSocket()
        socket.connectToServer(LOCAL_SERVER_NAME)
        if socket.waitForConnected(50):
            socket.write(b"ACTIVATE")
            socket.flush()
            socket.waitForBytesWritten(50)
            socket.close()
            return True
        return False
