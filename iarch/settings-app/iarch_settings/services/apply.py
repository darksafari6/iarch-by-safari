# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The apply pipeline: the only path from a switch on screen to a file on disk.

Every change in this application goes through :meth:`Applier.run`, and the reason
is that a change made in six places is a change made in six different ways. The
sequence is fixed:

1. **validate** the settings document against ``data/schemas/settings.schema.json``.
   A value the schema rejects is refused before anything is written, because a
   generator downstream clamps or refuses it and the user would see a change they
   did not make;
2. **back up** every file the change will touch, including settings.json itself,
   through :mod:`iarch.lib.configstore` -- which rotates five backups per file with
   sortable timestamped names, so a restore point is not a one-shot;
3. **write** the settings, atomically: a temp file in the destination directory,
   an fsync, a rename, the previous mode carried over;
4. **run** the generators and tools that own the surfaces being changed. Never a
   reimplementation of one: applying a theme calls ``iarch-theme apply``, changing
   motion calls ``iarch-anim``, rendering monitors calls ``gen_monitors_lua.py``;
5. **validate the output** -- a generated file that does not parse, or that lost
   its GENERATED header, is a failed step even though the tool exited 0;
6. **reload** the compositor and **verify** with ``hyprctl configerrors``. Empty
   output is a configuration the compositor parsed cleanly;
7. on any failure, **restore** every backup taken in step 2 and report what was
   restored. The toast says the change was undone and names the files, because a
   silent rollback is indistinguishable from a change that never happened.

Two rules the pipeline holds that are easy to get wrong:

* **A missing compositor is not a failure.** Steps 6 and 7 come back *unverified*
  when there is no ``hyprctl`` or no session, and an unverified apply is reported
  as one: the files were written and could not be checked, which is a different
  sentence from "it worked" and a different one from "it broke". ``iarch/lib/modes.py``
  already draws this line for the mode switches and this pipeline inherits it.
* **A refusal is a verdict, not a crash.** ``iarch-theme apply`` exits 1 when the
  contrast gate refuses an unreadable accent. That is the tool working, so the
  report carries the tool's own sentence and the pipeline rolls back rather than
  retrying or overriding it.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import paths
from . import config_store, hypr, runner

#: The pipeline's step names, in the order they run. A test asserts the report
#: contains these, so a step cannot be dropped quietly.
STEPS = ("validate", "backup", "write", "commands", "validate_output", "reload", "verify")

#: How long a command in the pipeline may take before it is treated as failed.
COMMAND_TIMEOUT = 60.0

#: A generated payload's first line must be the GENERATED sentence, or the file has
#: been overwritten by something that is not this project.
HEADER_REQUIRED_SUFFIXES = (".lua", ".css", ".conf", ".toml", ".kvconfig")


class ApplyError(RuntimeError):
    """The pipeline was asked to do something it refuses."""


class StepResult:
    """One step's outcome. ``detail`` is always a sentence, never a stack trace."""

    __slots__ = ("name", "verdict", "detail", "data")

    def __init__(self, name: str, verdict: str, detail: str = "",
                 data: Optional[Dict[str, Any]] = None) -> None:
        if name not in STEPS:
            raise ApplyError(f"{name!r} is not one of {', '.join(STEPS)}")
        self.name = name
        self.verdict = verdict
        self.detail = detail
        self.data = data or {}

    @property
    def ok(self) -> bool:
        return self.verdict == runner.OK

    def as_dict(self) -> Dict[str, Any]:
        return {"step": self.name, "verdict": self.verdict, "detail": self.detail,
                **self.data}


class Change:
    """One thing the user asked for.

    ``settings`` is a mapping of dotted paths to values, written to settings.json
    before any command runs, so a command that reads the file sees the new state.
    ``commands`` is a list of ``(label, callable)`` pairs; each callable returns a
    :class:`runner.Outcome`. ``targets`` are the files to back up and, on failure,
    to restore -- settings.json is added automatically and does not need listing.
    ``risky`` marks a change that needs the countdown dialog, which is a monitor
    scale or resolution: the one kind of change that can leave the dialog itself
    unreadable.
    """

    def __init__(
        self,
        label: str,
        *,
        settings: Optional[Mapping[str, Any]] = None,
        commands: Optional[Sequence[Tuple[str, Callable[[], runner.Outcome]]]] = None,
        targets: Optional[Sequence[Path]] = None,
        risky: bool = False,
        verify_configerrors: bool = True,
        reload_session: bool = True,
        config_home: Optional[Path] = None,
    ) -> None:
        if not label:
            raise ApplyError("a change needs a label: it is the sentence the toast shows")
        self.label = label
        self.settings: Dict[str, Any] = dict(settings or {})
        self.commands: List[Tuple[str, Callable[[], runner.Outcome]]] = list(commands or [])
        self.targets: List[Path] = [Path(target) for target in (targets or ())]
        self.risky = risky
        self.verify_configerrors = verify_configerrors
        self.reload_session = reload_session
        self.config_home = config_home

    def add_command(self, label: str, call: Callable[[], runner.Outcome]) -> "Change":
        self.commands.append((label, call))
        return self

    def add_target(self, path: Path) -> "Change":
        path = Path(path)
        if path not in self.targets:
            self.targets.append(path)
        return self


class Report:
    """What the pipeline did. Every key a caller may read exists."""

    def __init__(self, change: Change) -> None:
        self.change = change
        self.label = change.label
        self.steps: List[StepResult] = []
        self.backups: Dict[str, str] = {}
        self.restored: List[str] = []
        self.restore_failed: List[str] = []
        self.written: List[str] = []

    @property
    def verdict(self) -> str:
        """The worst verdict any step reached, in the order the pipeline cares about."""
        verdicts = [step.verdict for step in self.steps]
        if runner.FAILED in verdicts:
            return runner.FAILED
        if runner.UNVERIFIED in verdicts:
            return runner.UNVERIFIED
        return runner.OK

    @property
    def ok(self) -> bool:
        return self.verdict == runner.OK

    @property
    def rolled_back(self) -> bool:
        return bool(self.restored)

    def add(self, step: StepResult) -> StepResult:
        self.steps.append(step)
        return step

    def failed_step(self) -> Optional[StepResult]:
        for step in self.steps:
            if step.verdict == runner.FAILED:
                return step
        return None

    def message(self) -> str:
        """One sentence for a toast. It never says "success" without naming what ran."""
        failed = self.failed_step()
        if failed is not None:
            if self.restored:
                return (f"{self.label}: {failed.detail} "
                        f"Undone — restored {', '.join(self.restored)}.")
            return f"{self.label}: {failed.detail}"
        if self.verdict == runner.UNVERIFIED:
            unverified = [step.name for step in self.steps
                          if step.verdict == runner.UNVERIFIED]
            return (f"{self.label}: written, but {', '.join(unverified)} could not be "
                    f"checked — no compositor session to ask.")
        return f"{self.label}: applied and verified."

    def as_dict(self) -> Dict[str, Any]:
        """The stable report shape."""
        return {
            "label": self.label,
            "verdict": self.verdict,
            "message": self.message(),
            "steps": [step.as_dict() for step in self.steps],
            "backups": dict(self.backups),
            "restored": list(self.restored),
            "restore_failed": list(self.restore_failed),
            "written": list(self.written),
            "risky": self.change.risky,
        }


def output_is_sane(path: Path) -> Tuple[bool, str]:
    """Does this generated file still look like something this project wrote?

    A tool that exits 0 and leaves a truncated file is the failure mode this step
    exists for. What is checked depends on the file: JSON has to parse, and a
    payload of a type this project generates has to start with the GENERATED
    sentence, because a file that lost its header has been overwritten by something
    that is not a generator.
    """
    if not path.exists():
        return False, f"{path.name} does not exist after the change"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"{path.name} could not be read back: {exc}"
    if not text.strip():
        return False, f"{path.name} is empty after the change"
    if path.suffix == ".json":
        import json

        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            return False, f"{path.name} is not valid JSON after the change: {exc.msg}"
    if path.suffix in HEADER_REQUIRED_SUFFIXES:
        paths.add_repo_to_path()
        from iarch.lib import configstore  # noqa: PLC0415

        first = text.splitlines()[0]
        if not configstore.is_header_line(first):
            return False, (f"{path.name} lost its GENERATED header, so something other "
                           f"than a generator wrote it: {first[:60]!r}")
    return True, ""


def _last_line(text: str) -> str:
    """The last non-empty line of a tool's stderr, which is where its sentence is."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


class Applier:
    """Runs a :class:`Change` through the fixed sequence and rolls back on failure.

    ``reload`` and ``config_errors`` are parameters so a test can drive the whole
    pipeline with fakes and no compositor, which is the only way this can be tested
    at all in CI: the sandbox has no ``hyprctl``, and a pipeline that could only be
    exercised on a real session is a pipeline nobody has exercised.
    """

    def __init__(
        self,
        store: config_store.Store,
        *,
        reload: Optional[Callable[[], runner.Outcome]] = None,
        config_errors: Optional[Callable[[], Tuple[Optional[List[str]], str]]] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: float = COMMAND_TIMEOUT,
    ) -> None:
        self.store = store
        self._reload = reload if reload is not None else hypr.reload
        self._config_errors = (config_errors if config_errors is not None
                               else hypr.config_errors)
        self._env = dict(env) if env else None
        self.timeout = timeout

    # -- individual steps --------------------------------------------------

    def validate(self, report: Report) -> StepResult:
        """Step 1: the document the change would produce, against the schema."""
        document = dict(self.store.data)
        for dotted, value in report.change.settings.items():
            node: Any = document
            keys = [part for part in dotted.split(".") if part]
            for key in keys[:-1]:
                node = node.setdefault(key, {})
                if not isinstance(node, dict):
                    return report.add(StepResult(
                        "validate", runner.FAILED,
                        f"{dotted} cannot be set: {'.'.join(keys[:-1])} is not an object"))
            node[keys[-1]] = value
        document = config_store.derive_coarse(document)
        problems = config_store.validation_problems(document)
        if problems:
            return report.add(StepResult(
                "validate", runner.FAILED,
                "the change would write a settings.json the schema rejects: "
                + "; ".join(problems[:3]),
                {"problems": problems}))
        return report.add(StepResult("validate", runner.OK,
                                     "the change validates against the settings schema",
                                     {"validator": config_store.validator_state()}))

    def backup(self, report: Report) -> StepResult:
        """Step 2: a restore point for every file the change will touch."""
        targets = [self.store.user_path, *report.change.targets]
        seen: List[Path] = []
        for target in targets:
            if target not in seen:
                seen.append(target)
        missing: List[str] = []
        for target in seen:
            if not target.exists():
                # A file that does not exist yet has nothing to restore, and saying
                # so is not a failure: a first run creates it.
                missing.append(target.name)
                continue
            paths.add_repo_to_path()
            from iarch.lib import configstore  # noqa: PLC0415

            backup = configstore.backup_of(target, self._env)
            if backup is None:
                return report.add(StepResult(
                    "backup", runner.FAILED,
                    f"{target} exists but no backup could be taken, so the change is "
                    "refused: there would be nothing to restore"))
            report.backups[str(target)] = str(backup)
        return report.add(StepResult(
            "backup", runner.OK,
            f"{len(report.backups)} backup{'s' if len(report.backups) != 1 else ''} taken"
            + (f"; {', '.join(missing)} did not exist yet" if missing else ""),
            {"created": missing}))

    def write(self, report: Report) -> StepResult:
        """Step 3: settings.json, atomically."""
        try:
            written = self.store.save(report.change.settings or None)
        except (config_store.ConfigStoreError, OSError) as exc:
            return report.add(StepResult("write", runner.FAILED, str(exc)))
        report.written.append(str(written))
        return report.add(StepResult("write", runner.OK, f"wrote {written.name}"))

    def run_commands(self, report: Report) -> StepResult:
        """Step 4: the tools that own the surfaces being changed."""
        if not report.change.commands:
            return report.add(StepResult("commands", runner.OK,
                                         "no generator or tool was needed"))
        details: List[str] = []
        results: List[Dict[str, Any]] = []
        for label, call in report.change.commands:
            try:
                outcome = call()
            except Exception as exc:  # noqa: BLE001 - a tool's own error is a step failure
                outcome = runner.Outcome([label], runner.FAILED, reason=f"{exc}")
            results.append({"command": label, **outcome.as_dict()})
            details.append(f"{label}: {outcome.verdict}")
            if outcome.verdict == runner.FAILED:
                reason = (outcome.reason or _last_line(outcome.stderr)
                          or _last_line(outcome.stdout) or "no reason given")
                return report.add(StepResult(
                    "commands", runner.FAILED, f"{label} failed: {reason}",
                    {"commands": results}))
        for target in report.change.targets:
            if target.exists() and str(target) not in report.written:
                report.written.append(str(target))
        unverified = [item["command"] for item in results
                      if item["verdict"] == runner.UNVERIFIED]
        verdict = runner.UNVERIFIED if unverified else runner.OK
        detail = "; ".join(details)
        if unverified:
            detail += (f" — {', '.join(unverified)} could not be run, so what they would "
                       "have changed is unverified")
        return report.add(StepResult("commands", verdict, detail, {"commands": results}))

    def validate_output(self, report: Report) -> StepResult:
        """Step 5: the files exist, parse, and still carry their GENERATED header."""
        checked = 0
        for target in report.change.targets:
            sane, problem = output_is_sane(target)
            checked += 1
            if not sane:
                return report.add(StepResult("validate_output", runner.FAILED, problem))
        if not checked:
            return report.add(StepResult("validate_output", runner.OK,
                                         "no generated file to check"))
        return report.add(StepResult("validate_output", runner.OK,
                                     f"{checked} generated file"
                                     f"{'s' if checked != 1 else ''} still parse and carry "
                                     "their header"))

    def reload(self, report: Report) -> StepResult:
        """Step 6: ask the compositor to re-parse. Synchronous, so step 7 means now."""
        if not report.change.reload_session:
            return report.add(StepResult("reload", runner.OK,
                                         "no reload asked for (--no-reload)"))
        outcome = self._reload()
        if not outcome.ran:
            return report.add(StepResult("reload", runner.UNVERIFIED, outcome.reason))
        if not outcome.ok:
            return report.add(StepResult("reload", runner.FAILED,
                                         outcome.reason or "the compositor refused to reload"))
        return report.add(StepResult("reload", runner.OK, "the compositor re-parsed its config"))

    def verify(self, report: Report) -> StepResult:
        """Step 7: ``hyprctl configerrors`` is empty."""
        if not report.change.verify_configerrors:
            return report.add(StepResult("verify", runner.OK, "no compositor check asked for"))
        errors, verdict = self._config_errors()
        if verdict == runner.UNVERIFIED:
            return report.add(StepResult(
                "verify", runner.UNVERIFIED,
                "the compositor could not be asked for its config errors, so the files are "
                "written and unchecked"))
        if verdict == runner.FAILED:
            return report.add(StepResult(
                "verify", runner.FAILED,
                "the compositor could not answer `hyprctl configerrors` at all"))
        if errors:
            return report.add(StepResult(
                "verify", runner.FAILED,
                "the compositor reports config errors after the change: "
                + "; ".join(errors[:3]), {"errors": errors}))
        return report.add(StepResult("verify", runner.OK,
                                     "the compositor parsed the new configuration cleanly"))

    # -- rollback ----------------------------------------------------------

    def restore(self, report: Report) -> None:
        """Put every backup taken in step 2 back over its file."""
        for target, backup in report.backups.items():
            source = Path(backup)
            destination = Path(target)
            if not source.exists():
                report.restore_failed.append(destination.name)
                continue
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            except OSError:
                report.restore_failed.append(destination.name)
                continue
            report.restored.append(destination.name)
        # The in-memory document has to go back too, or the next save would write
        # the values that were just rolled back on disk.
        try:
            self.store.load()
        except Exception:  # noqa: BLE001 - a rollback must not raise over a reload
            pass

    # -- the sequence ------------------------------------------------------

    def run(self, change: Change) -> Report:
        """The whole pipeline. Never raises for a step that failed; it rolls back."""
        report = Report(change)
        sequence: List[Tuple[str, Callable[[Report], StepResult]]] = [
            ("validate", self.validate),
            ("backup", self.backup),
            ("write", self.write),
            ("commands", self.run_commands),
            ("validate_output", self.validate_output),
            ("reload", self.reload),
            ("verify", self.verify),
        ]
        for _name, step in sequence:
            result = step(report)
            if result.verdict == runner.FAILED:
                self.restore(report)
                return report
        return report


def config_target(name: str, *parts: str, config_home: Optional[Path] = None) -> Path:
    """A live-session file this project generates, under ``config_home``.

    ``config_home`` defaults to ``~/.config`` because that is what the session
    reads. The renderers default to ``~/.config/iarch/<tool>``, so a caller that
    forgets to pass ``--config-home`` writes a file nothing reads -- which is the
    mistake this helper exists to make awkward.
    """
    home = config_home or (Path.home() / ".config")
    return home.joinpath(name, *parts)
