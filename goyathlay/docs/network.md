# Network device support

## Available modules

- Cisco IOS: fixed translations for interface status, version, inventory, BGP summary, routes, spanning tree, and running configuration. `show` commands classify LOW; configuration and unknown commands classify HIGH.
- Aruba AOS-CX: fixed read-only `show` command translations. Unknown/non-show commands classify HIGH.
- Meraki: maps four status intents to fixed HTTP GET endpoint descriptions.

These are translation modules, not device clients. Cisco and Aruba have no SSH execution integration in the current CLI. Meraki makes no HTTP calls and handles no API key. The Meraki service itself is cloud-hosted; using a future API client will require network connectivity and is distinct from local-only AI inference.

Existing SSH operations use host inventory and TOFU trust enrollment. Unknown fingerprints require an explicit trust-once, trust-permanently, or reject decision. A changed fingerprint is surfaced and never silently accepted. For multi-host operations, host enrollment is serial to keep prompts unambiguous; approved command execution is concurrent and audited per host.

Do not add configuration writes without command-specific risk policy, final-command validation, explicit approval, and audit coverage.
