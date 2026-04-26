# mcp-utm

MCP server for managing [UTM](https://mac.getutm.app/) virtual machines on macOS via AppleScript.

Provides 22 tools for cloning, configuring, and controlling UTM VMs — including proper MAC address randomization for Apple Virtualization Framework clones, which enables concurrent VMs with unique network identities.

## Install

```bash
# PyPI
uvx mcp-utm

# Or install globally
uv tool install mcp-utm
pip install mcp-utm
```

## Claude Code config

```json
{
  "mcpServers": {
    "utm": {
      "command": "uvx",
      "args": ["mcp-utm"]
    }
  }
}
```

## Requirements

- **macOS** (uses AppleScript / `osascript`)
- **UTM 4.6+** ([download](https://mac.getutm.app/) or `brew install --cask utm`)
- **Python 3.11+**

## Tools

### Lifecycle
| Tool | Description |
|------|-------------|
| `list_vms` | List all registered VMs with status |
| `get_vm` | Get status and configuration of a VM |
| `clone_vm` | Clone a template with unique random MAC |
| `start_vm` | Start a stopped or suspended VM |
| `stop_vm` | Stop a running VM (graceful or force) |
| `delete_vm` | Delete a VM permanently |

### State
| Tool | Description |
|------|-------------|
| `suspend_vm` | Suspend a running VM to memory |
| `wait_for_vm` | Poll until VM reaches a target status |

### Networking
| Tool | Description |
|------|-------------|
| `get_vm_ip` | Discover VM IP via ARP table |
| `set_vm_network` | Update MAC address or network mode |

### Configuration
| Tool | Description |
|------|-------------|
| `set_vm_resources` | Update memory and CPU cores |
| `rename_vm` | Rename a VM |
| `set_vm_display` | Toggle dynamic resolution |

### Directory Shares (VirtioFS)
| Tool | Description |
|------|-------------|
| `list_vm_shares` | List shared directories |
| `add_vm_share` | Add a host directory share |
| `remove_vm_share` | Remove a directory share |
| `set_vm_shares` | Replace all shares |

### Drives
| Tool | Description |
|------|-------------|
| `list_vm_drives` | List attached drives |
| `attach_drive` | Attach an ISO or disk image |

### Portability
| Tool | Description |
|------|-------------|
| `export_vm` | Export VM to a `.utm` file |
| `import_vm` | Import VM from a `.utm` file |

### Console
| Tool | Description |
|------|-------------|
| `get_serial_port` | Get serial port address for console access |

## How MAC randomization works

Apple's Virtualization Framework ignores `MacAddress` changes written directly to `config.plist` — UTM caches the config in memory. This server uses AppleScript's `update configuration` command which properly updates UTM's internal state, giving each clone a unique MAC and therefore a unique IP on the `192.168.64.0/24` subnet.

## License

MIT
