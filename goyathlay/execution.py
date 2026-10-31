"""Run approved commands without invoking a command shell."""

import shlex
import subprocess


class ExecutionError(RuntimeError):
    """Raised when a command cannot be parsed, started, or completes in error."""

    def __init__(self, message: str, return_code: int | None = None) -> None:
        super().__init__(message)
        self.return_code = return_code


class ExecutionManager:
    """Execute commands as argument arrays and capture their results."""

    def execute(self, command: str) -> subprocess.CompletedProcess[str]:
        """Run a command, returning captured output when it exits successfully.

        Raises:
            ExecutionError: If the command is empty, invalid, unavailable, or
                exits with a nonzero status.
        """
        try:
            arguments = shlex.split(command)
        except ValueError as exc:
            raise ExecutionError(f"Invalid command syntax: {exc}") from exc

        if not arguments:
            raise ExecutionError("Command cannot be empty.")

        try:
            return subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            executable = arguments[0]
            raise ExecutionError(f"Command not found: {executable}") from exc
        except subprocess.CalledProcessError as exc:
            raise ExecutionError(
                f"Command exited with status {exc.returncode}: {arguments[0]}",
                return_code=exc.returncode,
            ) from exc
        except OSError as exc:
            raise ExecutionError(f"Could not execute {arguments[0]}: {exc}") from exc
