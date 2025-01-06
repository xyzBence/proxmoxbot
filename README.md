This is a Discord bot created for managing Proxmox servers.


Commands:

!listcommands - List all commands

!listnodes - List all nodes

!listvms <node> - List all VMs on a node

!startvm <node> <vm_id> - Start a VM

!restartvm <node> <vm_id> - Restart a VM

!stopvm <node> <vm_id> - Stop a VM

!serverinfo - Get server info

!vminfo <node> - Get VM info



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




Made By: Bence
Made: 2025-01-06
last update: 2025-01-06

This is still a beta version, and more features, improvements, and optimizations will be coming soon.


