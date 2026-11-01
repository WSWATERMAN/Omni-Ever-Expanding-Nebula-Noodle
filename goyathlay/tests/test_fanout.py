"""Tests for parallel SSH fan-out with serialized trust enrollment."""

import threading
import unittest
from unittest.mock import Mock

from goyathlay.fanout import FanoutExecutor, HostExecutionResult
from goyathlay.inventory import HostRecord
from goyathlay.ssh.executor import SSHExecutionResult


class FanoutExecutorTests(unittest.TestCase):
    def setUp(self):
        self.hosts = [
            HostRecord("web01", "web01.example", 22, "ubuntu"),
            HostRecord("web02", "web02.example", 2222, "deploy"),
            HostRecord("web03", "web03.example", 22, "ubuntu"),
        ]
        self.connector = Mock()
        self.executor = Mock()
        self.clients = [Mock(), Mock(), Mock()]
        self.connector.connect.side_effect = self.clients
        self.fanout = FanoutExecutor(self.connector, self.executor)

    def test_single_host(self):
        self.executor.execute.return_value = SSHExecutionResult("ok\n", "", 0)

        results = self.fanout.execute(self.hosts[:1], "ss -tulpn")

        self.assertEqual(results, [HostExecutionResult("web01", 0, "ok\n", "", True)])
        self.connector.connect.assert_called_once_with(
            "web01.example", username="ubuntu", port=22
        )
        self.executor.execute.assert_called_once_with(self.clients[0], "ss -tulpn")
        self.clients[0].close.assert_called_once()

    def test_multiple_hosts_enroll_before_execution_and_preserve_order(self):
        order = []
        self.connector.connect.side_effect = lambda hostname, **kwargs: (
            order.append(f"connect:{hostname}") or self.clients[len(order) // 2]
        )
        self.executor.execute.side_effect = lambda client, command: (
            order.append(f"execute:{client}") or SSHExecutionResult("ok", "", 0)
        )

        results = self.fanout.execute(self.hosts, "ss -tulpn")

        self.assertEqual([item.host for item in results], ["web01", "web02", "web03"])
        self.assertEqual(len(results), 3)
        self.assertEqual(len(self.connector.connect.call_args_list), 3)
        self.assertTrue(all(result.success for result in results))
        self.assertEqual(len(order), 6)
        self.assertTrue(all(item.startswith("connect:") for item in order[:3]))
        self.assertTrue(all(item.startswith("execute:") for item in order[3:]))

    def test_commands_run_concurrently(self):
        barrier = threading.Barrier(3)
        def execute_together(client, command):
            barrier.wait(timeout=3)
            return SSHExecutionResult("parallel", "", 0)
        self.executor.execute.side_effect = execute_together

        results = self.fanout.execute(self.hosts, "true")

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result.success for result in results))

    def test_partial_failure_does_not_stop_later_hosts(self):
        outcomes = {
            id(self.clients[0]): SSHExecutionResult("ok", "", 0),
            id(self.clients[1]): RuntimeError("remote command failed"),
            id(self.clients[2]): SSHExecutionResult("ok", "", 0),
        }
        def execute_by_client(client, command):
            outcome = outcomes[id(client)]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        self.executor.execute.side_effect = execute_by_client

        results = self.fanout.execute(self.hosts, "true")

        self.assertEqual([result.success for result in results], [True, False, True])
        self.assertEqual(results[1].exit_code, 255)
        self.assertEqual(results[1].stderr, "remote command failed")
        self.assertEqual(self.connector.connect.call_count, 3)

    def test_total_failure_returns_failed_result_for_each_host(self):
        self.connector.connect.side_effect = OSError("unreachable")

        results = self.fanout.execute(self.hosts, "true")

        self.assertEqual(len(results), len(self.hosts))
        self.assertTrue(all(not result.success for result in results))
        self.assertTrue(all(result.exit_code == 255 for result in results))
        self.executor.execute.assert_not_called()

    def test_connector_exception_does_not_prevent_next_host(self):
        self.connector.connect.side_effect = [
            OSError("first host unavailable"),
            self.clients[1],
        ]
        self.executor.execute.return_value = SSHExecutionResult("ok", "", 0)

        results = self.fanout.execute(self.hosts[:2], "true")

        self.assertEqual([result.success for result in results], [False, True])
        self.assertEqual(self.executor.execute.call_count, 1)
        self.assertEqual(results[0].stderr, "first host unavailable")

    def test_aggregation_reflects_success_and_failure_counts(self):
        outcomes = {
            id(self.clients[0]): SSHExecutionResult("", "", 0),
            id(self.clients[1]): SSHExecutionResult("", "denied", 1),
            id(self.clients[2]): SSHExecutionResult("", "", 0),
        }
        self.executor.execute.side_effect = lambda client, command: outcomes[id(client)]

        results = self.fanout.execute(self.hosts, "true")
        success_count = sum(result.success for result in results)

        self.assertEqual((len(results), success_count, len(results) - success_count), (3, 2, 1))

    def test_empty_command_is_rejected(self):
        with self.assertRaises(ValueError):
            self.fanout.execute(self.hosts, "  ")


if __name__ == "__main__":
    unittest.main()
