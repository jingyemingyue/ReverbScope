"""The suite stays in English when Python's process locale is Chinese.

``pin_language`` sets ``LANG=C.UTF-8`` and clears the other locale variables.
``_posix_step`` deliberately ignores a C locale, so the last step in
``i18n._system_choice`` is ``locale.getlocale()``. On a Chinese Mac that is
``zh_CN``, and the CLI then speaks Chinese. The fixture has to hide that.
"""

from __future__ import annotations

import pytest

from reverbscope import i18n


@pytest.fixture(scope="module", autouse=True)
def _process_locale_is_chinese():
    """What this machine's interpreter started with, on every machine.

    Installed before the function-scoped ``pin_language``. If that fixture
    does not replace ``getlocale``, resolution follows this value.
    """
    original = i18n.py_locale.getlocale
    i18n.py_locale.getlocale = lambda *_args, **_kwargs: ("zh_CN", "UTF-8")
    yield
    i18n.py_locale.getlocale = original


def test_a_chinese_process_locale_still_resolves_to_english() -> None:
    assert i18n.py_locale.getlocale() == (None, None)
    choice = i18n.language_choice()
    assert choice.lang == "en"
    assert i18n.activate() == "en"
    assert i18n._("ReverbScope analysis") == "ReverbScope analysis"
