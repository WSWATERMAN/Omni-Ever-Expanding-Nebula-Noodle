"""Non-interactive execution of approved commands over SSH."""

import time
from dataclasses import dataclass
from typing import Any


class SSHExecutionError(RuntimeError):
    """Raised when a remote command cannot be started or its result read."""


@dataclass(frozen=True)
class SSHExecutionResult:
    """Captured output and status returned by an SSH command."""

    stdout: str
    stderr: str
    exit_code: int


class SSHExecutor:
    """Run a command through an established SSH client without a PTY."""

    def execute(self, client: Any, command: str) -> SSHExecutionResult:
        """Execute the approved command and capture both streams and status."""
        if not command.strip():
            raise ValueError("Command cannot be empty.")
        try:
            _stdin, stdout_file, stderr_file = client.exec_command(command, get_pty=False)
            channel = stdout_file.channel
            out_chunks: list[bytes] = []
            err_chunks: list[bytes] = []
            while not channel.exit_status_ready():
                if channel.recv_ready():
                    out_chunks.append(channel.recv(32768))
                if channel.recv_stderr_ready():
                    err_chunks.append(channel.recv_stderr(32768))
                if not channel.recv_ready() and not channel.recv_stderr_ready() and not channel.exit_status_ready():
                    time.sleep(0.01)
            while channel.recv_ready():
                out_chunks.append(channel.recv(32768))
            while channel.recv_stderr_ready():
                err_chunks.append(channel.recv_stderr(32768))
            exit_code = channel.recv_exit_status()
            return SSHExecutionResult(
                stdout=b"".join(out_chunks).decode("utf-8", errors="replace"),
                stderr=b"".join(err_chunks).decode("utf-8", errors="replace"),
                exit_code=exit_code,
            )
        except Exception as exc:
            raise SSHExecutionError(f"Remote command could not be executed: {exc}") from exc
