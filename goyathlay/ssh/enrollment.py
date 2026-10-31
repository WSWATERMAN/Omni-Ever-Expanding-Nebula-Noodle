"""Explicit trust-on-first-use decisions for SSH host identities."""

from enum import Enum

from .host_identity import HostIdentity
from .trust_store import TrustStore


class EnrollmentResult(Enum):
    """Outcome of checking or enrolling an SSH host key."""

    TRUST_PERMANENT = "trust_permanent"
    TRUST_ONCE = "trust_once"
    ALREADY_TRUSTED = "already_trusted"
    REPLACED = "replaced"
    REJECT = "reject"


class EnrollmentManager:
    """Compare presented host identities and ask before trusting changes."""

    def __init__(self, trust_store: TrustStore) -> None:
        self.trust_store = trust_store

    def enroll(self, identity: HostIdentity) -> EnrollmentResult:
        """Check a host key and return the user's explicit trust decision."""
        known = self.trust_store.lookup(identity.host, identity.port)
        if known and known["fingerprint"] == identity.fingerprint:
            self.trust_store.mark_verified(identity.host, identity.port)
            return EnrollmentResult.ALREADY_TRUSTED

        if known:
            return self._review_changed(identity, known["fingerprint"])
        return self._review_unknown(identity)

    def _review_unknown(self, identity: HostIdentity) -> EnrollmentResult:
        print("-" * 40)
        print("UNKNOWN SSH HOST")
        print("-" * 40)
        print(f"Host:\n{identity.host}")
        print(f"Algorithm:\n{identity.algorithm}")
        print(f"Fingerprint:\n{identity.fingerprint}")
        print("[T] Trust Permanently")
        print("[O] One-Time Connection")
        print("[R] Reject")

        while True:
            choice = input("Selection: ").strip().casefold()
            if choice in ("t", "trust permanently"):
                self.trust_store.store(identity)
                return EnrollmentResult.TRUST_PERMANENT
            if choice in ("o", "one-time connection"):
                return EnrollmentResult.TRUST_ONCE
            if choice in ("r", "reject"):
                return EnrollmentResult.REJECT
            print("Please enter T (Trust Permanently), O (One-Time), or R (Reject).")

    def _review_changed(self, identity: HostIdentity, stored_fingerprint: str) -> EnrollmentResult:
        print("-" * 40)
        print("HOST IDENTITY CHANGED")
        print("-" * 40)
        print(f"Host:\n{identity.host}")
        print(f"Stored:\n{stored_fingerprint}")
        print(f"Current:\n{identity.fingerprint}")
        print("Possible Causes:")
        print("- Server rebuilt")
        print("- SSH reconfigured")
        print("- DNS change")
        print("- Security incident")
        print("[T] Replace Trust")
        print("[R] Reject")

        while True:
            choice = input("Selection: ").strip().casefold()
            if choice in ("t", "replace trust"):
                self.trust_store.store(identity)
                return EnrollmentResult.REPLACED
            if choice in ("r", "reject"):
                return EnrollmentResult.REJECT
            print("Please enter T (Replace Trust) or R (Reject).")
