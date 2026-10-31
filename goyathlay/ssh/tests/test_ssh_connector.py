"""Tests for TOFU-enforced SSH connection setup."""

import unittest
from unittest.mock import Mock

from goyathlay.ssh.connector import SSHConnectionError, SSHConnector
from goyathlay.ssh.enrollment import EnrollmentResult


class FakeKey:
    def get_name(self):
        return "ssh-ed25519"

    def asbytes(self):
        return b"test-public-key-bytes"


class FakeTransport:
    def __init__(self, sock):
        self.sock = sock
        self.closed = False

    def start_client(self, timeout):
        pass

    def get_remote_server_key(self):
        return FakeKey()

    def close(self):
        self.closed = True


class FakeHostKeys:
    def __init__(self):
        self.entries = []

    def add(self, hostname, keytype, key):
        self.entries.append((hostname, keytype, key))


class FakeRejectPolicy:
    pass


class FakeSSHClient:
    def __init__(self):
        self.host_keys = FakeHostKeys()
        self.policy = None
        self.connect_args = None
        self.closed = False

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def get_host_keys(self):
        return self.host_keys

    def connect(self, **kwargs):
        self.connect_args = kwargs

    def close(self):
        self.closed = True


class FakeParamiko:
    Transport = FakeTransport
    RejectPolicy = FakeRejectPolicy

    def __init__(self):
        self.client = FakeSSHClient()

    def SSHClient(self):
        return self.client


class SSHConnectorTests(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.paramiko = FakeParamiko()
        self.connector = SSHConnector(
            self.manager,
            paramiko_module=self.paramiko,
            socket_factory=lambda address, timeout: Mock(),
        )

    def test_already_trusted_host_connects_with_reject_policy(self):
        self.manager.enroll.return_value = EnrollmentResult.ALREADY_TRUSTED

        client = self.connector.connect("server01", "scott")

        self.assertIs(client, self.paramiko.client)
        self.assertIsInstance(client.policy, FakeRejectPolicy)
        self.assertEqual(client.host_keys.entries[0][:2], ("server01", "ssh-ed25519"))
        self.assertEqual(client.connect_args["username"], "scott")

    def test_unknown_host_is_connected_after_permanent_trust(self):
        self.manager.enroll.return_value = EnrollmentResult.TRUST_PERMANENT

        self.connector.connect("server01", "scott")

        self.manager.enroll.assert_called_once()
        self.assertEqual(self.paramiko.client.connect_args["hostname"], "server01")

    def test_one_time_trust_connects_without_writing_store(self):
        self.manager.enroll.return_value = EnrollmentResult.TRUST_ONCE

        self.connector.connect("server01", "scott")

        self.assertTrue(self.paramiko.client.connect_args)
        self.assertEqual(len(self.paramiko.client.host_keys.entries), 1)

    def test_rejected_unknown_host_does_not_connect(self):
        self.manager.enroll.return_value = EnrollmentResult.REJECT

        with self.assertRaises(SSHConnectionError):
            self.connector.connect("server01", "scott")

        self.paramiko.SSHClient = Mock(side_effect=AssertionError("must not connect"))

    def test_changed_fingerprint_rejection_blocks_connection(self):
        self.manager.enroll.return_value = EnrollmentResult.REJECT

        with self.assertRaises(SSHConnectionError):
            self.connector.connect("server01", "scott")

        self.assertIsNone(self.paramiko.client.connect_args)

    def test_explicit_replacement_requires_a_fresh_trust_check(self):
        self.manager.enroll.return_value = EnrollmentResult.REPLACED

        with self.assertRaisesRegex(SSHConnectionError, "reconnect to verify"):
            self.connector.connect("server01", "scott")

        self.assertIsNone(self.paramiko.client.connect_args)


if __name__ == "__main__":
    unittest.main()
