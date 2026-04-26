"""AppleScript interface to UTM.

Wraps osascript calls to the UTM scripting API. All functions raise
``RuntimeError`` on AppleScript execution failures.
"""

from __future__ import annotations

import json
import random
import subprocess
from dataclasses import dataclass


def _run(script: str, timeout: int = 30) -> str:
    """Execute an AppleScript snippet and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"osascript failed (rc={result.returncode})")
    return result.stdout.strip()


def _run_json(script: str, timeout: int = 30) -> dict | list:
    """Execute AppleScript that prints JSON and parse the result."""
    # Wrap in a JXA (JavaScript for Automation) call for clean JSON output
    raw = _run(script, timeout=timeout)
    return json.loads(raw) if raw else {}


def generate_mac() -> str:
    """Generate a random locally-administered unicast MAC address."""
    octets = [random.randint(0, 255) for _ in range(6)]
    octets[0] = (octets[0] & 0xFC) | 0x02  # locally administered, unicast
    return ":".join(f"{b:02x}" for b in octets)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class VMInfo:
    id: str
    name: str
    status: str
    backend: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "status": self.status, "backend": self.backend}


@dataclass
class VMConfig:
    name: str
    memory: int  # MiB
    cpu_cores: int
    mac_address: str
    network_mode: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "memory": self.memory,
            "cpu_cores": self.cpu_cores,
            "mac_address": self.mac_address,
            "network_mode": self.network_mode,
        }


# ---------------------------------------------------------------------------
# VM listing and status
# ---------------------------------------------------------------------------

def list_vms() -> list[VMInfo]:
    """List all registered UTM virtual machines."""
    script = '''
    tell application "UTM"
        set output to ""
        repeat with vm in virtual machines
            set vmId to id of vm
            set vmName to name of vm
            set vmStatus to status of vm as text
            set vmBackend to backend of vm as text
            set output to output & vmId & "||" & vmName & "||" & vmStatus & "||" & vmBackend & linefeed
        end repeat
        return output
    end tell
    '''
    raw = _run(script)
    vms = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("||")
        if len(parts) >= 4:
            vms.append(VMInfo(id=parts[0], name=parts[1], status=parts[2], backend=parts[3]))
    return vms


def get_vm_status(name: str) -> str:
    """Get the status of a VM by name."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        return status of vm as text
    end tell
    '''
    return _run(script)


def get_vm_config(name: str) -> VMConfig:
    """Read configuration of a VM."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set conf to configuration of vm
        set vmName to name of conf
        set vmMem to memory of conf
        set vmCores to cpu cores of conf
        set nics to network interfaces of conf
        if (count of nics) > 0 then
            set nic to item 1 of nics
            set macAddr to address of nic
            set netMode to mode of nic as text
        else
            set macAddr to ""
            set netMode to ""
        end if
        return vmName & "||" & vmMem & "||" & vmCores & "||" & macAddr & "||" & netMode
    end tell
    '''
    raw = _run(script)
    parts = raw.split("||")
    return VMConfig(
        name=parts[0],
        memory=int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
        cpu_cores=int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
        mac_address=parts[3] if len(parts) > 3 else "",
        network_mode=parts[4] if len(parts) > 4 else "",
    )


# ---------------------------------------------------------------------------
# VM lifecycle
# ---------------------------------------------------------------------------

def clone_vm(template_name: str, new_name: str, randomize_mac: bool = True) -> VMConfig:
    """Clone a VM, optionally assigning a random MAC address.

    Uses AppleScript ``duplicate`` + ``update configuration`` so UTM's
    in-memory state is updated (unlike raw plist edits).
    """
    new_mac = generate_mac() if randomize_mac else ""

    # Step 1: duplicate and set name + MAC in one shot
    if new_mac:
        script = f'''
        tell application "UTM"
            set tmpl to virtual machine named "{template_name}"
            duplicate tmpl with properties {{configuration:{{name:"{new_name}"}}}}
            set vm to virtual machine named "{new_name}"
            set conf to configuration of vm
            set nic to item 1 of (network interfaces of conf)
            set address of nic to "{new_mac}"
            update configuration of vm with conf
        end tell
        '''
    else:
        script = f'''
        tell application "UTM"
            set tmpl to virtual machine named "{template_name}"
            duplicate tmpl with properties {{configuration:{{name:"{new_name}"}}}}
        end tell
        '''
    _run(script, timeout=600)

    return get_vm_config(new_name)


def start_vm(name: str) -> str:
    """Start a VM. Returns status after start command."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        start vm
        return status of vm as text
    end tell
    '''
    return _run(script, timeout=60)


def stop_vm(name: str, force: bool = False) -> str:
    """Stop a VM. Returns status after stop command."""
    method = "by force" if force else ""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        stop vm {method}
        return status of vm as text
    end tell
    '''
    return _run(script, timeout=60)


def delete_vm(name: str) -> bool:
    """Delete a VM. Returns True on success."""
    script = f'''
    tell application "UTM"
        delete virtual machine named "{name}"
    end tell
    '''
    _run(script, timeout=60)
    return True


# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

def get_vm_ip(name: str, timeout: int = 60) -> str:
    """Discover VM IP via ARP table by reading its MAC from UTM config.

    Polls ARP every 2 seconds until the MAC appears or timeout is reached.
    """
    config = get_vm_config(name)
    mac = config.mac_address.lower()
    if not mac:
        raise RuntimeError(f"No MAC address found for VM '{name}'")

    # ARP output may strip leading zeros from MAC octets (e.g. 0e → e).
    # Build a normalized form for matching.
    mac_stripped = ":".join(p.lstrip("0") or "0" for p in mac.split(":"))

    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
        for line in result.stdout.split("\n"):
            line_lower = line.lower()
            if mac in line_lower or mac_stripped in line_lower:
                # Parse IP from "? (192.168.64.x) at aa:bb:cc:dd:ee:ff ..."
                start = line.find("(")
                end = line.find(")")
                if start != -1 and end != -1:
                    return line[start + 1 : end]
        time.sleep(2)

    raise TimeoutError(f"IP not found for VM '{name}' (MAC: {mac}) after {timeout}s")


def set_vm_network(name: str, mac_address: str | None = None, mode: str | None = None) -> VMConfig:
    """Update network configuration of a stopped VM."""
    parts = []
    if mac_address:
        parts.append(f'set address of nic to "{mac_address}"')
    if mode:
        parts.append(f'set mode of nic to {mode}')
    if not parts:
        return get_vm_config(name)

    updates = "\n            ".join(parts)
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set conf to configuration of vm
        set nic to item 1 of (network interfaces of conf)
        {updates}
        update configuration of vm with conf
    end tell
    '''
    _run(script)
    return get_vm_config(name)


def set_vm_resources(name: str, memory: int | None = None, cpu_cores: int | None = None) -> VMConfig:
    """Update memory and/or CPU cores of a stopped VM."""
    parts = []
    if memory is not None:
        parts.append(f"set memory of conf to {memory}")
    if cpu_cores is not None:
        parts.append(f"set cpu cores of conf to {cpu_cores}")
    if not parts:
        return get_vm_config(name)

    updates = "\n            ".join(parts)
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set conf to configuration of vm
        {updates}
        update configuration of vm with conf
    end tell
    '''
    _run(script)
    return get_vm_config(name)


# ---------------------------------------------------------------------------
# Suspend / Resume
# ---------------------------------------------------------------------------

def suspend_vm(name: str, save: bool = True) -> str:
    """Suspend a running VM to memory. Optionally save state to disk."""
    saving = "with saving" if save else "without saving"
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        suspend vm {saving}
        return status of vm as text
    end tell
    '''
    return _run(script, timeout=60)


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def rename_vm(name: str, new_name: str) -> VMConfig:
    """Rename a stopped VM via update configuration."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set conf to configuration of vm
        set name of conf to "{new_name}"
        update configuration of vm with conf
    end tell
    '''
    _run(script)
    return get_vm_config(new_name)


# ---------------------------------------------------------------------------
# Serial port
# ---------------------------------------------------------------------------

def get_serial_port(name: str) -> dict:
    """Get the first serial port's interface and address (ptty path or TCP info)."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set ports to serial ports of vm
        if (count of ports) > 0 then
            set p to item 1 of ports
            set pId to id of p
            set pIface to interface of p as text
            set pAddr to address of p
            set pPort to port of p
            return pId & "||" & pIface & "||" & pAddr & "||" & pPort
        else
            return "none"
        end if
    end tell
    '''
    raw = _run(script)
    if raw == "none":
        return {"available": False}
    parts = raw.split("||")
    return {
        "available": True,
        "id": int(parts[0]) if parts[0].isdigit() else 0,
        "interface": parts[1] if len(parts) > 1 else "",
        "address": parts[2] if len(parts) > 2 else "",
        "port": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
    }


# ---------------------------------------------------------------------------
# Wait for status
# ---------------------------------------------------------------------------

def wait_for_vm(name: str, target_status: str = "started", timeout: int = 120) -> str:
    """Poll VM status until it matches target or timeout is reached.

    Args:
        name: VM name
        target_status: One of "stopped", "started", "paused"
        timeout: Seconds to wait
    """
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = get_vm_status(name)
        if status == target_status:
            return status
        time.sleep(2)
    raise TimeoutError(f"VM '{name}' did not reach '{target_status}' within {timeout}s (current: {status})")


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

def export_vm(name: str, path: str) -> bool:
    """Export a VM to a .utm file at the given path."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set dest to POSIX file "{path}"
        export vm to dest
    end tell
    '''
    _run(script, timeout=600)
    return True


def import_vm(path: str) -> VMInfo:
    """Import a VM from a .utm file. Returns the imported VM info."""
    script = f'''
    tell application "UTM"
        set src to POSIX file "{path}"
        set vm to import new virtual machine from src
        set vmId to id of vm
        set vmName to name of vm
        set vmStatus to status of vm as text
        set vmBackend to backend of vm as text
        return vmId & "||" & vmName & "||" & vmStatus & "||" & vmBackend
    end tell
    '''
    raw = _run(script, timeout=600)
    parts = raw.split("||")
    return VMInfo(id=parts[0], name=parts[1], status=parts[2], backend=parts[3])


# ---------------------------------------------------------------------------
# Drives
# ---------------------------------------------------------------------------

@dataclass
class DriveInfo:
    id: str
    removable: bool
    host_size_mib: int

    def to_dict(self) -> dict:
        return {"id": self.id, "removable": self.removable, "host_size_mib": self.host_size_mib}


def list_vm_drives(name: str) -> list[DriveInfo]:
    """List drives attached to a VM."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set conf to configuration of vm
        set drvs to drives of conf
        set output to ""
        repeat with d in drvs
            set dId to id of d
            set dRemovable to removable of d
            set dSize to host size of d
            set output to output & dId & "||" & dRemovable & "||" & dSize & linefeed
        end repeat
        return output
    end tell
    '''
    raw = _run(script)
    drives = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("||")
        if len(parts) >= 3:
            drives.append(DriveInfo(
                id=parts[0],
                removable=parts[1].lower() == "true",
                host_size_mib=int(parts[2]) if parts[2].isdigit() else 0,
            ))
    return drives


def attach_drive(name: str, drive_id: str, source_path: str) -> bool:
    """Attach an ISO or disk image to a removable drive on a stopped VM.

    Args:
        name: VM name (must be stopped)
        drive_id: Drive ID (from list_vm_drives)
        source_path: Path to ISO or disk image
    """
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set conf to configuration of vm
        set drvs to drives of conf
        repeat with d in drvs
            if id of d is "{drive_id}" then
                set item 1 of (drvs whose id is "{drive_id}") to {{id:"{drive_id}", source:POSIX file "{source_path}"}}
                exit repeat
            end if
        end repeat
        update configuration of vm with conf
    end tell
    '''
    _run(script)
    return True


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Directory shares (VirtioFS)
# ---------------------------------------------------------------------------

def list_vm_shares(name: str) -> list[str]:
    """List shared directories registered for a VM. Returns POSIX paths."""
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set shares to registry of vm
        set output to ""
        repeat with s in shares
            set output to output & (POSIX path of s) & linefeed
        end repeat
        return output
    end tell
    '''
    raw = _run(script)
    return [p.strip() for p in raw.strip().split("\n") if p.strip()]


def set_vm_shares(name: str, paths: list[str]) -> list[str]:
    """Replace all shared directories for a VM.

    Uses ``update registry`` which creates security-scoped bookmarks,
    allowing VirtioFS mounts to survive across boots.

    Args:
        name: VM name (must be stopped)
        paths: List of host POSIX paths to share
    """
    if not paths:
        script = f'''
        tell application "UTM"
            set vm to virtual machine named "{name}"
            update registry of vm with {{}}
        end tell
        '''
    else:
        share_items = ", ".join(f'POSIX file "{p}"' for p in paths)
        script = f'''
        tell application "UTM"
            set vm to virtual machine named "{name}"
            update registry of vm with {{{share_items}}}
        end tell
        '''
    _run(script)
    return list_vm_shares(name)


def add_vm_share(name: str, path: str) -> list[str]:
    """Add a shared directory to a VM without removing existing shares.

    Args:
        name: VM name (must be stopped)
        path: Host POSIX path to share
    """
    current = list_vm_shares(name)
    # Normalize trailing slashes for dedup
    normalized = path.rstrip("/")
    existing = [p.rstrip("/") for p in current]
    if normalized in existing:
        return current
    current.append(path)
    return set_vm_shares(name, current)


def remove_vm_share(name: str, path: str) -> list[str]:
    """Remove a shared directory from a VM.

    Args:
        name: VM name (must be stopped)
        path: Host POSIX path to remove
    """
    current = list_vm_shares(name)
    normalized = path.rstrip("/")
    updated = [p for p in current if p.rstrip("/") != normalized]
    if len(updated) == len(current):
        return current  # nothing to remove
    return set_vm_shares(name, updated)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def set_vm_display(name: str, dynamic_resolution: bool) -> bool:
    """Toggle dynamic resolution on the first display of a stopped VM."""
    val = "true" if dynamic_resolution else "false"
    script = f'''
    tell application "UTM"
        set vm to virtual machine named "{name}"
        set conf to configuration of vm
        set disps to displays of conf
        if (count of disps) > 0 then
            set dynamic resolution of item 1 of disps to {val}
            update configuration of vm with conf
        end if
    end tell
    '''
    _run(script)
    return True
