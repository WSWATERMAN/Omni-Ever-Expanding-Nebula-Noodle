"""Parallel execution of one approved command across SSH inventory hosts."""

from concurrent.futures import ThreadPoolExecutor, as_completed
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
    """Enroll hosts serially, then execute the approved command concurrently."""

    def __init__(
        self,
        connector: SSHConnector | None = None,
        executor: SSHExecutor | None = None,
        max_workers: int = 8,
    ) -> None:
        """Create a bounded executor; serial enrollment keeps TOFU prompts legible."""
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer.")
        self.connector = connector or SSHConnector()
        self.executor = executor or SSHExecutor()
        self.max_workers = max_workers

    def execute(
        self,
        hosts: Iterable[HostRecord],
        command: str,
    ) -> list[HostExecutionResult]:
        """Enroll serially, run commands concurrently, and return input order.

        Serial connection setup ensures trust-on-first-use decisions are never
        prompted concurrently. Connection and execution errors are represented
        as failed host results; one host failure does not stop other hosts.
        """
        if not command.strip():
            raise ValueError("Command cannot be empty.")
        host_list = list(hosts)
        results: list[HostExecutionResult | None] = [None] * len(host_list)
        connected: list[tuple[int, HostRecord, object]] = []
        for index, host in enumerate(host_list):
            try:
                client = self.connector.connect(
                    host.hostname,
                    username=host.username,
                    port=host.port,
                )
                connected.append((index, host, client))
            except Exception as exc:
                results[index] = HostExecutionResult(host.name, 255, "", str(exc), False)

        def run_one(host: HostRecord, client: object) -> HostExecutionResult:
            try:
                remote = self.executor.execute(client, command)
                return HostExecutionResult(host.name, remote.exit_code, remote.stdout,
                                           remote.stderr, remote.exit_code == 0)
            except Exception as exc:
                return HostExecutionResult(host.name, 255, "", str(exc), False)

        try:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(connected)))) as pool:
                futures = {pool.submit(run_one, host, client): (index, host, client)
                           for index, host, client in connected}
                for future in as_completed(futures):
                    index, _host, _client = futures[future]
                    results[index] = future.result()
        finally:
            for _index, _host, client in connected:
                try:
                    client.close()
                except Exception:
                    pass
        return [result for result in results if result is not None]
