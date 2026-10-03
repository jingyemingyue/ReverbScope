"""Settings dialog: language, profile, backend, output folder, copy-recording,
theme and the developer tools switch."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from roomscope.i18n import _, available_locales
from roomscope.interpretation import available_profiles
from roomscope.interpretation.profiles import profile_title
from roomscope.settings import load_settings, save_settings
from roomscope.ui.widgets import label, tidy_form

#: Display names of the catalogs, each in its own language.
LANGUAGE_NAMES = {
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "ja": "日本語",
    "ko": "한국어",
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
}
#: Shown in both languages: the new language is not active until a restart.
RESTART_FOR_LANGUAGE = (
    "语言设置将在重新启动 RoomScope 后完全生效。\n"
    "The language change takes full effect after RoomScope restarts."
)


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Settings"))
        self.setMinimumWidth(520)
        self._settings = load_settings()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        form = tidy_form(QFormLayout())
        self.language = QComboBox()
        # Language names are written in their own language, so a user can find
        # theirs whatever the current interface language is.
        self.language.addItem(_("Follow the system"), "")
        for tag in available_locales():
            self.language.addItem(LANGUAGE_NAMES.get(tag, tag), tag)
        index = self.language.findData(self._settings.language)
        self.language.setCurrentIndex(max(index, 0))
        self.profile = QComboBox()
        for name in available_profiles():
            self.profile.addItem(profile_title(name), name)
        profile_index = self.profile.findData(self._settings.default_profile or "generic")
        self.profile.setCurrentIndex(max(profile_index, 0))
        self.backend = QComboBox()
        self.backend.addItem(_("Default (PortAudio)"), "")
        self.backend.addItem("portaudio", "portaudio")
        self.backend.addItem("fake", "fake")
        backend_index = self.backend.findData(self._settings.audio_backend)
        self.backend.setCurrentIndex(max(backend_index, 0))
        folder_row = QHBoxLayout()
        self.output_dir = QLineEdit(self._settings.output_dir)
        browse = QPushButton(_("Browse..."))
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self.output_dir)
        folder_row.addWidget(browse)
        self.copy_recording = QCheckBox(_("Copy the raw recording into every session"))
        self.copy_recording.setChecked(self._settings.copy_recording)
        self.theme = QComboBox()
        self.theme.addItem(_("Follow the system"), "")
        self.theme.addItem(_("Light"), "light")
        self.theme.addItem(_("Dark"), "dark")
        self.theme.setCurrentIndex(max(self.theme.findData(self._settings.theme), 0))
        self.developer_tools = QCheckBox(
            _("Show developer tools (Developer menu, advanced audio options; after a restart)")
        )
        self.developer_tools.setChecked(self._settings.developer_tools)
        form.addRow(_("Language"), self.language)
        self.language_hint = label(RESTART_FOR_LANGUAGE, "hint", wrap=True)
        form.addRow(self.language_hint)
        form.addRow(_("Default profile"), self.profile)
        form.addRow(_("Audio backend"), self.backend)
        form.addRow(_("Default output folder"), folder_row)
        form.addRow(self.copy_recording)
        form.addRow(_("Theme"), self.theme)
        form.addRow(self.developer_tools)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok is not None:
            ok.setText(_("OK"))
        if cancel is not None:
            cancel.setText(_("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Default output folder"))
        if directory:
            self.output_dir.setText(directory)

    def accept(self) -> None:
        # Start from the stored settings so fields this dialog does not show
        # survive a save.
        settings = replace(
            self._settings,
            language=str(self.language.currentData() or ""),
            default_profile=str(self.profile.currentData() or "generic"),
            audio_backend=str(self.backend.currentData() or ""),
            output_dir=self.output_dir.text().strip(),
            copy_recording=self.copy_recording.isChecked(),
            theme=str(self.theme.currentData() or ""),
            developer_tools=self.developer_tools.isChecked(),
        )
        save_settings(settings)
        from PySide6.QtWidgets import QApplication

        from roomscope.ui.theme import apply_application_chrome

        app = QApplication.instance()
        if app is not None:
            apply_application_chrome(app)
        # The new language is used from the next start: every window keeps the
        # language it was built in, and switching the translator now would
        # leave the open ones half in the old language.
        super().accept()

    def selected_output_dir(self) -> Path | None:
        text = self.output_dir.text().strip()
        return Path(text) if text else None
