from PySide6.QtWidgets import (
    QPushButton, QDialog,
    QVBoxLayout, QLabel, QHBoxLayout
)


class UpStreamConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("详细信息")
        self.setModal(True)

        # 文本内容
        info_label = QLabel(
            "版本：v1.2.3\n"
            "状态：运行正常\n"
            "说明：这是一个自定义弹窗（custom dialog），\n"
            "你可以在这里放更多多行信息、甚至放表格或输入框。"
        )

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)

        # 底部按钮一行横向布局
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        # 整个弹窗的竖向布局
        layout = QVBoxLayout()
        layout.addWidget(info_label)
        layout.addLayout(btn_row)
        self.setLayout(layout)
