"""MCP server exposing UTM virtual machine management via AppleScript.

Tools for listing, cloning, configuring, and controlling UTM VMs.
Provides proper MAC address randomization for Apple VF clones via
the AppleScript ``update configuration`` API.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import applescript as utm

mcp = FastMCP("utm")


@mcp.tool()
def list_vms() -> list[dict]:
    """List all registered UTM virtual machines with their status."""
    return [vm.to_dict() for vm in utm.list_vms()]


@mcp.tool()
def get_vm(name: str) -> dict:
    """Get status and configuration of a VM by name."""
    status = utm.get_vm_status(name)
    config = utm.get_vm_config(name)
    return {"status": status, **config.to_dict()}


@mcp.tool()
def clone_vm(
    template: str,
    name: str,
    randomize_mac: bool = True,
) -> dict:
    """Clone a UTM template VM with a unique random MAC address.

    Args:
        template: Name of the template VM to clone
        name: Name for the new VM
        randomize_mac: Assign a random MAC so clones get unique IPs (default: True)
    """
    config = utm.clone_vm(template, name, randomize_mac=randomize_mac)
    return {"cloned": True, **config.to_dict()}


@mcp.tool()
def start_vm(name: str) -> dict:
    """Start a stopped or suspended VM."""
    status = utm.start_vm(name)
    return {"name": name, "status": status}


@mcp.tool()
def stop_vm(name: str, force: bool = False) -> dict:
    """Stop a running VM.

    Args:
        name: VM name
        force: Force stop if graceful shutdown fails
    """
    status = utm.stop_vm(name, force=force)
    return {"name": name, "status": status}


@mcp.tool()
def delete_vm(name: str) -> dict:
    """Delete a VM permanently. Cannot be undone."""
    utm.delete_vm(name)
    return {"name": name, "deleted": True}


@mcp.tool()
def get_vm_ip(name: str, timeout: int = 60) -> dict:
    """Discover the IP address of a running VM via ARP.

    Polls the ARP table for the VM's MAC address. Works for Apple VF
    (macOS) VMs on the 192.168.64.0/24 subnet and bridged QEMU VMs.

    Args:
        name: VM name
        timeout: Seconds to wait for ARP discovery (default: 60)
    """
    ip, mac = utm.get_vm_ip(name, timeout=timeout)
    return {"name": name, "ip": ip, "mac_address": mac}


@mcp.tool()
def set_vm_network(
    name: str,
    mac_address: str | None = None,
    mode: str | None = None,
) -> dict:
    """Update network configuration of a stopped VM.

    Args:
        name: VM name (must be stopped)
        mac_address: New MAC address (e.g. "aa:bb:cc:dd:ee:ff"), or None to keep current
        mode: Network mode ("shared" or "bridged"), or None to keep current
    """
    config = utm.set_vm_network(name, mac_address=mac_address, mode=mode)
    return config.to_dict()


@mcp.tool()
def set_vm_resources(
    name: str,
    memory: int | None = None,
    cpu_cores: int | None = None,
) -> dict:
    """Update memory and CPU cores of a stopped VM.

    Args:
        name: VM name (must be stopped)
        memory: Memory in MiB, or None to keep current
        cpu_cores: Number of CPU cores, or None to keep current
    """
    config = utm.set_vm_resources(name, memory=memory, cpu_cores=cpu_cores)
    return config.to_dict()


@mcp.tool()
def suspend_vm(name: str, save: bool = True) -> dict:
    """Suspend a running VM to memory.

    Args:
        name: VM name (must be running)
        save: Save VM state to disk for later resume (default: True)
    """
    status = utm.suspend_vm(name, save=save)
    return {"name": name, "status": status}


@mcp.tool()
def rename_vm(name: str, new_name: str) -> dict:
    """Rename a stopped VM.

    Args:
        name: Current VM name (must be stopped)
        new_name: New name for the VM
    """
    config = utm.rename_vm(name, new_name)
    return config.to_dict()


@mcp.tool()
def get_serial_port(name: str) -> dict:
    """Get the serial port address of a VM.

    Returns the ptty path (for Apple VF) or TCP address/port (for QEMU)
    that can be used for direct console access without SSH.

    Args:
        name: VM name
    """
    return utm.get_serial_port(name)


@mcp.tool()
def wait_for_vm(name: str, target_status: str = "started", timeout: int = 120) -> dict:
    """Wait until a VM reaches a target status.

    Useful for orchestration — start a VM then wait for it to be ready.

    Args:
        name: VM name
        target_status: Status to wait for: "stopped", "started", or "paused"
        timeout: Seconds to wait (default: 120)
    """
    status = utm.wait_for_vm(name, target_status=target_status, timeout=timeout)
    return {"name": name, "status": status}


@mcp.tool()
def export_vm(name: str, path: str) -> dict:
    """Export a VM to a .utm file.

    Args:
        name: VM name
        path: Destination file path (e.g. "/tmp/my-vm.utm")
    """
    utm.export_vm(name, path)
    return {"name": name, "exported_to": path}


@mcp.tool()
def import_vm(path: str) -> dict:
    """Import a VM from a .utm file.

    Args:
        path: Path to the .utm file to import
    """
    vm = utm.import_vm(path)
    return vm.to_dict()


@mcp.tool()
def list_vm_drives(name: str) -> list[dict]:
    """List drives attached to a VM with their IDs and sizes.

    Args:
        name: VM name
    """
    return [d.to_dict() for d in utm.list_vm_drives(name)]


@mcp.tool()
def attach_drive(name: str, drive_id: str, source_path: str) -> dict:
    """Attach an ISO or disk image to a removable drive.

    Args:
        name: VM name (must be stopped)
        drive_id: Drive ID (from list_vm_drives)
        source_path: Path to ISO or disk image file
    """
    utm.attach_drive(name, drive_id, source_path)
    return {"name": name, "drive_id": drive_id, "source": source_path}


@mcp.tool()
def list_vm_shares(name: str) -> dict:
    """List shared directories (VirtioFS) registered for a VM.

    Args:
        name: VM name
    """
    shares = utm.list_vm_shares(name)
    return {"name": name, "shares": shares}


@mcp.tool()
def add_vm_share(name: str, path: str) -> dict:
    """Add a host directory as a VirtioFS share on a VM.

    Creates a security-scoped bookmark so the share persists across boots
    and works with Apple VF clones. The directory appears inside the guest
    at /Volumes/My Shared Files/<folder-name>.

    Args:
        name: VM name (must be stopped)
        path: Host directory path to share (e.g. "/Users/you/project")
    """
    shares = utm.add_vm_share(name, path)
    return {"name": name, "shares": shares}


@mcp.tool()
def remove_vm_share(name: str, path: str) -> dict:
    """Remove a shared directory from a VM.

    Args:
        name: VM name (must be stopped)
        path: Host directory path to remove
    """
    shares = utm.remove_vm_share(name, path)
    return {"name": name, "shares": shares}


@mcp.tool()
def set_vm_shares(name: str, paths: list[str]) -> dict:
    """Replace all shared directories on a VM.

    Overwrites the entire share list. Use add_vm_share/remove_vm_share
    for incremental changes.

    Args:
        name: VM name (must be stopped)
        paths: List of host directory paths to share (empty list clears all)
    """
    shares = utm.set_vm_shares(name, paths)
    return {"name": name, "shares": shares}


@mcp.tool()
def set_vm_display(name: str, dynamic_resolution: bool) -> dict:
    """Toggle dynamic resolution on the VM display.

    Args:
        name: VM name (must be stopped)
        dynamic_resolution: Enable or disable dynamic resolution
    """
    utm.set_vm_display(name, dynamic_resolution)
    return {"name": name, "dynamic_resolution": dynamic_resolution}
