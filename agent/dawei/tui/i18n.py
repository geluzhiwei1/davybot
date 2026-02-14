# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TUI Internationalization (i18n) Module

Provides internationalization support for the Dawei TUI.
Supports multiple languages with dynamic language switching.
Can read both .mo and .po files for translations.
"""

import gettext
import locale
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# Supported languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
}

# Default language
DEFAULT_LANGUAGE = "en"

# Translation caches
_translations: dict[str, gettext.GNUTranslations] = {}
_po_translations: dict[str, dict[str, str]] = {}
_current_language: str = DEFAULT_LANGUAGE


def get_locales_dir() -> Path:
    """Get the directory containing locale files"""
    return Path(__file__).parent / "locales"


def parse_po_file(po_file: Path) -> dict[str, str]:
    """Parse a .po file and return a dictionary of translations

    Args:
        po_file: Path to .po file

    Returns:
        Dict[str, str]: Mapping of msgid to msgstr
    """
    translations = {}

    try:
        with Path(po_file).open(encoding="utf-8") as f:
            current_msgid = None
            current_msgstr = None
            in_msgstr = False

            for line in f:
                line = line.rstrip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Parse msgid
                if line.startswith("msgid"):
                    # Save previous translation if exists
                    if current_msgid is not None:
                        translations[current_msgid] = current_msgstr or current_msgid

                    # Extract new msgid
                    msgid_match = re.match(r'msgid\s+"(.+)"', line)
                    if msgid_match:
                        current_msgid = msgid_match.group(1)
                        current_msgstr = ""
                        in_msgstr = False

                # Parse msgstr
                elif line.startswith("msgstr "):
                    msgstr_match = re.match(r'msgstr\s+"(.*)"', line)
                    if msgstr_match:
                        current_msgstr = msgstr_match.group(1)
                        in_msgstr = True

                # Continuation of msgstr
                elif in_msgstr and line.startswith('"'):
                    str_match = re.match(r'"(.+)"', line)
                    if str_match:
                        current_msgstr += str_match.group(1)

            # Save last translation
            if current_msgid is not None:
                translations[current_msgid] = current_msgstr or current_msgid

    except Exception:
        logger.exception("Failed to parse PO file {po_file}: ")

    return translations


def load_po_translation(language: str) -> dict[str, str]:
    """Load translations from .po file

    Args:
        language: Language code

    Returns:
        Dict[str, str]: Translation dictionary
    """
    if language in _po_translations:
        return _po_translations[language]

    po_file = get_locales_dir() / language / "LC_MESSAGES" / "dawei_tui.po"

    if po_file.exists():
        translations = parse_po_file(po_file)
        _po_translations[language] = translations
        logger.info(f"Loaded {len(translations)} translations from {po_file.name}")
        return translations

    return {}


def install_translation(language: str = DEFAULT_LANGUAGE) -> gettext.GNUTranslations:
    """Install translation for specified language

    Tries to load .mo file first, then falls back to .po file.

    Args:
        language: Language code (e.g., 'en', 'zh_CN')

    Returns:
        gettext.GNUTranslations: Translation object
    """
    global _current_language

    # Use default language if not specified
    if not language:
        language = DEFAULT_LANGUAGE

    # Normalize language code
    language = language.replace("-", "_").replace("@", "_")

    # Check if language is supported
    if language not in SUPPORTED_LANGUAGES:
        logger.warning(f"Language '{language}' not supported, falling back to '{DEFAULT_LANGUAGE}'")
        language = DEFAULT_LANGUAGE

    # Return cached translation if available
    if language in _translations:
        _current_language = language
        return _translations[language]

    # Try to load translation from .mo file
    locales_dir = get_locales_dir()
    mo_file = locales_dir / language / "LC_MESSAGES" / "dawei_tui.mo"

    try:
        if mo_file.exists() and mo_file.stat().st_size > 28:
            with Path(mo_file).open("rb") as f:
                translation = gettext.GNUTranslations(f)
                _translations[language] = translation
                _current_language = language
                translation.install()
                logger.info(f"Loaded .mo translation for {language}")
                return translation
        else:
            logger.debug(f".mo file not found or empty: {mo_file}")
    except Exception as e:
        logger.debug(f"Failed to load .mo file: {e}")

    # Fallback: Load from .po file
    po_translations = load_po_translation(language)
    if po_translations:
        # Create a simple translation wrapper
        class POTranslation:
            def __init__(self, translations):
                self.translations = translations

            def gettext(self, message):
                return self.translations.get(message, message)

            def ngettext(self, singular, plural, count):
                if count == 1:
                    return self.translations.get(singular, singular)
                return self.translations.get(plural, plural)

            def install(self):
                import builtins

                builtins._ = self.gettext
                builtins.ngettext = self.ngettext

        translation = POTranslation(po_translations)
        _translations[language] = translation
        _current_language = language
        translation.install()
        logger.info(f"Loaded .po translation for {language}")
        return translation

    # Fallback to null translation if neither .mo nor .po exists
    logger.debug(f"No translation file found for {language}, using null translation")
    translation = gettext.NullTranslations()
    _translations[language] = translation
    _current_language = language
    translation.install()

    return translation


def get_translation(language: str = DEFAULT_LANGUAGE) -> gettext.GNUTranslations:
    """Get translation object for specified language without installing it

    Args:
        language: Language code (e.g., 'en', 'zh_CN')

    Returns:
        gettext.GNUTranslations: Translation object
    """
    # Use current language if not specified
    if not language:
        language = _current_language

    # Return cached translation if available
    if language in _translations:
        return _translations[language]

    # Load and cache
    return install_translation(language)


def get_current_language() -> str:
    """Get currently active language code

    Returns:
        str: Current language code
    """
    return _current_language


def set_language(language: str) -> None:
    """Set current language and install translation

    Args:
        language: Language code (e.g., 'en', 'zh_CN')
    """
    install_translation(language)
    logger.info(f"Language set to: {SUPPORTED_LANGUAGES.get(language, language)}")


def get_supported_languages() -> dict[str, str]:
    """Get dictionary of supported languages

    Returns:
        Dict[str, str]: Mapping of language codes to language names
    """
    return SUPPORTED_LANGUAGES.copy()


def get_system_language() -> str:
    """Detect system default language

    Returns:
        str: Detected language code, or DEFAULT_LANGUAGE if detection fails
    """
    try:
        # Get system locale
        system_locale = locale.getdefaultlocale()[0]
        if system_locale:
            # Normalize and check if supported
            lang_code = system_locale.replace("-", "_")
            if lang_code in SUPPORTED_LANGUAGES:
                return lang_code
            # Try base language (e.g., 'zh' from 'zh_CN')
            base_lang = lang_code.split("_")[0]
            for supported_code in SUPPORTED_LANGUAGES:
                if supported_code.startswith(base_lang):
                    return supported_code
    except Exception as e:
        logger.warning(f"Failed to detect system language: {e}")

    return DEFAULT_LANGUAGE


# Convenience function: translate using current language
def _(message: str) -> str:
    """Translate message using current language

    This is a convenience function that should be imported and used in TUI code:
        from dawei.tui.i18n import _
        text = _("Hello, World!")

    Args:
        message: Message to translate

    Returns:
        str: Translated message
    """
    translation = _translations.get(_current_language)
    if translation:
        if hasattr(translation, "translations"):
            # PO translation wrapper
            return translation.translations.get(message, message)
        # GNUTranslations
        return translation.gettext(message)
    return message


# Plural translation function
def _n(singular: str, plural: str, count: int) -> str:
    """Translate message with plural form

    Args:
        singular: Singular form of message
        plural: Plural form of message
        count: Count for determining plural form

    Returns:
        str: Translated message in appropriate form
    """
    translation = _translations.get(_current_language)
    if translation:
        if hasattr(translation, "translations"):
            # PO translation wrapper
            if count == 1:
                return translation.translations.get(singular, singular)
            return translation.translations.get(plural, plural)
        # GNUTranslations
        return translation.ngettext(singular, plural, count)
    return singular if count == 1 else plural


# Initialize with system language or default
system_lang = get_system_language()
install_translation(system_lang)
