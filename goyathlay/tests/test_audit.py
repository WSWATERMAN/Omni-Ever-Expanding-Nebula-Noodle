import json
import tempfile
import unittest
from pathlib import Path

from goyathlay.audit import AuditRecord, AuditStore


class AuditStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "audit.jsonl"
        self.store = AuditStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def make_record(intent, command, return_code=0, success=True, host=None):
        return AuditRecord(
            timestamp="2026-10-31T18:00:00Z",
            intent=intent,
            command=command,
            risk_level="LOW",
            approval_result="approved",
            return_code=return_code,
            success=success,
            host=host,
        )

    def test_creates_audit_store_with_owner_only_permissions(self):
        self.assertTrue(self.path.exists())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_append_and_reload_one_record(self):
        record = self.make_record("show listening ports", "netstat -tuln")

        self.store.append(record)

        self.assertEqual(self.store.load(), [record])

    def test_multiple_appends_preserve_record_order(self):
        first = self.make_record("first", "pwd")
        second = self.make_record("second", "ls -la")

        self.store.append(first)
        self.store.append(second)

        self.assertEqual(self.store.load(), [first, second])
        self.assertEqual(len(self.path.read_text().splitlines()), 2)

    def test_load_skips_malformed_lines_and_continues(self):
        first = self.make_record("first", "pwd")
        second = self.make_record("second", "ls -la")
        self.store.append(first)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write("not json\n")
            stream.write(json.dumps({"timestamp": "missing fields"}) + "\n")
        self.store.append(second)

        self.assertEqual(self.store.load(), [first, second])

    def test_load_skips_invalid_utf8_and_continues(self):
        first = self.make_record("first", "pwd")
        second = self.make_record("second", "ls -la")
        self.store.append(first)
        with self.path.open("ab") as stream:
            stream.write(b"\xff\xfe\n")
        self.store.append(second)

        self.assertEqual(self.store.load(), [first, second])

    def test_append_is_jsonl_and_preserves_history(self):
        records = [self.make_record(str(index), "echo test") for index in range(3)]
        for record in records:
            self.store.append(record)

        lines = self.path.read_text().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(line)["intent"] for line in lines], ["0", "1", "2"])

    def test_host_is_persisted_and_loaded(self):
        record = self.make_record("remote task", "ss -tulpn", host="web01")

        self.store.append(record)

        self.assertEqual(self.store.load(), [record])
        self.assertEqual(json.loads(self.path.read_text())['host'], "web01")

    def test_legacy_records_without_host_remain_loadable(self):
        legacy = {
            "timestamp": "2026-10-31T18:00:00Z",
            "intent": "local task",
            "command": "pwd",
            "risk_level": "LOW",
            "approval_result": "approved",
            "return_code": 0,
            "success": True,
        }
        self.path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

        records = self.store.load()

        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].host)


if __name__ == "__main__":
    unittest.main()
