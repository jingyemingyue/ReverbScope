"""Settings for the guided assistant. The API key never enters the settings file."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.experimental.guided.config import (
    GuidedSettings,
    load_guided_settings,
    save_guided_settings,
)
from reverbscope.experimental.guided.privacy import StoreChoice, process_vault, reveal_key
from reverbscope.experimental.guided.setup import (
    assistant_labels,
    interface_language,
    preview_without_measurement,
    test_provider,
)


def _choice(box: QComboBox, pairs: tuple[tuple[str, str], ...], current: str) -> None:
    for text, value in pairs:
        box.addItem(text, value)
    index = box.findData(current)
    box.setCurrentIndex(max(index, 0))


class GuidedAssistantDialog(QDialog):
    """Built-in, local, or bring-your-own-key cloud. Cloud is never the default."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._language = interface_language()
        self.L = assistant_labels(self._language)
        self.vault = process_vault()
        self._settings = load_guided_settings()
        self.setWindowTitle(self.L["settings_title"])
        root = QVBoxLayout(self)
        form = QFormLayout()
        self._hint = QLabel(self.L["settings_hint"])
        self._hint.setWordWrap(True)
        self._cost = QLabel(self.L["cost"])
        self._cost.setWordWrap(True)
        self.engine = QComboBox()
        _choice(
            self.engine,
            (
                (self.L["engine_builtin"], "builtin"),
                (self.L["engine_local"], "local"),
                (self.L["engine_cloud"], "cloud"),
                (self.L["engine_auto"], "auto"),
            ),
            self._settings.explanation_engine,
        )
        self.provider = QComboBox()
        _choice(
            self.provider,
            (
                (self.L["provider_openai"], "openai"),
                (self.L["provider_anthropic"], "anthropic"),
                (self.L["provider_gemini"], "gemini"),
                (self.L["provider_openai_compatible"], "openai_compatible"),
            ),
            self._settings.provider_id or "openai",
        )
        self.model = QLineEdit(self._settings.model_id)
        self.model.setPlaceholderText(self.L["model_hint"])
        self.base_url = QLineEdit(self._settings.base_url)
        self.ack = QCheckBox(self.L["ack_endpoint"])
        self.ack.setChecked(self._settings.custom_endpoint_acknowledged)
        self._endpoint = QLabel(self.L["endpoint_warning"])
        self._endpoint.setWordWrap(True)
        self._key_state = QLabel(self.L["not_configured"])
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(self.L["key_hint"])
        key_actions = QHBoxLayout()
        replace_key = QPushButton(self.L["replace"])
        remove_key = QPushButton(self.L["remove"])
        test_key = QPushButton(self.L["test_connection"])
        replace_key.clicked.connect(self._replace_key)
        remove_key.clicked.connect(self._remove_key)
        test_key.clicked.connect(self._test_key)
        key_actions.addWidget(replace_key)
        key_actions.addWidget(remove_key)
        key_actions.addWidget(test_key)
        self.reveal_box = QCheckBox(self.L["reveal_confirm"])
        self.reveal_button = QPushButton(self.L["reveal"])
        self.reveal_button.clicked.connect(self._reveal_or_hide)
        self.secret_label = QLabel("")
        self.secret_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.cloud_enabled = QCheckBox(self.L["cloud_enabled"])
        self.cloud_enabled.setChecked(self._settings.cloud_explanation_enabled)
        self.consent = QComboBox()
        _choice(
            self.consent,
            (
                (self.L["consent_unset"], "unset"),
                (self.L["consent_once"], "once"),
                (self.L["consent_always"], "always"),
            ),
            self._settings.cloud_consent,
        )
        self.data_level = QComboBox()
        _choice(
            self.data_level,
            ((self.L["level_minimal"], "minimal"), (self.L["level_detailed"], "detailed")),
            self._settings.data_level,
        )
        self.length = QComboBox()
        _choice(
            self.length,
            (
                (self.L["length_concise"], "concise"),
                (self.L["length_balanced"], "balanced"),
                (self.L["length_detailed_choice"], "detailed"),
            ),
            self._settings.length,
        )
        self.expertise = QComboBox()
        _choice(
            self.expertise,
            (
                (self.L["expertise_beginner"], "beginner"),
                (self.L["expertise_intermediate"], "intermediate"),
                (self.L["expertise_expert"], "expert"),
            ),
            self._settings.expertise,
        )
        self.language = QComboBox()
        _choice(
            self.language,
            (
                (self.L["language_follow"], ""),
                (self.L["language_en"], "en"),
                (self.L["language_zh"], "zh-CN"),
            ),
            self._settings.language,
        )
        self.privacy = QCheckBox(self.L["privacy"])
        self.privacy.setChecked(self._settings.privacy_mode)
        self.offline = QCheckBox(self.L["offline"])
        self.offline.setChecked(self._settings.offline)
        self.lookup = QCheckBox(self.L["lookup"])
        self.lookup.setChecked(self._settings.allow_knowledge_lookup)
        self.share_usage = QCheckBox(self.L["share_usage"])
        self.share_usage.setChecked(self._settings.share_anonymous_usage)
        self.share_hardware = QCheckBox(self.L["share_hardware"])
        self.share_hardware.setChecked(self._settings.share_hardware_compatibility)
        self.share_crash = QCheckBox(self.L["share_crash"])
        self.share_crash.setChecked(self._settings.share_anonymous_crashes)
        self._local = QLabel(self.L["local_status"])
        self._local.setWordWrap(True)
        self._packs = QLabel(self.L["packs_status"])
        self._packs.setWordWrap(True)
        preview = QPushButton(self.L["preview"])
        preview.clicked.connect(self._preview)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        form.addRow(self._hint)
        form.addRow(self._cost)
        form.addRow(self.L["engine"], self.engine)
        form.addRow(self.L["provider"], self.provider)
        form.addRow(self.L["model"], self.model)
        form.addRow(self.L["base_url"], self.base_url)
        form.addRow(self.ack)
        form.addRow(self._endpoint)
        form.addRow(self.L["key"], self._key_state)
        form.addRow(self.key_edit)
        form.addRow(key_actions)
        form.addRow(self.reveal_box)
        form.addRow(self.reveal_button)
        form.addRow(self.secret_label)
        form.addRow(self.cloud_enabled)
        form.addRow(self.L["consent_label"], self.consent)
        form.addRow(self.L["data_level"], self.data_level)
        form.addRow(self.L["length"], self.length)
        form.addRow(self.L["expertise"], self.expertise)
        form.addRow(self.L["language_label"], self.language)
        form.addRow(self.privacy)
        form.addRow(self.offline)
        form.addRow(self.lookup)
        form.addRow(self.share_usage)
        form.addRow(self.share_hardware)
        form.addRow(self.share_crash)
        form.addRow(self._local)
        form.addRow(self._packs)
        form.addRow(preview)
        form.addRow(self.preview_text)
        form.addRow(self.status)
        root.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton(self.L["save"])
        cancel = QPushButton(self.L["cancel"])
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        root.addLayout(buttons)
        self._refresh_key_state()

    def draft(self) -> GuidedSettings:
        """Settings that are safe to write. The line edit is not included."""
        return replace(
            self._settings,
            explanation_engine=str(self.engine.currentData() or "builtin"),
            provider_id=str(self.provider.currentData() or ""),
            model_id=self.model.text().strip(),
            base_url=self.base_url.text().strip(),
            custom_endpoint_acknowledged=self.ack.isChecked(),
            cloud_explanation_enabled=self.cloud_enabled.isChecked(),
            cloud_consent=str(self.consent.currentData() or "unset"),
            data_level=str(self.data_level.currentData() or "minimal"),
            length=str(self.length.currentData() or "balanced"),
            expertise=str(self.expertise.currentData() or "beginner"),
            language=str(self.language.currentData() or ""),
            privacy_mode=self.privacy.isChecked(),
            offline=self.offline.isChecked(),
            allow_knowledge_lookup=self.lookup.isChecked(),
            share_anonymous_usage=self.share_usage.isChecked(),
            share_hardware_compatibility=self.share_hardware.isChecked(),
            share_anonymous_crashes=self.share_crash.isChecked(),
            allow_telemetry=self.share_usage.isChecked(),
            allow_crash_report=self.share_crash.isChecked(),
        )

    def _provider(self) -> str:
        return str(self.provider.currentData() or "")

    def _refresh_key_state(self) -> None:
        configured = self.vault.configured(self._provider())
        self._key_state.setText(self.L["configured"] if configured else self.L["not_configured"])

    def _replace_key(self) -> bool:
        key = self.key_edit.text().strip()
        if not key:
            self.status.setText(self.L["key_empty"])
            return False
        provider = self._provider()
        if self.vault.secure_available():
            result = self.vault.store(provider, key, StoreChoice.SECURE)
        else:
            choice = _ask_store_choice(self, self.L)
            if choice is None or choice is StoreChoice.CANCEL:
                self.status.setText(self.L["key_not_stored"])
                return False
            result = self.vault.store(provider, key, choice)
        if not result.stored:
            self.status.setText(self.L["key_not_stored"])
            return False
        self.key_edit.clear()
        self.secret_label.clear()
        self.reveal_box.setChecked(False)
        if result.where == "secure":
            self.status.setText(self.L["key_stored_secure"])
        else:
            self.status.setText(self.L["key_stored_session"])
        self._refresh_key_state()
        return True

    def _remove_key(self) -> None:
        self.vault.remove(self._provider())
        self.key_edit.clear()
        self.secret_label.clear()
        self.reveal_box.setChecked(False)
        self.status.setText(self.L["key_removed"])
        self._refresh_key_state()

    def _test_key(self) -> None:
        typed = self.key_edit.text().strip()
        key = typed or (self.vault.get(self._provider()) or "")
        result = test_provider(self.draft(), key)
        self.status.setText(self.L["test_ok"] if result.ok else self.L["test_failed"])

    def _reveal_or_hide(self) -> None:
        if self.secret_label.text():
            self.secret_label.clear()
            self.reveal_button.setText(self.L["reveal"])
            return
        if not self.reveal_box.isChecked():
            return
        typed = self.key_edit.text().strip()
        key = typed or (self.vault.get(self._provider()) or "")
        if not key:
            return
        self.secret_label.setText(reveal_key(key, confirmed=True))
        self.reveal_button.setText(self.L["hide"])

    def _preview(self) -> None:
        self.preview_text.setPlainText(preview_without_measurement(self.draft(), self._language))

    def _save(self) -> None:
        if self.key_edit.text().strip() and not self._replace_key():
            return
        save_guided_settings(self.draft())
        self.accept()


def _ask_store_choice(parent: QWidget, labels: dict[str, str]) -> StoreChoice | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(labels["store_title"])
    layout = QVBoxLayout(dialog)
    note = QLabel(labels["secure_unavailable"])
    note.setWordWrap(True)
    layout.addWidget(note)
    chosen: list[StoreChoice] = []

    def pick(choice: StoreChoice) -> None:
        chosen.append(choice)
        dialog.accept()

    secure = QPushButton(labels["secure_choice"])
    secure.setEnabled(False)
    session = QPushButton(labels["session_choice"])
    cancel = QPushButton(labels["cancel_choice"])
    session.clicked.connect(lambda: pick(StoreChoice.SESSION))
    cancel.clicked.connect(lambda: pick(StoreChoice.CANCEL))
    layout.addWidget(secure)
    layout.addWidget(session)
    layout.addWidget(cancel)
    dialog.exec()
    return chosen[0] if chosen else None
