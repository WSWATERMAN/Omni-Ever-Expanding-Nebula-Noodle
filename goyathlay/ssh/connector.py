"""SSH connection setup guarded by explicit TOFU enrollment."""

import base64
import hashlib
import socket
from typing import Any, Callable

from .enrollment import EnrollmentManager, EnrollmentResult
from .host_identity import HostIdentity
from .trust_store import TrustStore


class SSHConnectionError(RuntimeError):
    """Raised when SSH setup or host trust validation fails."""


class SSHConnector:
    """Enroll each presented host key before opening an authenticated session."""

    _CONNECTABLE = {
        EnrollmentResult.TRUST_PERMANENT,
        EnrollmentResult.TRUST_ONCE,
        EnrollmentResult.ALREADY_TRUSTED,
    }

    def __init__(
        self,
        enrollment_manager: EnrollmentManager | None = None,
        *,
        trust_store: TrustStore | None = None,
        timeout: float = 10.0,
        paramiko_module: Any | None = None,
        socket_factory: Callable[..., Any] = socket.create_connection,
    ) -> None:
        """Create a connector, optionally supplying dependencies for testing."""
        if enrollment_manager is not None and trust_store is not None:
            raise ValueError("Pass enrollment_manager or trust_store, not both.")
        self.enrollment_manager = enrollment_manager or EnrollmentManager(trust_store or TrustStore())
        self.timeout = timeout
        self._paramiko = paramiko_module
        self._socket_factory = socket_factory

    def connect(self, host: str, username: str, port: int = 22) -> Any:
        """Verify/enroll the remote key, then return an authenticated SSHClient.

        Trust-once keys are added only to this client's in-memory host-key set.
        Paramiko's RejectPolicy remains active for the authenticated handshake,
        so a key change between the preflight and session connection is rejected.
        """
        if not host.strip() or not username.strip():
            raise ValueError("host and username must not be empty.")
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535.")

        paramiko = self._get_paramiko()
        transport = None
        client = None
        try:
            sock = self._socket_factory((host, port), timeout=self.timeout)
            transport = paramiko.Transport(sock)
            transport.start_client(timeout=self.timeout)
            key = transport.get_remote_server_key()
            identity = HostIdentity(
                host=host,
                port=port,
                algorithm=key.get_name(),
                fingerprint=_sha256_fingerprint(key),
            )
        except Exception as exc:
            if transport is not None:
                transport.close()
            else:
                try:
                    sock.close()
                except (UnboundLocalError, OSError, AttributeError):
                    pass
            raise SSHConnectionError(f"Could not retrieve SSH host key for {host}:{port}: {exc}") from exc
        else:
            transport.close()

        try:
            decision = self.enrollment_manager.enroll(identity)
        except Exception as exc:
            raise SSHConnectionError(f"SSH host trust review failed for {host}:{port}: {exc}") from exc
        if decision not in self._CONNECTABLE:
            detail = (
                "Host key replacement was recorded; reconnect to verify the new key."
                if decision is EnrollmentResult.REPLACED
                else "SSH host was rejected by the trust review."
            )
            raise SSHConnectionError(detail)

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            host_key_name = host if port == 22 else f"[{host}]:{port}"
            client.get_host_keys().add(host_key_name, key.get_name(), key)
            client.connect(
                hostname=host,
                port=port,
                username=username,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
                allow_agent=True,
                look_for_keys=True,
            )
            return client
        except Exception as exc:
            if client is not None:
                client.close()
            raise SSHConnectionError(f"Could not establish SSH connection to {host}:{port}: {exc}") from exc

    def _get_paramiko(self) -> Any:
        """Load Paramiko lazily, allowing local-only installations to import."""
        if self._paramiko is None:
            try:
                import paramiko
            except ImportError as exc:
                raise SSHConnectionError("Paramiko is required for SSH connections.") from exc
            self._paramiko = paramiko
        return self._paramiko


def _sha256_fingerprint(key: Any) -> str:
    """Format an SSH public key fingerprint like OpenSSH's SHA256 form."""
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")
