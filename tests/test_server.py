"""Tests for the MCP server tool layer."""

from unittest.mock import patch
import pytest

from mcp_utm.server import mcp
from mcp_utm.applescript import VMInfo, VMConfig, DriveInfo


class TestToolsRegistered:
    def test_tool_count(self):
        tools = mcp._tool_manager.list_tools()
        assert len(tools) == 22

    def test_expected_tools(self):
        names = {t.name for t in mcp._tool_manager.list_tools()}
        expected = {
            "list_vms", "get_vm", "clone_vm", "start_vm", "stop_vm", "delete_vm",
            "suspend_vm", "wait_for_vm", "get_vm_ip", "set_vm_network",
            "set_vm_resources", "rename_vm", "set_vm_display", "list_vm_shares",
            "add_vm_share", "remove_vm_share", "set_vm_shares", "list_vm_drives",
            "attach_drive", "export_vm", "import_vm", "get_serial_port",
        }
        assert expected == names
