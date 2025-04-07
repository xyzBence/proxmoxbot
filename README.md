# Proxmox Discord Bot

A modern Discord bot for monitoring and managing your Proxmox servers directly from Discord. Designed for simplicity, reliability, and powerful automation features.

---

## 📦 Features

- Slash command support (`/command`) for easier usage
- Full control over Proxmox virtual machines and containers
- Real-time server monitoring (CPU, RAM, storage, ping)
- Dynamic command list with dropdown interaction
- Server uptime and status tracking
- Clean permission system based on Discord roles
- Smart resource overview (average stats, status color indicators)

---

## 🧾 Slash Commands

| Command                        | Description |
|-------------------------------|-------------|
| `/listcommands`               | Show all available commands with interactive dropdown |
| `/listnodes`                  | List all nodes in your Proxmox cluster |
| `/listvms <node>`             | List all virtual machines on a specific node |
| `/vmavg <node>`               | Show average resource usage of all VMs on the node |
| `/startvm <node> <vm_id>`     | Start a virtual machine |
| `/restartvm <node> <vm_id>`   | Restart a virtual machine |
| `/stopvm <node> <vm_id>`      | Stop a virtual machine |
| `/listcts <node>`             | List all LXC containers on a node |
| `/ctavg <node>`               | Show average resource usage of all containers |
| `/startct <node> <ct_id>`     | Start a container |
| `/restartct <node> <ct_id>`   | Restart a container |
| `/stopct <node> <ct_id>`      | Stop a container |
| `/serverinfo`                 | Display comprehensive server status and resource usage |
| `/setlog`                     |
| `/deletelog`                  |   
| `/setuser`                    |
| `/setstaff`                   |
| `/config`                     |

---

## ⚙️ Setup Instructions

1. Place `main.py`, `config.json`, and `start.bat` in the same directory.
2. Run the bot using `start.bat` (Windows) or `python3 main.py` (Linux/macOS).
3. Configure your connection settings in `config.json`. See `help.txt` for details.

### ⚠️ Permissions

Only users with at least one of the following roles are allowed to execute commands:
- `user`
- `staff`
- `admin`

Users without the required roles will receive the message:
> `"Error: You are not authorized to use this bot."`

---

## 📚 Python Requirements

- Python version: **3.13.1**
- Proxmox version: **8.3.2**

### Required Python Packages:

```bash
pip install discord.py
pip install proxmoxer
pip install requests
pip install ping3
pip install psutil
```

---

## 📥 Python Imports and Their Purpose

```python
import discord
from discord.ext import commands
import json
import time
from proxmoxer import ProxmoxAPI
import requests
from ping3 import ping
import psutil
import subprocess
import statistics
from discord.ext import tasks
import asyncio
from itertools import cycle
from discord.ui import Select, View, Button
import logging
import datetime
```

---

## 🔄 Updates

### **version: 2025-01-06 [BETA]**
- Initial release

### **version: 2025-01-07 [BETA]**
- Fixed user authentication issue
- Added LXC container support (`/ctavg`, `/startct`, etc.)
- Enhanced `/serverinfo` and bugfixes in internet monitoring
- UI improvements and security enhancements
- Forced control options added for VMs and CTs
- Discord bot now shows online status

### **version: 2025-03-24 [BETA]**
- Major redesign: more modern layout and command handling
- Replaced `/vminfo` and `/ctinfo` with `/vmavg` and `/ctavg`
- Added `/listcts`
- Improved `/serverinfo` with storage color indicators (green/yellow/red)
- Improved dropdown-based command selection
- Smarter and clearer bot status messages

### **version: 2025-04-07 [Release Candidate]**
- Refactored all commands to use the new Discord slash (`/`) format
- Message formatting
- Command updates and modernization
- More modern appearance
- Easier usability
- Various bug fixes
- Tons of new features

---

## 👤 About

- **Made by**: Bence  
- **Created**: 2025-01-06  
- **Last Update**: 2025-04-07  
- **GitHub**: [xyzBence](https://github.com/xyzBence)  
- **Discord**: `bbencevagyok`

This project is still in **Release Candidate**. Stay tuned for more features, improved UI, and smarter automation tools soon!

---

