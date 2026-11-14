# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Translations for the settings application.

Every string a person reads is wrapped in :func:`_` at the point of use, and this
module owns the lookup. Three decisions are worth stating, because each one is a
way this could have gone wrong:

* **No compiled catalogue is not an error.** ``gettext.translation`` with
  ``fallback=True`` returns a null translation whose ``gettext`` is the identity,
  so a checkout with ``.po`` files and no ``.mo`` files shows English rather than
  crashing. Compiling them is ``tools/compile_po.py``, and the packaging step that
  runs it is Part 6.
* **The starter language is Urdu, which is written right to left.** So the layout
  rule is not a nicety here: ``style/glass.css`` uses symmetric padding and margin
  and no ``-left``/``-right`` property at all, and every container the pages build
  is a box whose direction GTK derives from the locale. A layout that only worked
  left to right would be broken in the one language this project ships.
* **Direction is answered from the locale, not from a widget.** :func:`is_rtl`
  reads the language tag, so the pages, the CSS and a test can all agree on the
  same answer without a display.
"""
from __future__ import annotations

import gettext as _gettext
import locale
import os
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

from . import DOMAIN as _DOMAIN
from .paths import APP_DIR

#: Languages written right to left that this project's layout has to survive.
#: Urdu is the one it ships a starter catalogue for; the rest are here so the
#: answer does not depend on which RTL language somebody happens to run.
RTL_LANGUAGES = frozenset({
    "ar", "arc", "ckb", "dv", "fa", "he", "ks", "lrc", "ms", "ps", "sd", "ug",
    "ur", "yi",
})

#: What a missing or broken catalogue falls back to.
FALLBACK_LANGUAGE = "en"

_TRANSLATION: _gettext.NullTranslations = _gettext.NullTranslations()
_INSTALLED = False


class I18nError(RuntimeError):
    """A catalogue could not be read at all, as opposed to merely being absent."""


def language_tags(env: Optional[Mapping[str, str]] = None) -> List[str]:
    """The languages to try, most preferred first.

    ``LANGUAGE`` is colon separated and is what gettext itself consults; the
    ``LC_*`` and ``LANG`` variables are consulted in the documented order. Both
    paths are honoured so a test can pin one variable without fighting the other.
    """
    env = os.environ if env is None else env
    tags: List[str] = []
    for name in ("LANGUAGE",):
        value = env.get(name)
        if value:
            tags.extend(part for part in value.split(":") if part)
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = env.get(name)
        if value and value not in ("C", "POSIX"):
            tags.append(value)
    return tags


def base_language(tag: str) -> str:
    """``ur_PK.UTF-8`` -> ``ur``: the part that decides direction and catalogue."""
    return tag.split(".")[0].split("@")[0].split("_")[0].strip().lower()


def is_rtl(tag: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> bool:
    """True when the effective language is written right to left."""
    if tag is None:
        tags = language_tags(env)
        tag = tags[0] if tags else FALLBACK_LANGUAGE
    return base_language(tag) in RTL_LANGUAGES


def localedirs(env: Optional[Mapping[str, str]] = None) -> List[Path]:
    """Where compiled catalogues are looked for, in order.

    ``IARCH_LOCALEDIR`` first so a test or a packager can point at a tree without
    touching the checkout, then the application's own ``po/``, then the system
    location a package would install into.
    """
    env = os.environ if env is None else env
    found: List[Path] = []
    override = env.get("IARCH_LOCALEDIR")
    if override:
        found.append(Path(override))
    found.append(APP_DIR / "po")
    found.append(Path("/usr/share/locale"))
    return found


def install(localedir: Optional[Path] = None,
            languages: Optional[Sequence[str]] = None,
            env: Optional[Mapping[str, str]] = None) -> _gettext.NullTranslations:
    """Bind :func:`_` to a catalogue, or to English when there is none.

    Returns the translation object so a test can assert which one was loaded. A
    catalogue that exists but cannot be read is an :class:`I18nError`: that is a
    packaging fault, and falling back to English silently would hide a translation
    somebody wrote.
    """
    global _TRANSLATION, _INSTALLED
    wanted = list(languages) if languages else language_tags(env)
    directories = [Path(localedir)] if localedir else localedirs(env)
    translation: _gettext.NullTranslations = _gettext.NullTranslations()
    for directory in directories:
        if not directory.is_dir():
            continue
        try:
            # fallback=False on purpose: a missing catalogue raises FileNotFoundError
            # and the next directory is tried, while a catalogue that exists and
            # cannot be parsed raises and becomes an I18nError. Loading a null
            # translation here would make the two cases indistinguishable.
            candidate = _gettext.translation(
                _DOMAIN, localedir=str(directory), languages=wanted or None, fallback=False)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise I18nError(f"Catalogue in {directory} could not be read: {exc}") from exc
        translation = candidate
        break
    _TRANSLATION = translation
    _INSTALLED = True
    return translation


def _(message: str) -> str:
    """Translate one message; the identity function when no catalogue is loaded."""
    return _TRANSLATION.gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    """Translate a message that has a plural form."""
    return _TRANSLATION.ngettext(singular, plural, count)


def current() -> str:
    """The language in effect, for the About page's debug information."""
    if _INSTALLED and type(_TRANSLATION) is not _gettext.NullTranslations:
        info = getattr(_TRANSLATION, "info", lambda: {})()
        language = info().get("Language")
        if language:
            return str(language)
    tags = language_tags()
    return base_language(tags[0]) if tags else FALLBACK_LANGUAGE


def system_locale() -> str:
    """The locale Python resolved, which is what GTK uses for text direction."""
    try:
        return locale.getlocale()[0] or FALLBACK_LANGUAGE
    except (ValueError, TypeError):
        return FALLBACK_LANGUAGE
