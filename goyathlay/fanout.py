"""Sequential execution of one approved command across SSH inventory hosts."""

from dataclasses import dataclass
from typing import Iterable

from .inventory import HostRecord
from .ssh.connector import SSHConnector
from .ssh.executor import SSHExecutor


@dataclass(frozen=True)
class HostExecutionResult:
    """Result of attempting an approved command on one inventory host."""

    host: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool


class FanoutExecutor:
    """Execute commands sequentially, continuing after per-host failures."""

    def __init__(
        self,
        connector: SSHConnector | None = None,
        executor: SSHExecutor | None = None,
    ) -> None:
        """Create an executor with reusable SSH connector and command executor."""
        self.connector = connector or SSHConnector()
        self.executor = executor or SSHExecutor()

    def execute(
        self,
        hosts: Iterable[HostRecord],
        command: str,
    ) -> list[HostExecutionResult]:
        """Run the command once per host and return results in input order.

        Connection, authentication, and remote execution errors are represented
        as failed host results. A failure for one host does not stop the loop.
        """
        if not command.strip():
            raise ValueError("Command cannot be empty.")
        results: list[HostExecutionResult] = []
        for host in hosts:
            client = None
            try:
                client = self.connector.connect(
                    host.hostname,
                    username=host.username,
                    port=host.port,
                )
                remote = self.executor.execute(client, command)
                results.append(
                    HostExecutionResult(
                        host=host.name,
                        exit_code=remote.exit_code,
                        stdout=remote.stdout,
                        stderr=remote.stderr,
                        success=remote.exit_code == 0,
                    )
                )
            except Exception as exc:
                results.append(
                    HostExecutionResult(
                        host=host.name,
                        exit_code=255,
                        stdout="",
                        stderr=str(exc),
                        success=False,
                    )
                )
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
        return results
