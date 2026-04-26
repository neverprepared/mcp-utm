"""Tests for AppleScript wrapper functions — mocks osascript, no UTM required."""

from unittest.mock import patch, MagicMock
import subprocess
import pytest

from mcp_utm.applescript import (
    _run,
    list_vms,
    get_vm_status,
    get_vm_config,
    clone_vm,
    start_vm,
    stop_vm,
    delete_vm,
    suspend_vm,
    rename_vm,
    get_serial_port,
    wait_for_vm,
    get_vm_ip,
    set_vm_network,
    set_vm_resources,
    export_vm,
    import_vm,
    list_vm_drives,
    attach_drive,
    list_vm_shares,
    set_vm_shares,
    add_vm_share,
    remove_vm_share,
    set_vm_display,
    VMInfo,
    VMConfig,
    DriveInfo,
)


def _mock_run(stdout="", returncode=0, stderr=""):
    """Create a mock subprocess.run result."""
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------

class TestRun:
    @patch("mcp_utm.applescript.subprocess.run")
    def test_success(self, mock_sub):
        mock_sub.return_value = _mock_run(stdout="ok\n")
        assert _run("script") == "ok"

    @patch("mcp_utm.applescript.subprocess.run")
    def test_failure_raises(self, mock_sub):
        mock_sub.return_value = _mock_run(returncode=1, stderr="error msg")
        with pytest.raises(RuntimeError, match="error msg"):
            _run("script")

    @patch("mcp_utm.applescript.subprocess.run")
    def test_utm_not_running(self, mock_sub):
        mock_sub.return_value = _mock_run(returncode=1, stderr="Application can't be found.")
        with pytest.raises(RuntimeError, match="UTM is not running"):
            _run("script")


# ---------------------------------------------------------------------------
# list_vms
# ---------------------------------------------------------------------------

class TestListVMs:
    @patch("mcp_utm.applescript._run")
    def test_parses_output(self, mock_run):
        mock_run.return_value = "ABC-123||my-vm||stopped||apple\nDEF-456||other||started||qemu"
        vms = list_vms()
        assert len(vms) == 2
        assert vms[0] == VMInfo(id="ABC-123", name="my-vm", status="stopped", backend="apple")
        assert vms[1] == VMInfo(id="DEF-456", name="other", status="started", backend="qemu")

    @patch("mcp_utm.applescript._run")
    def test_empty_list(self, mock_run):
        mock_run.return_value = ""
        assert list_vms() == []

    @patch("mcp_utm.applescript._run")
    def test_malformed_line_skipped(self, mock_run):
        mock_run.return_value = "ABC||only-two-parts\nDEF||good||stopped||apple"
        vms = list_vms()
        assert len(vms) == 1


# ---------------------------------------------------------------------------
# get_vm_status
# ---------------------------------------------------------------------------

class TestGetVMStatus:
    @patch("mcp_utm.applescript._run")
    def test_returns_status(self, mock_run):
        mock_run.return_value = "started"
        assert get_vm_status("my-vm") == "started"
        # Verify escaping is in the script
        script = mock_run.call_args[0][0]
        assert 'virtual machine named "my-vm"' in script

    def test_rejects_bad_name(self):
        with pytest.raises(ValueError):
            get_vm_status('" & do shell script "id"')


# ---------------------------------------------------------------------------
# get_vm_config
# ---------------------------------------------------------------------------

class TestGetVMConfig:
    @patch("mcp_utm.applescript._run")
    def test_parses_full_output(self, mock_run):
        mock_run.return_value = "my-vm||8192||4||aa:bb:cc:dd:ee:ff||shared"
        config = get_vm_config("my-vm")
        assert config == VMConfig(
            name="my-vm", memory=8192, cpu_cores=4,
            mac_address="aa:bb:cc:dd:ee:ff", network_mode="shared",
        )

    @patch("mcp_utm.applescript._run")
    def test_handles_missing_fields(self, mock_run):
        mock_run.return_value = "my-vm||8192"
        config = get_vm_config("my-vm")
        assert config.name == "my-vm"
        assert config.memory == 8192
        assert config.cpu_cores == 0
        assert config.mac_address == ""

    @patch("mcp_utm.applescript._run")
    def test_handles_float_memory(self, mock_run):
        mock_run.return_value = "my-vm||4096.0||2||aa:bb:cc:dd:ee:ff||shared"
        config = get_vm_config("my-vm")
        assert config.memory == 4096


# ---------------------------------------------------------------------------
# clone_vm
# ---------------------------------------------------------------------------

class TestCloneVM:
    @patch("mcp_utm.applescript.get_vm_config")
    @patch("mcp_utm.applescript._run")
    def test_clone_with_mac(self, mock_run, mock_config):
        mock_config.return_value = VMConfig("clone", 8192, 4, "aa:bb:cc:dd:ee:ff", "shared")
        result = clone_vm("template", "clone", randomize_mac=True)
        script = mock_run.call_args[0][0]
        assert "duplicate" in script
        assert "set address of nic" in script
        assert "update configuration" in script
        assert result.name == "clone"

    @patch("mcp_utm.applescript.get_vm_config")
    @patch("mcp_utm.applescript._run")
    def test_clone_without_mac(self, mock_run, mock_config):
        mock_config.return_value = VMConfig("clone", 8192, 4, "aa:bb:cc:dd:ee:ff", "shared")
        clone_vm("template", "clone", randomize_mac=False)
        script = mock_run.call_args[0][0]
        assert "set address" not in script

    def test_rejects_bad_template_name(self):
        with pytest.raises(ValueError):
            clone_vm("bad\"name", "clone")

    def test_rejects_bad_clone_name(self):
        with pytest.raises(ValueError):
            clone_vm("template", "bad\"name")


# ---------------------------------------------------------------------------
# start / stop / delete / suspend
# ---------------------------------------------------------------------------

class TestLifecycle:
    @patch("mcp_utm.applescript._run")
    def test_start(self, mock_run):
        mock_run.return_value = "starting"
        assert start_vm("my-vm") == "starting"

    @patch("mcp_utm.applescript._run")
    def test_stop_graceful(self, mock_run):
        mock_run.return_value = "stopping"
        stop_vm("my-vm", force=False)
        assert "by force" not in mock_run.call_args[0][0]

    @patch("mcp_utm.applescript._run")
    def test_stop_force(self, mock_run):
        mock_run.return_value = "stopping"
        stop_vm("my-vm", force=True)
        assert "by force" in mock_run.call_args[0][0]

    @patch("mcp_utm.applescript._run")
    def test_delete(self, mock_run):
        assert delete_vm("my-vm") is True

    @patch("mcp_utm.applescript._run")
    def test_suspend_with_save(self, mock_run):
        mock_run.return_value = "paused"
        suspend_vm("my-vm", save=True)
        assert "with saving" in mock_run.call_args[0][0]

    @patch("mcp_utm.applescript._run")
    def test_suspend_without_save(self, mock_run):
        mock_run.return_value = "paused"
        suspend_vm("my-vm", save=False)
        assert "without saving" in mock_run.call_args[0][0]


# ---------------------------------------------------------------------------
# rename_vm
# ---------------------------------------------------------------------------

class TestRenameVM:
    @patch("mcp_utm.applescript.get_vm_config")
    @patch("mcp_utm.applescript._run")
    def test_rename(self, mock_run, mock_config):
        mock_config.return_value = VMConfig("new-name", 8192, 4, "aa:bb:cc:dd:ee:ff", "shared")
        result = rename_vm("old-name", "new-name")
        script = mock_run.call_args[0][0]
        assert 'set name of conf to "new-name"' in script
        assert result.name == "new-name"


# ---------------------------------------------------------------------------
# get_serial_port
# ---------------------------------------------------------------------------

class TestGetSerialPort:
    @patch("mcp_utm.applescript._run")
    def test_no_ports(self, mock_run):
        mock_run.return_value = "none"
        result = get_serial_port("my-vm")
        assert result == {"available": False}

    @patch("mcp_utm.applescript._run")
    def test_with_port(self, mock_run):
        mock_run.return_value = "0||ptty||/dev/ttys001||0"
        result = get_serial_port("my-vm")
        assert result["available"] is True
        assert result["interface"] == "ptty"
        assert result["address"] == "/dev/ttys001"


# ---------------------------------------------------------------------------
# wait_for_vm
# ---------------------------------------------------------------------------

class TestWaitForVM:
    @patch("mcp_utm.applescript.get_vm_status")
    def test_already_at_target(self, mock_status):
        mock_status.return_value = "started"
        assert wait_for_vm("my-vm", "started", timeout=5) == "started"

    @patch("mcp_utm.applescript.time.sleep")
    @patch("mcp_utm.applescript.time.monotonic")
    @patch("mcp_utm.applescript.get_vm_status")
    def test_reaches_target(self, mock_status, mock_time, mock_sleep):
        mock_status.side_effect = ["starting", "starting", "started"]
        mock_time.side_effect = [0, 0, 2, 2, 4, 4]
        assert wait_for_vm("my-vm", "started", timeout=10) == "started"

    @patch("mcp_utm.applescript.time.sleep")
    @patch("mcp_utm.applescript.time.monotonic")
    @patch("mcp_utm.applescript.get_vm_status")
    def test_timeout(self, mock_status, mock_time, mock_sleep):
        mock_status.return_value = "starting"
        mock_time.side_effect = [0, 0, 5, 5, 11]
        with pytest.raises(TimeoutError, match="did not reach"):
            wait_for_vm("my-vm", "started", timeout=10)

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid target_status"):
            wait_for_vm("my-vm", "running")


# ---------------------------------------------------------------------------
# get_vm_ip
# ---------------------------------------------------------------------------

class TestGetVMIP:
    @patch("mcp_utm.applescript.subprocess.run")
    @patch("mcp_utm.applescript.get_vm_config")
    def test_finds_ip(self, mock_config, mock_sub):
        mock_config.return_value = VMConfig("vm", 8192, 4, "aa:bb:cc:dd:ee:ff", "shared")
        mock_sub.return_value = _mock_run(
            stdout="? (192.168.64.5) at aa:bb:cc:dd:ee:ff on bridge100 ifscope [bridge]\n"
        )
        ip, mac = get_vm_ip("vm", timeout=5)
        assert ip == "192.168.64.5"
        assert mac == "aa:bb:cc:dd:ee:ff"

    @patch("mcp_utm.applescript.subprocess.run")
    @patch("mcp_utm.applescript.get_vm_config")
    def test_finds_ip_stripped_zeros(self, mock_config, mock_sub):
        mock_config.return_value = VMConfig("vm", 8192, 4, "0a:0b:0c:0d:0e:0f", "shared")
        mock_sub.return_value = _mock_run(
            stdout="? (192.168.64.5) at a:b:c:d:e:f on bridge100 ifscope [bridge]\n"
        )
        ip, mac = get_vm_ip("vm", timeout=5)
        assert ip == "192.168.64.5"

    @patch("mcp_utm.applescript.get_vm_config")
    def test_no_mac(self, mock_config):
        mock_config.return_value = VMConfig("vm", 8192, 4, "", "shared")
        with pytest.raises(RuntimeError, match="No MAC"):
            get_vm_ip("vm", timeout=5)


# ---------------------------------------------------------------------------
# set_vm_network
# ---------------------------------------------------------------------------

class TestSetVMNetwork:
    @patch("mcp_utm.applescript.get_vm_config")
    @patch("mcp_utm.applescript._run")
    def test_set_mac(self, mock_run, mock_config):
        mock_config.return_value = VMConfig("vm", 8192, 4, "11:22:33:44:55:66", "shared")
        set_vm_network("vm", mac_address="11:22:33:44:55:66")
        script = mock_run.call_args[0][0]
        assert 'set address of nic to "11:22:33:44:55:66"' in script

    def test_rejects_bad_mac(self):
        with pytest.raises(ValueError, match="Invalid MAC"):
            set_vm_network("vm", mac_address="not-a-mac")

    def test_rejects_bad_mode(self):
        with pytest.raises(ValueError, match="Invalid network mode"):
            set_vm_network("vm", mode="hacked")

    @patch("mcp_utm.applescript.get_vm_config")
    def test_no_changes(self, mock_config):
        mock_config.return_value = VMConfig("vm", 8192, 4, "aa:bb:cc:dd:ee:ff", "shared")
        result = set_vm_network("vm")
        assert result.name == "vm"


# ---------------------------------------------------------------------------
# set_vm_resources
# ---------------------------------------------------------------------------

class TestSetVMResources:
    def test_memory_too_low(self):
        with pytest.raises(ValueError, match="Memory must be"):
            set_vm_resources("vm", memory=32)

    def test_memory_too_high(self):
        with pytest.raises(ValueError, match="Memory must be"):
            set_vm_resources("vm", memory=2_000_000)

    def test_cores_too_low(self):
        with pytest.raises(ValueError, match="CPU cores must be"):
            set_vm_resources("vm", cpu_cores=0)

    def test_cores_too_high(self):
        with pytest.raises(ValueError, match="CPU cores must be"):
            set_vm_resources("vm", cpu_cores=512)

    @patch("mcp_utm.applescript.get_vm_config")
    @patch("mcp_utm.applescript._run")
    def test_valid_resources(self, mock_run, mock_config):
        mock_config.return_value = VMConfig("vm", 16384, 8, "aa:bb:cc:dd:ee:ff", "shared")
        result = set_vm_resources("vm", memory=16384, cpu_cores=8)
        assert result.memory == 16384


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------

class TestExportImport:
    @patch("mcp_utm.applescript._run")
    def test_export(self, mock_run):
        assert export_vm("my-vm", "/tmp/export.utm") is True

    def test_export_bad_path(self):
        with pytest.raises(ValueError, match="must be absolute"):
            export_vm("my-vm", "relative/path.utm")

    def test_export_traversal(self):
        with pytest.raises(ValueError, match="traversal"):
            export_vm("my-vm", "/tmp/../etc/export.utm")

    @patch("mcp_utm.applescript._run")
    def test_import(self, mock_run):
        mock_run.return_value = "ABC||imported-vm||stopped||apple"
        vm = import_vm("/tmp/import.utm")
        assert vm.name == "imported-vm"

    @patch("mcp_utm.applescript._run")
    def test_import_malformed(self, mock_run):
        mock_run.return_value = "bad"
        with pytest.raises(RuntimeError, match="Unexpected import"):
            import_vm("/tmp/import.utm")


# ---------------------------------------------------------------------------
# drives
# ---------------------------------------------------------------------------

class TestDrives:
    @patch("mcp_utm.applescript._run")
    def test_list_drives(self, mock_run):
        mock_run.return_value = "DRIVE-1||true||1024\nDRIVE-2||false||51200"
        drives = list_vm_drives("my-vm")
        assert len(drives) == 2
        assert drives[0] == DriveInfo(id="DRIVE-1", removable=True, host_size_mib=1024)
        assert drives[1] == DriveInfo(id="DRIVE-2", removable=False, host_size_mib=51200)

    @patch("mcp_utm.applescript._run")
    def test_attach_drive(self, mock_run):
        assert attach_drive("my-vm", "DRIVE-1", "/tmp/boot.iso") is True
        script = mock_run.call_args[0][0]
        assert "set source of d" in script
        assert "update configuration" in script

    def test_attach_bad_path(self):
        with pytest.raises(ValueError, match="must be absolute"):
            attach_drive("my-vm", "DRIVE-1", "relative.iso")


# ---------------------------------------------------------------------------
# shares
# ---------------------------------------------------------------------------

class TestShares:
    @patch("mcp_utm.applescript._run")
    def test_list_shares(self, mock_run):
        mock_run.return_value = "/Users/dev/.ssh/\n/tmp\n"
        shares = list_vm_shares("my-vm")
        assert shares == ["/Users/dev/.ssh/", "/tmp"]

    @patch("mcp_utm.applescript._run")
    def test_list_shares_empty(self, mock_run):
        mock_run.return_value = ""
        assert list_vm_shares("my-vm") == []

    @patch("mcp_utm.applescript.list_vm_shares")
    @patch("mcp_utm.applescript.set_vm_shares")
    def test_add_share_new(self, mock_set, mock_list):
        mock_list.return_value = ["/existing/"]
        mock_set.return_value = ["/existing/", "/new/path"]
        result = add_vm_share("my-vm", "/new/path")
        assert "/new/path" in result

    @patch("mcp_utm.applescript.list_vm_shares")
    def test_add_share_dedup(self, mock_list):
        mock_list.return_value = ["/existing/"]
        result = add_vm_share("my-vm", "/existing")
        assert result == ["/existing/"]

    @patch("mcp_utm.applescript.list_vm_shares")
    @patch("mcp_utm.applescript.set_vm_shares")
    def test_remove_share(self, mock_set, mock_list):
        mock_list.return_value = ["/Users/dev/.ssh/", "/tmp/"]
        mock_set.return_value = ["/Users/dev/.ssh/"]
        result = remove_vm_share("my-vm", "/tmp")
        mock_set.assert_called_once()

    @patch("mcp_utm.applescript.list_vm_shares")
    def test_remove_nonexistent(self, mock_list):
        mock_list.return_value = ["/existing/"]
        result = remove_vm_share("my-vm", "/not-there")
        assert result == ["/existing/"]

    def test_set_shares_bad_path(self):
        with pytest.raises(ValueError, match="must be absolute"):
            set_vm_shares("my-vm", ["relative/path"])


# ---------------------------------------------------------------------------
# display
# ---------------------------------------------------------------------------

class TestDisplay:
    @patch("mcp_utm.applescript._run")
    def test_enable_dynamic(self, mock_run):
        set_vm_display("my-vm", True)
        assert "true" in mock_run.call_args[0][0]

    @patch("mcp_utm.applescript._run")
    def test_disable_dynamic(self, mock_run):
        set_vm_display("my-vm", False)
        assert "false" in mock_run.call_args[0][0]
