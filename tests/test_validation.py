"""Tests for input validation and escaping — no UTM/osascript required."""

import pytest

from mcp_utm.applescript import (
    _esc,
    _parse_int,
    _validate_mac,
    _validate_path,
    _validate_timeout,
    _validate_vm_name,
    _MAX_TIMEOUT,
    _VALID_NETWORK_MODES,
    _VALID_STATUSES,
    generate_mac,
)


# ---------------------------------------------------------------------------
# _esc — AppleScript string escaping
# ---------------------------------------------------------------------------

class TestEsc:
    def test_plain_string(self):
        assert _esc("hello") == "hello"

    def test_double_quote(self):
        assert _esc('has"quote') == 'has\\"quote'

    def test_backslash(self):
        assert _esc("back\\slash") == "back\\\\slash"

    def test_both(self):
        assert _esc('a\\"b') == 'a\\\\\\"b'

    def test_empty(self):
        assert _esc("") == ""

    def test_injection_payload(self):
        payload = '" & do shell script "rm -rf /" & "'
        escaped = _esc(payload)
        assert '"' not in escaped.replace('\\"', '')


# ---------------------------------------------------------------------------
# _validate_vm_name
# ---------------------------------------------------------------------------

class TestValidateVMName:
    def test_simple_name(self):
        assert _validate_vm_name("my-vm") == "my-vm"

    def test_name_with_spaces(self):
        assert _validate_vm_name("brainbox macos template") == "brainbox macos template"

    def test_name_with_dots(self):
        assert _validate_vm_name("vm.2024.01") == "vm.2024.01"

    def test_name_with_underscores(self):
        assert _validate_vm_name("my_vm_1") == "my_vm_1"

    def test_empty_name(self):
        with pytest.raises(ValueError, match="Invalid VM name"):
            _validate_vm_name("")

    def test_quote_injection(self):
        with pytest.raises(ValueError, match="Invalid VM name"):
            _validate_vm_name('" & do shell script "id"')

    def test_ampersand(self):
        with pytest.raises(ValueError, match="Invalid VM name"):
            _validate_vm_name("vm & rm -rf /")

    def test_semicolon(self):
        with pytest.raises(ValueError, match="Invalid VM name"):
            _validate_vm_name("vm; echo pwned")

    def test_backtick(self):
        with pytest.raises(ValueError, match="Invalid VM name"):
            _validate_vm_name("vm`id`")

    def test_newline(self):
        with pytest.raises(ValueError, match="Invalid VM name"):
            _validate_vm_name("vm\ninjected")

    def test_parentheses(self):
        with pytest.raises(ValueError, match="Invalid VM name"):
            _validate_vm_name("vm()")


# ---------------------------------------------------------------------------
# _validate_mac
# ---------------------------------------------------------------------------

class TestValidateMAC:
    def test_valid_mac(self):
        assert _validate_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"

    def test_uppercase_mac(self):
        assert _validate_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"

    def test_mixed_case(self):
        assert _validate_mac("aA:bB:cC:dD:eE:fF") == "aA:bB:cC:dD:eE:fF"

    def test_too_short(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            _validate_mac("aa:bb:cc")

    def test_wrong_separator(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            _validate_mac("aa-bb-cc-dd-ee-ff")

    def test_injection_in_mac(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            _validate_mac('" & do shell script "id')

    def test_empty(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            _validate_mac("")


# ---------------------------------------------------------------------------
# _validate_path
# ---------------------------------------------------------------------------

class TestValidatePath:
    def test_absolute_path(self):
        assert _validate_path("/Users/dev/workspace") == "/Users/dev/workspace"

    def test_root(self):
        assert _validate_path("/") == "/"

    def test_relative_path(self):
        with pytest.raises(ValueError, match="must be absolute"):
            _validate_path("relative/path")

    def test_traversal(self):
        with pytest.raises(ValueError, match="traversal"):
            _validate_path("/Users/../etc/passwd")

    def test_double_dot_in_name(self):
        # "..." in a filename is fine — only ".." as a path component is blocked
        assert _validate_path("/Users/dev/file...txt") == "/Users/dev/file...txt"

    def test_empty(self):
        with pytest.raises(ValueError, match="must be absolute"):
            _validate_path("")

    def test_injection_in_path(self):
        with pytest.raises(ValueError, match="must be absolute"):
            _validate_path('" & do shell script "id')


# ---------------------------------------------------------------------------
# _validate_timeout
# ---------------------------------------------------------------------------

class TestValidateTimeout:
    def test_normal(self):
        assert _validate_timeout(60) == 60

    def test_zero_becomes_one(self):
        assert _validate_timeout(0) == 1

    def test_negative_becomes_one(self):
        assert _validate_timeout(-10) == 1

    def test_over_max_capped(self):
        assert _validate_timeout(999999) == _MAX_TIMEOUT

    def test_at_max(self):
        assert _validate_timeout(_MAX_TIMEOUT) == _MAX_TIMEOUT


# ---------------------------------------------------------------------------
# _parse_int
# ---------------------------------------------------------------------------

class TestParseInt:
    def test_integer_string(self):
        assert _parse_int("42") == 42

    def test_float_string(self):
        assert _parse_int("4096.0") == 4096

    def test_empty(self):
        assert _parse_int("") == 0

    def test_garbage(self):
        assert _parse_int("not-a-number") == 0

    def test_none(self):
        assert _parse_int(None) == 0


# ---------------------------------------------------------------------------
# generate_mac
# ---------------------------------------------------------------------------

class TestGenerateMAC:
    def test_format(self):
        mac = generate_mac()
        assert len(mac.split(":")) == 6
        _validate_mac(mac)  # should not raise

    def test_locally_administered(self):
        mac = generate_mac()
        first_octet = int(mac.split(":")[0], 16)
        assert first_octet & 0x02 == 0x02, "bit 1 (locally administered) must be set"

    def test_unicast(self):
        mac = generate_mac()
        first_octet = int(mac.split(":")[0], 16)
        assert first_octet & 0x01 == 0x00, "bit 0 (multicast) must be clear"

    def test_uniqueness(self):
        macs = {generate_mac() for _ in range(100)}
        assert len(macs) > 95, "should generate mostly unique MACs"


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------

class TestConstants:
    def test_valid_statuses_complete(self):
        for s in ("stopped", "started", "paused"):
            assert s in _VALID_STATUSES

    def test_valid_network_modes(self):
        for m in ("shared", "bridged"):
            assert m in _VALID_NETWORK_MODES
