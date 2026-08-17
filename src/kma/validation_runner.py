"""Catalog-bound Kyverno validation inside an offline Bubblewrap sandbox."""

from __future__ import annotations

import os
import platform
import pwd
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Protocol

from kma.canonical import safe_terminal_text, sha256_digest

_BWRAP = Path("/usr/bin/bwrap")
_PRLIMIT = Path("/usr/bin/prlimit")
_TIMEOUT = Path("/usr/bin/timeout")
_SYSTEM_GO = Path("/usr/bin/go")
_GO_DIRECTIVE = re.compile(r"(?m)^go\s+(\d+\.\d+(?:\.\d+)?)\s*$")
_GO_VERSION = re.compile(r"go(\d+)\.(\d+)(?:\.(\d+))?")


class ValidationRuntimeError(RuntimeError):
    """A sanitized failure to establish the required validation boundary."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class ValidationRunner(Protocol):
    def readiness(self) -> dict[str, Any]:
        """Return non-secret runtime facts or raise ValidationRuntimeError."""

    def run(
        self,
        *,
        target_id: str,
        command_argv: tuple[str, ...],
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        """Execute one catalog-resolved command and return bounded evidence."""


class OfflineBubblewrapRunner:
    """Run a fixed Go test target without host network, credentials, or writable source."""

    def __init__(self, repository_root: Path, *, repository_revision: str) -> None:
        self.root = repository_root.resolve(strict=True)
        self.repository_revision = repository_revision

    @staticmethod
    def _sanitized_go_environment() -> dict[str, str]:
        return {
            "GOENV": "off",
            "GOTOOLCHAIN": "local",
            "HOME": pwd.getpwuid(os.getuid()).pw_dir,
            "PATH": "/usr/bin:/bin",
        }

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, int, int]:
        match = _GO_VERSION.search(value)
        if match is None:
            raise ValidationRuntimeError("VALIDATION.GO_VERSION_UNAVAILABLE")
        return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]

    def _required_go_version(self) -> str:
        try:
            text = (self.root / "go.mod").read_text(encoding="utf-8")
        except OSError as error:
            raise ValidationRuntimeError("VALIDATION.GO_MOD_UNAVAILABLE") from error
        match = _GO_DIRECTIVE.search(text)
        if match is None:
            raise ValidationRuntimeError("VALIDATION.GO_VERSION_UNAVAILABLE")
        return match.group(1)

    def _go_environment(self) -> tuple[Path, str, Path]:
        if not _SYSTEM_GO.is_file():
            raise ValidationRuntimeError("VALIDATION.GO_RUNTIME_UNAVAILABLE")
        try:
            completed = subprocess.run(
                [str(_SYSTEM_GO), "env", "GOROOT", "GOVERSION", "GOMODCACHE"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
                cwd="/",
                env=self._sanitized_go_environment(),
            )
            goroot_text, version, module_cache_text = completed.stdout.splitlines()
            goroot = Path(goroot_text).resolve(strict=True)
            module_cache = Path(module_cache_text).resolve(strict=True)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise ValidationRuntimeError("VALIDATION.GO_RUNTIME_UNAVAILABLE") from error

        required = self._required_go_version()
        if self._version_tuple(version) < self._version_tuple(f"go{required}"):
            host_os = platform.system().lower()
            architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(
                platform.machine().lower()
            )
            if architecture is None:
                raise ValidationRuntimeError("VALIDATION.GO_RUNTIME_UNAVAILABLE")
            cached = (
                module_cache
                / "golang.org"
                / f"toolchain@v0.0.1-go{required}.{host_os}-{architecture}"
            )
            try:
                goroot = cached.resolve(strict=True)
            except OSError as error:
                raise ValidationRuntimeError("VALIDATION.GO_TOOLCHAIN_NOT_CACHED") from error
            version = f"go{required}"

        if not (goroot / "bin" / "go").is_file():
            raise ValidationRuntimeError("VALIDATION.GO_RUNTIME_UNAVAILABLE")
        return goroot, version, module_cache

    def readiness(self) -> dict[str, Any]:
        for executable in (_BWRAP, _PRLIMIT, _TIMEOUT):
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise ValidationRuntimeError("VALIDATION.SANDBOX_UNAVAILABLE")
        try:
            probe = subprocess.run(
                [
                    str(_BWRAP),
                    "--unshare-all",
                    "--unshare-user",
                    "--disable-userns",
                    "--assert-userns-disabled",
                    "--die-with-parent",
                    "--new-session",
                    "--cap-drop",
                    "ALL",
                    "--ro-bind",
                    "/usr",
                    "/usr",
                    "--symlink",
                    "usr/bin",
                    "/bin",
                    "--symlink",
                    "usr/lib",
                    "/lib",
                    "--symlink",
                    "usr/lib64",
                    "/lib64",
                    "--proc",
                    "/proc",
                    "--dev",
                    "/dev",
                    "--clearenv",
                    "/usr/bin/true",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ValidationRuntimeError("VALIDATION.SANDBOX_UNAVAILABLE") from error
        if probe.returncode != 0:
            raise ValidationRuntimeError("VALIDATION.SANDBOX_UNAVAILABLE")
        goroot, version, module_cache = self._go_environment()
        return {
            "backend": "bubblewrap",
            "network": "unshared",
            "source_mount": "read-only",
            "environment": "cleared",
            "go_version": version,
            "go_runtime_digest": sha256_digest(
                {
                    "goroot": goroot.name,
                    "go_binary": (goroot / "bin" / "go").stat().st_size,
                }
            ),
            "module_cache_available": module_cache.is_dir(),
        }

    @staticmethod
    def _bounded_output(handle, max_output_bytes: int) -> tuple[str, str, bool]:
        handle.seek(0)
        payload = handle.read()
        digest = sha256_digest(payload)
        truncated = len(payload) > max_output_bytes
        preview = payload[:max_output_bytes].decode("utf-8", errors="replace")
        return safe_terminal_text(preview, limit=max_output_bytes), digest, truncated

    def _sandbox_argv(
        self,
        *,
        goroot: Path,
        module_cache: Path,
        command_argv: tuple[str, ...],
        timeout_seconds: int,
    ) -> list[str]:
        sandbox_command = ["/goroot/bin/go", *command_argv[1:]]
        return [
            str(_TIMEOUT),
            "--signal=TERM",
            "--kill-after=5s",
            f"{timeout_seconds}s",
            str(_PRLIMIT),
            "--nofile=512:512",
            "--fsize=134217728:134217728",
            "--as=6442450944:6442450944",
            "--",
            str(_BWRAP),
            "--unshare-all",
            "--unshare-user",
            "--disable-userns",
            "--assert-userns-disabled",
            "--die-with-parent",
            "--new-session",
            "--hostname",
            "kma-validation",
            "--cap-drop",
            "ALL",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            "1073741824",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/tmp/home",
            "--dir",
            "/workspace",
            "--ro-bind",
            str(self.root),
            "/workspace",
            "--dir",
            "/gomodcache",
            "--ro-bind",
            str(module_cache),
            "/gomodcache",
            "--dir",
            "/goroot",
            "--ro-bind",
            str(goroot),
            "/goroot",
            "--chdir",
            "/workspace",
            "--clearenv",
            "--setenv",
            "PATH",
            "/goroot/bin:/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/tmp/home",
            "--setenv",
            "GOENV",
            "off",
            "--setenv",
            "GOTOOLCHAIN",
            "local",
            "--setenv",
            "GOPROXY",
            "off",
            "--setenv",
            "GOSUMDB",
            "off",
            "--setenv",
            "GOMODCACHE",
            "/gomodcache",
            "--setenv",
            "GOCACHE",
            "/tmp/go-build",
            "--setenv",
            "GOTMPDIR",
            "/tmp",
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "CGO_ENABLED",
            "0",
            "--setenv",
            "TZ",
            "UTC",
            *sandbox_command,
        ]

    def run(
        self,
        *,
        target_id: str,
        command_argv: tuple[str, ...],
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        if len(command_argv) < 3 or command_argv[:2] != ("go", "test"):
            raise ValidationRuntimeError("VALIDATION.COMMAND_PROFILE_DENIED")
        self.readiness()
        goroot, version, module_cache = self._go_environment()
        argv = self._sandbox_argv(
            goroot=goroot,
            module_cache=module_cache,
            command_argv=command_argv,
            timeout_seconds=timeout_seconds,
        )
        started = time.monotonic()
        try:
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                completed = subprocess.run(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    check=False,
                    timeout=timeout_seconds + 10,
                    close_fds=True,
                )
                stdout_preview, stdout_digest, stdout_truncated = self._bounded_output(
                    stdout, max_output_bytes
                )
                stderr_preview, stderr_digest, stderr_truncated = self._bounded_output(
                    stderr, max_output_bytes
                )
        except subprocess.TimeoutExpired as error:
            raise ValidationRuntimeError("VALIDATION.SANDBOX_TIMEOUT") from error
        except OSError as error:
            raise ValidationRuntimeError("VALIDATION.SANDBOX_UNAVAILABLE") from error

        exit_code = completed.returncode
        timed_out = exit_code in {124, 137}
        outcome = "timed_out" if timed_out else "passed" if exit_code == 0 else "failed"
        return {
            "target_id": target_id,
            "outcome": outcome,
            "exit_code": exit_code,
            "repository_revision": self.repository_revision,
            "command_argv": list(command_argv),
            "command_digest": sha256_digest(command_argv),
            "sandbox": {
                "backend": "bubblewrap",
                "network": "unshared",
                "source_mount": "read-only",
                "environment": "cleared",
                "capabilities": "dropped",
                "go_version": version,
                "timeout_seconds": timeout_seconds,
            },
            "stdout_preview": stdout_preview,
            "stderr_preview": stderr_preview,
            "stdout_digest": stdout_digest,
            "stderr_digest": stderr_digest,
            "output_truncated": stdout_truncated or stderr_truncated,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
