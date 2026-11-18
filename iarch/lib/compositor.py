# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Asking the compositor to reload, and asking it whether the reload was happy.

Purpose
    A theme apply that writes a Hyprland include and never checks the result can
    leave a session that does not parse its own configuration. This module is the
    two questions that prevent that — reload, then read the parsing errors — and
    the comparison that decides whose errors they are.

Inputs
    Nothing from disk. A runner may be injected; the default runs ``hyprctl``.

Outputs
    ``reload()`` reports whether the compositor was asked and answered;
    ``config_errors()`` returns the current error lines or ``None`` when the
    compositor could not be asked; ``new_errors()`` returns only the lines that
    were not there before, which is the only set a rollback may act on.

Dependencies
    ``iarch.lib.runner``. Both commands are verified against the release this
    repository targets, and neither needs a ``TODO(verify)``:

      hyprctl reload        — Hyprland v0.57.2, src/ipc/s1/Commands.cpp:2113
                              legacyCommand("reload", COMMAND_MATCH_PREFIX, reloadRequest),
                              and docs/hyprctl.1.rst: "Force a reload of the config file."
      hyprctl configerrors  — src/ipc/s1/Commands.cpp:2104 legacyCommand("configerrors",
                              COMMAND_MATCH_EXACT, configErrorsRequest), described in
                              hyprctl/src/Strings.hpp as "Lists all current config parsing
                              errors". configErrorsRequest returns Config::mgr()->getErrors()
                              split on newlines, so empty output is a config the compositor
                              parsed cleanly.

    The same two citations are carried by ``iarch/cli/iarch_anim.py``, which keeps
    its own copy of this sequence: see D-T1-08 in docs/DECISIONS.md for why that
    tested pipeline was not moved under a theme-format change.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from iarch.lib import runner as default_runner
from iarch.lib.runner import Runner

HYPRCTL = "hyprctl"
RELOAD_COMMAND = (HYPRCTL, "reload")
CONFIGERRORS_COMMAND = (HYPRCTL, "configerrors")
HYPRCTL_TIMEOUT_SECONDS = 30.0


def reload(run: Optional[Runner] = None) -> Dict[str, Any]:
    """Ask the compositor to re-read its configuration.

    The report keeps three outcomes apart, because they mean different things to
    the caller: asked and answered, asked and refused, and never asked because
    ``hyprctl`` is not installed (a chroot, CI, a session that is not running).
    """
    execute = run or default_runner.run
    answer = execute(RELOAD_COMMAND, HYPRCTL_TIMEOUT_SECONDS)
    if answer is None:
        return {"asked": False, "reloaded": False, "verdict": "not-installed",
                "note": f"{HYPRCTL} is not installed, so the compositor was not asked to reload"}
    if answer.timed_out:
        return {"asked": True, "reloaded": False, "verdict": "timed-out",
                "note": answer.describe()}
    return {"asked": True, "reloaded": answer.ok,
            "verdict": "reloaded" if answer.ok else "refused",
            "note": None if answer.ok else answer.describe(),
            "returncode": answer.returncode}


def config_errors(run: Optional[Runner] = None) -> Optional[List[str]]:
    """The compositor's current config parsing errors, or ``None`` if it cannot say.

    Read as plain lines rather than as JSON on purpose: the JSON form is assembled
    by hand in ``configErrorsRequest`` while the normal form is exactly the error
    lines, which is the same information with no parser in between. Empty means a
    config the compositor parsed cleanly; ``None`` means it could not be asked, and
    a caller must not print ``None`` as "no errors".
    """
    execute = run or default_runner.run
    answer = execute(CONFIGERRORS_COMMAND, HYPRCTL_TIMEOUT_SECONDS)
    if answer is None or answer.timed_out or not answer.ok:
        return None
    return answer.lines()


def new_errors(baseline: Optional[Sequence[str]], after: Optional[Sequence[str]]) -> List[str]:
    """The error lines a change introduced.

    Errors that were already there are not this change's fault and rolling back
    would not remove them, so only lines absent from the baseline count. A baseline
    or a result that could not be read yields no new lines, which the caller reports
    as *unverified* rather than as clean.
    """
    if after is None:
        return []
    known = set(baseline or ())
    return [line for line in after if line not in known]


def verification(baseline: Optional[List[str]], after: Optional[List[str]],
                 reloaded: bool) -> Dict[str, Any]:
    """The one verdict shape every pipeline reports, so the wording cannot drift.

    ``clean`` — the compositor was asked and reports nothing new.
    ``rejected`` — it reports lines this change introduced; roll back.
    ``unverified`` — the reload or the read could not happen, so nothing is known.
    """
    if not reloaded:
        return {"baseline": baseline, "after": after, "new": [], "verdict": "unverified"}
    if after is None:
        return {"baseline": baseline, "after": None, "new": [], "verdict": "unverified"}
    fresh = new_errors(baseline, after)
    return {"baseline": baseline, "after": after, "new": fresh,
            "verdict": "rejected" if fresh else "clean"}
