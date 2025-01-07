This is a Discord bot created for managing Proxmox servers.


Commands:

!listcommands - List all commands

!listnodes - List all nodes

!listvms <node_name> - List all VMs on a node

!startvm <node_name> <vm_id> - Start a VM

!restartvm <node_name> <vm_id> - Restart a VM

!stopvm <node_name> <vm_id> - Stop a VM

!serverinfo - Get server info

!vminfo <node_name> - Get VMs info

!ctinfo <node_name> - Get LXC containers info

!startct <node_name> <ct_id> - Start an LXC container

!restartct <node_name> <ct_id> - Restart an LXC container

!stopct <node_name> <ct_id> - Stop an LXC container





The start.bat file is a basic startup option in a Windows environment. The start.bat file must be in the same folder as the config.json and main.py files.

In the help.txt file, everything is explained in detail, and it provides a guide for setting up the bot.

The bot can be configured in the config.json file. Full instructions can be found in the help.txt file.

Anyone who is neither a user, nor a staff member, nor an admin has no permissions for anything, and the bot will return an error: Error: You are not authorized to use this bot.




---> python version: 3.13.1

---> Proxmox version: 8.3.2

---> python packages:

pip install discord.py

pip install proxmoxer

pip install requests

pip install ping3

pip install psutil



---> Imports:

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



---------------

Updates:

1. version: 2025-01-06 [BETA]

2. version: 2025-01-07 [BETA]
	--> MAIN: Fixed authenticate user error.
	--> LXC container management options have been added. Commands: !ctinfo, !startct, !stopct, !restartct
	--> The !serverinfo command has been updated. The LXC container section has been added here as well. Internet monitoring bug fixed.
	--> Improved appearance.
	--> More refined and reworked commands.
	--> Enhanced security.
	--> Forced start, restart, and shutdown for cases where a VM or CT fails to stop.
	--> Commands are now more optimized and easier to understand.
	--> Discord bot status has been added




Made By: Bence
Made: 2025-01-06
last update: 2025-01-06

This is still a beta version, and more features, improvements, and optimizations will be coming soon.

If you need help, my Discord is: bbencevagyok

![kép](https://github.com/user-attachments/assets/59f56223-d9dd-46a1-92fa-bae3aa23c2b4)

![kép](https://github.com/user-attachments/assets/98b650e0-c0af-470c-a3fa-24635f300b76)

![kép](https://github.com/user-attachments/assets/e4923e64-dc3f-4573-b0fc-259da9c21d93)

![kép](https://github.com/user-attachments/assets/bb96c2cf-c4be-4003-8b10-a31985390748)

![kép](https://github.com/user-attachments/assets/5057da8b-7670-4f5a-9604-9a572019ac79)

![kép](https://github.com/user-attachments/assets/72d8647d-a130-4f1d-8e6f-651596e17884)











