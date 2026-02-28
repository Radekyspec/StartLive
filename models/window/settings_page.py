from functools import partial

from PySide6.QtCore import Slot
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QLineEdit, QButtonGroup, QPushButton, QFontDialog, QSlider
)

import app_state
from app_state import bg_settings_default
from constant import ProxyMode, PreferProto
from models.widgets import SettingsWidget
from models.workers.live_delay import StreamTimeShiftUpdateWorker


class SettingsPage(SettingsWidget):
    proxy_group: QButtonGroup
    delay_edit: QLineEdit
    delay_save_btn: QPushButton
    prefer_proto_group: QButtonGroup
    cover_edit: QLineEdit
    cover_btn: QPushButton
    bg_mode_group: QButtonGroup
    bg_opacity_slider: QSlider
    bg_blur_slider: QSlider
    tray_icon_edit: QLineEdit

    def __init__(self, parent: "MainWindow" = None):
        super().__init__(parent)

        self._parent_window = parent
        proxy_default_index = app_state.app_settings.get("proxy_mode",
                                                         ProxyMode.NONE)
        self.proxy_group = self.add_multi_choice_item(
            "代理设置",
            ["不使用代理", "使用系统代理", "使用自定义代理"],
            default=proxy_default_index
        )

        self.proxy_addr_edit, self.proxy_addr_btn = self.add_text_item(
            "自定义代理服务器地址（URL）",
            "保存并应用",
            placeholder=app_state.app_settings.get("custom_proxy_url",
                                                   "socks5://127.0.0.1:7898")
        )
        self.proxy_addr_edit.setToolTip(
            "代理协议支持 http://，https://，socks5://，socks5h://")
        self.proxy_addr_edit.setText(
            app_state.app_settings.get("custom_proxy_url", ""))
        self.proxy_addr_btn.clicked.connect(self._save_custom_proxy)

        self.proxy_group.idClicked.connect(self._on_proxy_mode_changed)

        self._on_proxy_mode_changed(self.proxy_group.checkedId())

        self.delay_edit, self.delay_save_btn = self.add_text_item(
            "推流延迟",
            "保存并应用",
            placeholder="请输入10 - 300之间的整数"
        )
        self.delay_edit.setValidator(QIntValidator(10, 300, self.delay_edit))
        self.delay_edit.setToolTip(
            "此设置项为B站在标准推流基础上添加的延迟\n\n"
            "推流协议本身自带一些不可避免的短暂的延迟，设置成0不能实现无延迟直播\n\n"
            "设置后，仅在PC开播生效，直播画面和音频将同步延迟；连麦、连线、PK等正常功能可能受到影响")
        self.delay_edit.textChanged.connect(
            lambda: self.delay_save_btn.setEnabled(True))
        self.delay_save_btn.clicked.connect(self._on_delay_save)

        proto_default_index = app_state.app_settings.get("prefer_proto",
                                                         PreferProto.RTMP)
        self.prefer_proto_group = self.add_multi_choice_item(
            "推流协议选择",
            ["优先RTMP", "优先SRT，无SRT流时回退至RTMP",
             "优先SRT，无SRT时停止直播"],
            default=proto_default_index
        )
        self.prefer_proto_group.idClicked.connect(self._on_prefer_proto_changed)

        self.cover_edit, self.cover_btn = self.add_file_picker_item(
            "自定义背景图片", dialog_title="选择背景图片",
            name_filter="图片文件 (*.jfif;*.pjpeg;*.jpeg;*.pjp;*.jpg;*.png);;所有文件 (*)",
            placeholder=app_state.app_settings.get("background_image", "")
        )
        self.cover_edit.setText(
            app_state.app_settings.custom_bg
        )
        self.cover_edit.textChanged.connect(self._on_cover_changed)
        self._on_cover_changed()

        bg_mode_default = app_state.app_settings.custom_bg_mode
        self.bg_mode_group = self.add_multi_choice_item(
            "背景缩放模式",
            ["无拉伸", "拉伸填充", "等比填充", "等比适应"],
            default=bg_mode_default
        )
        self.bg_mode_group.idClicked.connect(self._on_bg_mode_changed)

        bg_opacity_default = app_state.app_settings.custom_bg_opacity
        self.bg_opacity_slider = self.add_slider_item(
            "背景不透明度", min_value=10, max_value=100,
            default=bg_opacity_default, suffix="%"
        )
        self.bg_opacity_slider.valueChanged.connect(self._on_bg_opacity_changed)

        bg_blur_default = app_state.app_settings.custom_bg_blur_radius
        self.bg_blur_slider = self.add_slider_item(
            "背景模糊半径", min_value=0, max_value=40,
            default=bg_blur_default, suffix=""
        )
        self.bg_blur_slider.valueChanged.connect(self._on_bg_blur_changed)

        self.tray_icon_edit, self.tray_icon_btn = self.add_file_picker_item(
            "自定义托盘图标", dialog_title="选择托盘图标图片",
            name_filter="图片文件 (*.jfif;*.pjpeg;*.jpeg;*.pjp;*.jpg;*.png);;所有文件 (*)",
            placeholder=app_state.app_settings["custom_tray_icon"]
        )
        self.tray_icon_edit.textChanged.connect(
            self._parent_window.switch_tray_icon)

        custom_tray_hint = app_state.app_settings["custom_tray_hint"]
        self.tray_hint_edit, self.tray_hint_btn = self.add_text_item(
            "自定义托盘图标提示",
            "保存更改",
            "你所热爱的 就是你的生活" if custom_tray_hint == "" else custom_tray_hint)
        self.tray_hint_btn.clicked.connect(self._switch_tray_hint)

        self.font_edit, self.font_btn = self.add_font_picker_item(
            "自定义显示字体（重启生效）", options=(
                    QFontDialog.FontDialogOption.DontUseNativeDialog | QFontDialog.FontDialogOption.ScalableFonts))
        self.main_vbox.addStretch(1)

    @Slot()
    def _on_delay_save(self):
        self.delay_save_btn.setEnabled(False)
        delay_value = self.delay_edit.text()
        if not delay_value:
            delay_value = 0
        update_delay = StreamTimeShiftUpdateWorker(delay_value)
        self._parent_window.add_thread(
            update_delay,
            on_finished=update_delay.on_finished,
            on_exception=partial(update_delay.on_exception, self.delay_save_btn)
        )

    @Slot()
    def _switch_tray_hint(self):
        self._parent_window.switch_tray_hint(self.tray_hint_edit.text())

    @Slot(int)
    def _on_prefer_proto_changed(self, _id: int):
        match _id:
            case 0:
                app_state.app_settings["prefer_proto"] = PreferProto.RTMP
            case 1:
                app_state.app_settings[
                    "prefer_proto"] = PreferProto.SRT_FALLBACK_RTMP
            case 2:
                app_state.app_settings["prefer_proto"] = PreferProto.SRT_ONLY
            case _:
                raise ValueError("Unexpected protocol choice")

    @Slot(int)
    def _on_proxy_mode_changed(self, _id: int):
        is_custom = (_id == 2)
        self.proxy_addr_edit.setEnabled(is_custom)
        self.proxy_addr_btn.setEnabled(is_custom)
        match _id:
            case 0:
                app_state.app_settings["proxy_mode"] = ProxyMode.NONE
            case 1:
                app_state.app_settings["proxy_mode"] = ProxyMode.SYSTEM
            case 2:
                app_state.app_settings["proxy_mode"] = ProxyMode.CUSTOM
            case _:
                raise ValueError("Unexpected proxy mode")

    @Slot()
    def _save_custom_proxy(self):
        url = self.proxy_addr_edit.text().strip()
        app_state.app_settings["custom_proxy_url"] = url

        if self.proxy_group.checkedId() != 2:
            btn = self.proxy_group.button(2)
            if btn:
                btn.setChecked(True)

    @Slot()
    def _on_cover_changed(self):
        path = self.cover_edit.text().strip()
        app_state.app_settings.custom_bg = path

        if self._parent_window is not None and hasattr(self._parent_window,
                                                       "set_background_image"):
            self._parent_window.set_background_image(path)
            self._on_bg_opacity_changed(
                app_state.app_settings.custom_bg_opacity)
            self._on_bg_blur_changed(
                app_state.app_settings.custom_bg_blur_radius)

    @Slot(int)
    def _on_bg_mode_changed(self, mode_index: int):
        app_state.app_settings.custom_bg_mode = mode_index
        if self._parent_window is not None and hasattr(self._parent_window,
                                                       "set_background_mode"):
            self._parent_window.set_background_mode(mode_index)

    @Slot(int)
    def _on_bg_opacity_changed(self, value: int):
        app_state.app_settings.custom_bg_opacity = value
        if self._parent_window is not None and hasattr(self._parent_window,
                                                       "set_background_opacity"):
            self._parent_window.set_background_opacity(value / 100.0)

    @Slot(int)
    def _on_bg_blur_changed(self, value: int):
        app_state.app_settings.custom_bg_blur_radius = value
        if self._parent_window is not None and hasattr(self._parent_window,
                                                       "set_background_blur_radius"):
            self._parent_window.set_background_blur_radius(value)

    def reset_bg(self):
        bg_settings_default()
        self.cover_edit.setText(app_state.app_settings.custom_bg)

        bg_mode_default = app_state.app_settings.custom_bg_mode
        self.bg_mode_group.button(bg_mode_default).setChecked(True)

        self.bg_opacity_slider.setValue(
            app_state.app_settings.custom_bg_opacity
        )
        self.bg_blur_slider.setValue(
            app_state.app_settings.custom_bg_blur_radius
        )
        self._on_cover_changed()

    def reset_default(self):
        pm = app_state.app_settings["proxy_mode"]
        self._on_proxy_mode_changed(pm)
        self.proxy_group.button(pm).setChecked(
            True)
        self.tray_icon_edit.setText(app_state.app_settings["custom_tray_icon"])
        self.tray_hint_edit.setText(app_state.app_settings["custom_tray_hint"])
        self.tray_hint_edit.update_placeholder("你所热爱的 就是你的生活")
        self.proxy_addr_edit.setText(app_state.app_settings["custom_proxy_url"])
        self.proxy_addr_edit.update_placeholder("socks5://127.0.0.1:7898")
        self.prefer_proto_group.button(
            app_state.app_settings["prefer_proto"]).setChecked(True)
        self.reset_bg()
