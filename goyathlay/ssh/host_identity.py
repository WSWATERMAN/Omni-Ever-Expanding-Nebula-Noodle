"""Value object describing an SSH server's presented host key."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HostIdentity:
    """SSH host identity fields obtained from a future SSH handshake."""

    host: str
    port: int
    algorithm: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("Host must not be empty.")
        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")
        if not self.algorithm.strip():
            raise ValueError("Host key algorithm must not be empty.")
        if not self.fingerprint.startswith("SHA256:") or not self.fingerprint[7:]:
            raise ValueError("Fingerprint must use the SHA256: format.")
