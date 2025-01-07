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



#configuration
with open("config.json", "r") as config_file:
    config = json.load(config_file)

TOKEN = config["bot_token"]
proxmox = ProxmoxAPI(
    config["proxmox"]["host"],
    user=config["proxmox"]["user"],
    password=config["proxmox"]["password"],
    verify_ssl=config["proxmox"]["verify_ssl"]
)


#reauthenticate

def reconnect_proxmox():
    """Recreate Proxmox API connection when authentication expires."""
    global proxmox
    try:
        proxmox = ProxmoxAPI(
            config["proxmox"]["host"],
            user=config["proxmox"]["user"],
            password=config["proxmox"]["password"],
            verify_ssl=config["proxmox"]["verify_ssl"]
        )
        print("Reconnected to Proxmox API successfully.")
    except Exception as e:
        print(f"Failed to reconnect to Proxmox API: {e}")

def ensure_proxmox_connection():
    """Ensure Proxmox connection is valid, reconnect if needed."""
    try:
        proxmox.nodes.get()
    except Exception:
        print("Proxmox connection expired, reconnecting...")
        reconnect_proxmox()


@tasks.loop(hours=1)
async def auto_reconnect_proxmox():
    """Automatically reconnect to Proxmox API every hour."""
    try:
        reconnect_proxmox()  
        print("Proxmox API reconnected automatically.")
    except Exception as e:
        print(f"Automatic reconnection failed: {e}")
        
        
        try:
            
            admin_id = list(config["admin"].keys())[0]  
            admin = await bot.fetch_user(int(admin_id)) 
            embed = discord.Embed(
                title="⚠️ Proxmox API Reauthentication Failed",
                description=f"```{str(e)}```",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
            await admin.send(embed=embed)
        except Exception as notify_error:
            print(f"Failed to notify admin: {notify_error}")



intents = discord.Intents.all()  
bot = commands.Bot(command_prefix="!", intents=intents)


def get_embed(title, description, color):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return embed

def has_permission(user_id, group, vm_id=None):
    if str(user_id) in config[group]:
        if group == "user" and vm_id:
            return vm_id in config[group][str(user_id)]["allowed_vms"]
        return True
    return False

# Commands
@bot.command()
async def listcommands(ctx):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    commands_list = (
        "**List all commands:** _-now using this command_\n"
        "```!listcommands```\n\n"
        "**List all nodes:**\n"
        "```!listnodes```\n\n"
        "**List all VMs on a node:**\n"
        "!listvms <node_name>\n"
        "```!listvms```\n\n"
        "**Get server info:**\n"
        "```!serverinfo```\n\n"
        "**Get VM info on a node:**\n"
        "!vminfo <node_name>\n"
        "```!vminfo```\n\n"
        "**Start a VM:**\n"
        "!startvm <node_name> <vm_id>\n"
        "```!startvm```\n\n"
        "**Restart a VM:**\n"
        "!restartvm <node_name> <vm_id>\n"
        "```!restartvm```\n\n"
        "**Stop a VM:**\n"
        "!stopvm <node_name> <vm_id>\n"
        "```!stopvm```\n\n"
        "**Get CT info on a node:**\n"
        "!ctinfo <node_name>\n"
        "```!ctinfo```\n\n"
        "**Start a CT:**\n"
        "!startct <node_name> <ct_id>\n"
        "```!startct```\n\n"
        "**Restart a CT:**\n"
        "!restartct <node_name> <ct_id>\n"
        "```!restartct```\n\n"
        "**Stop a CT:**\n"
        "!stopct <node_name> <ct_id>\n"
        "```!stopct```"
    )

    embed = discord.Embed(
        title="Available Commands",
        description=commands_list,
        color=discord.Color.from_rgb(153, 50, 204) 
    )
    await ctx.reply(embed=embed)

@bot.command()
async def listnodes(ctx):
    
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    
    ensure_proxmox_connection()

    try:
        
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("No Nodes Found", "No nodes are available on this server.", discord.Color.yellow()))
            return

        
        node_list = []
        for node in nodes:
            node_name = node.get("node", "Unnamed")
            status = "\U0001F7E2 Online" if node.get("status", "unknown") == "online" else "\U0001F534 Offline"
            uptime = f"{round(node.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in node else "N/A"

            
            try:
                vms = proxmox.nodes(node_name).qemu.get()
                vm_count = len(vms)
            except Exception:
                vm_count = "N/A"

            
            node_list.append(
                f"**Node Name:** ```{node_name}```\n"
                f"**Status:** {status}\n"
                f"**Uptime:** {uptime}\n"
                f"**Number of VMs:** {vm_count}\n"
                "------------------------------------"
            )

        
        await ctx.reply(embed=get_embed(
            "Available Nodes",
            "\n\n".join(node_list),
            discord.Color.green()
        ))

    except Exception as e:
        
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def listvms(ctx, node: str = None):
    
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    
    ensure_proxmox_connection()

    
    if node is None:
        await ctx.reply(embed=get_embed("Usage Error", "You must provide a node name.\nExample: `!listvms <node_name>`", discord.Color.orange()))
        return

    try:
        
        vms = proxmox.nodes(node).qemu.get()
        if not vms:
            await ctx.reply(embed=get_embed(f"No VMs on {node}", f"The node `{node}` has no virtual machines.", discord.Color.yellow()))
            return

        
        vm_list = []
        for vm in vms:
            vm_name = vm.get("name", "Unnamed")
            vm_id = vm.get("vmid", "Unknown")
            vm_status = "\U0001F7E2 Online" if vm["status"] == "running" else "\U0001F534 Offline"
            vm_uptime = f"{round(vm.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in vm else "N/A"
            vm_cpu_usage = f"{round(vm.get('cpu', 0) * 100, 1):.1f}%" if "cpu" in vm else "N/A"
            vm_memory_usage = f"{round(vm.get('mem', 0) / 1024 / 1024, 0)} MB" if "mem" in vm else "N/A"

            
            vm_list.append(
                f"**Name:** {vm_name}\n"
                f"**ID:** ```{vm_id}```\n"
                f"**Status:** {vm_status}\n"
                f"**Uptime:** {vm_uptime}\n"
                f"*CPU Usage:* {vm_cpu_usage}, *Memory Usage:* {vm_memory_usage}\n"
                "------------------------------------"
            )

        
        await ctx.reply(embed=get_embed(
            f"Virtual Machines on Node: {node}",
            "\n\n".join(vm_list),
            discord.Color.green()
        ))

    except Exception as e:
        
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))



@bot.command()
async def startvm(ctx, node: str, vm_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to start this VM.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        
        if vm_status.get("lock"):
            
            proxmox.nodes(node).qemu(vm_id).status.unlock.post()
            await ctx.reply(embed=get_embed("Info", f"Lock found on VM `{vm_id}`, releasing lock...", discord.Color.orange()))
        
        if vm_status["status"] == "running":
            await ctx.reply(embed=get_embed("Error", "VM is already running.", discord.Color.red()))
            return

        status_message = await ctx.reply(embed=get_embed(
            "VM is Starting...",
            "⏳ Preparing to start VM...",
            discord.Color.orange()
        ))

        for step, text in enumerate(["Preparing resources...", "Booting up..."], 1):
            await asyncio.sleep(2)
            await status_message.edit(embed=get_embed(
                "VM is Starting...",
                f"⏳ {text}",
                discord.Color.orange()
            ))

        proxmox.nodes(node).qemu(vm_id).status.start.post()

        await status_message.edit(embed=get_embed(
            "Success",
            f"🎉 VM `{vm_id}` on `{node}` has started successfully.",
            discord.Color.green()
        ))

        if has_permission(ctx.author.id, "admin"):
            admin_id = list(config["admin"].keys())[0]
            admin = await bot.fetch_user(int(admin_id))
            await admin.send(embed=get_embed(
                "VM Started",
                f"The VM `{vm_id}` on `{node}` was started by `{ctx.author}`.",
                discord.Color.blue()
            ))

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def restartvm(ctx, node: str, vm_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to restart this VM.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        
        if vm_status.get("lock"):
            proxmox.nodes(node).qemu(vm_id).status.unlock.post()
            await ctx.reply(embed=get_embed("Info", f"Lock found on VM `{vm_id}`, releasing lock...", discord.Color.orange()))
        
        if vm_status["status"] != "running":
            await ctx.reply(embed=get_embed("Error", "VM is not running, cannot restart.", discord.Color.red()))
            return

        status_message = await ctx.reply(embed=get_embed(
            "VM is Restarting...",
            "⏳ Shutting down VM...",
            discord.Color.orange()
        ))

        proxmox.nodes(node).qemu(vm_id).status.stop.post()
        await asyncio.sleep(2)

        await status_message.edit(embed=get_embed(
            "VM is Restarting...",
            "⏳ Preparing to start VM...",
            discord.Color.orange()
        ))
        await asyncio.sleep(2)

        proxmox.nodes(node).qemu(vm_id).status.start.post()
        await status_message.edit(embed=get_embed(
            "Success",
            f"🎉 VM `{vm_id}` on `{node}` has been successfully restarted.",
            discord.Color.green()
        ))

        if has_permission(ctx.author.id, "admin"):
            admin_id = list(config["admin"].keys())[0]
            admin = await bot.fetch_user(int(admin_id))
            await admin.send(embed=get_embed(
                "VM Restarted",
                f"The VM `{vm_id}` on `{node}` was restarted by `{ctx.author}`.",
                discord.Color.blue()
            ))

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def stopvm(ctx, node: str, vm_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to stop this VM.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()

        if vm_status.get("lock"):
            proxmox.nodes(node).qemu(vm_id).status.unlock.post()
            await ctx.reply(embed=get_embed("Info", f"Lock found on VM `{vm_id}`, releasing lock...", discord.Color.orange()))

        if vm_status["status"] != "running":
            await ctx.reply(embed=get_embed("Error", "VM is not running, cannot stop.", discord.Color.red()))
            return

        status_message = await ctx.reply(embed=get_embed(
            "VM is Stopping...",
            "⏳ Shutting down VM...",
            discord.Color.orange()
        ))

        proxmox.nodes(node).qemu(vm_id).status.stop.post()
        await asyncio.sleep(2)

        await status_message.edit(embed=get_embed(
            "Success",
            f"🎉 VM `{vm_id}` on `{node}` has been successfully stopped.",
            discord.Color.green()
        ))

        if has_permission(ctx.author.id, "admin"):
            admin_id = list(config["admin"].keys())[0]
            admin = await bot.fetch_user(int(admin_id))
            await admin.send(embed=get_embed(
                "VM Stopped",
                f"The VM `{vm_id}` on `{node}` was stopped by `{ctx.author}`.",
                discord.Color.blue()
            ))

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))




@bot.command()
async def serverinfo(ctx):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    try:
        ensure_proxmox_connection()
        nodes = proxmox.nodes.get()
        info_list = []
        total_vms_cpu_usage = total_cts_memory_usage = 0
        total_vms_memory_usage = 0
        total_vms_count = total_cts_count = 0

        for node in nodes:
            node_name = node.get("node", "N/A")
            try:
                node_status = proxmox.nodes(node_name).status.get()
                online_status = "\U00002705 **Online**" if node_status else "**N/A**"
                cpu_usage = f"{round(node_status.get('cpu', 0) * 100, 1):.1f}%" if "cpu" in node_status else "0.0%"
                memory_used = f"{round(node_status['memory']['used'] / 1024 / 1024, 0):.0f}" if "memory" in node_status and "used" in node_status["memory"] else "**N/A**"
                memory_total = f"{round(node_status['memory']['total'] / 1024 / 1024, 0):.0f}" if "memory" in node_status and "total" in node_status["memory"] else "**N/A**"
                uptime = f"{round(node_status['uptime'] / 3600, 1):.1f} hours" if "uptime" in node_status else "**N/A**"

                
                try:
                    net_io = psutil.net_io_counters()
                    network_stats = f"**Network:** Received: {net_io.bytes_recv // (1024 ** 2)} MB, Sent: {net_io.bytes_sent // (1024 ** 2)} MB"
                except Exception as e:
                    network_stats = f"Error retrieving network stats: {str(e)}"

                
                def calculate_avg_ping(host, count=3):
                    ping_times = []
                    for _ in range(count):
                        try:
                            command = ["ping", "-c", "1", host] if psutil.POSIX else ["ping", "-n", "1", host]
                            ping_process = subprocess.run(command, capture_output=True, text=True)
                            if "time=" in ping_process.stdout:
                                ping_time = float(ping_process.stdout.split("time=")[-1].split("ms")[0].strip())
                                ping_times.append(ping_time)
                        except Exception:
                            pass
                    return round(statistics.mean(ping_times), 1) if ping_times else None

                google_ping = calculate_avg_ping("google.com")
                kinopoisk_ping = calculate_avg_ping("kinopoisk.ru")
                ping_results = []
                if google_ping is not None and kinopoisk_ping is not None:
                    overall_avg_ping = round((google_ping + kinopoisk_ping) / 2, 1)
                    stability = "\U0001F7E2 *Stable connection*" if overall_avg_ping < 100 else "\U0001F534 *Unstable connection*"
                    ping_results.append(f"**Ping:** {overall_avg_ping} ms {stability}")
                else:
                    ping_results.append("**Ping:** Error calculating average ping")

                
                vms = proxmox.nodes(node_name).qemu.get()
                vm_list = []
                for vm in vms:
                    vm_name = vm.get("name", "Unnamed")
                    vm_status = "\U0001F7E2 Online" if vm["status"] == "running" else "\U0001F534 Offline"
                    vm_uptime = f"{round(vm.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in vm else "**N/A**"
                    vm_cpu_usage = round(vm.get("cpu", 0) * 100, 1) if "cpu" in vm else 0
                    vm_memory_usage = round(vm.get("mem", 0) / 1024 / 1024, 0) if "mem" in vm else 0

                    total_vms_cpu_usage += vm_cpu_usage
                    total_vms_memory_usage += vm_memory_usage
                    total_vms_count += 1

                    vm_list.append(
                        f"**{vm_name}**: {vm_status}, Uptime: {vm_uptime}\n"
                        f"**VM ID:**\n```{vm['vmid']}```\n"
                        f"*CPU Usage:* {vm_cpu_usage:.1f}%, *Memory Usage:* {vm_memory_usage} MB"
                    )

                
                cts = proxmox.nodes(node_name).lxc.get()
                ct_list = []
                for ct in cts:
                    ct_name = ct.get("name", "Unnamed")
                    ct_status = "\U0001F7E2 Online" if ct["status"] == "running" else "\U0001F534 Offline"
                    ct_uptime = f"{round(ct.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in ct else "**N/A**"
                    ct_memory_usage = round(ct.get("mem", 0) / 1024 / 1024, 0) if "mem" in ct else 0

                    total_cts_memory_usage += ct_memory_usage
                    total_cts_count += 1

                    ct_list.append(
                        f"**{ct_name}**: {ct_status}, Uptime: {ct_uptime}\n"
                        f"**CT ID:**\n```{ct['vmid']}```\n"
                        f"*Memory Usage:* {ct_memory_usage} MB"
                    )

                
                info_list.append(
                    f"**Node:** {node_name} {online_status}\n\n"
                    f"**CPU:** {cpu_usage}\n"
                    f"**Memory:** {memory_used} MB / {memory_total} MB\n"
                    f"**Uptime:** {uptime}\n\n"
                    f"{network_stats}\n"
                    + "\n".join(ping_results) + "\n\n"
                    "------------------------------------\n"
                    "**VMs:**\n\n" + "\n\n".join(vm_list) + "\n\n"
                    "**VMs Average:**\n*CPU Usage:*\n"
                    f"{round(total_vms_cpu_usage / total_vms_count, 1) if total_vms_count > 0 else '0.0'}%\n"
                    f"*Memory Usage:*\n{round(total_vms_memory_usage / total_vms_count, 0) if total_vms_count > 0 else '0'} MB\n\n"
                    "------------------------------------\n"
                    "**CTs:**\n\n" + "\n\n".join(ct_list) + "\n\n"
                    "**CTs Average:**\n*Memory Usage:*\n"
                    f"{round(total_cts_memory_usage / total_cts_count, 0) if total_cts_count > 0 else '0'} MB"
                )

            except Exception as e:
                info_list.append(f"**Node:** {node_name}\n**Error retrieving data:** {str(e)}")

        embed = discord.Embed(title="Server Info", description="\n\n".join(info_list), color=0x1f8b4c)
        embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.reply(embed=embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))



@bot.command()
async def vminfo(ctx, node: str = None):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    if node is None:
        await ctx.reply(embed=get_embed("Usage Error", "You must provide a node name.\nExample: `!vminfo <node_name>`", discord.Color.orange()))
        return

    try:
        ensure_proxmox_connection()  
        vms = proxmox.nodes(node).qemu.get()
        if not vms:
            await ctx.reply(embed=get_embed(f"No VMs on {node}", f"The node `{node}` has no virtual machines.", discord.Color.yellow()))
            return

        total_vms_cpu_usage = 0
        total_vms_memory_usage = 0
        total_vms_count = 0
        vm_list = []

        for vm in vms:
            vm_name = vm.get("name", "Unnamed")
            vm_id = vm.get("vmid", "Unknown")
            vm_status = "\U0001F7E2 Online" if vm["status"] == "running" else "\U0001F534 Offline"
            vm_uptime = f"{round(vm.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in vm else "**N/A**"
            vm_cpu_usage = round(vm.get("cpu", 0) * 100, 1) if "cpu" in vm else 0
            vm_memory_usage = round(vm.get("mem", 0) / 1024 / 1024, 0) if "mem" in vm else 0

            total_vms_cpu_usage += vm_cpu_usage
            total_vms_memory_usage += vm_memory_usage
            total_vms_count += 1

            vm_list.append(
                f"**Name:** {vm_name}\n"
                f"**VM ID:**\n```{vm_id}```\n"  
                f"**Status:** {vm_status}\n"
                f"**Uptime:** {vm_uptime}\n"
                f"*CPU Usage:* {vm_cpu_usage:.1f}%, *Memory Usage:* {vm_memory_usage} MB\n"
                "------------------------------------"
            )

        
        avg_vms_cpu = f"{round(total_vms_cpu_usage / total_vms_count, 1):.1f}%" if total_vms_count > 0 else "**N/A**"
        avg_vms_memory = f"{round(total_vms_memory_usage / total_vms_count, 0):.0f} MB" if total_vms_count > 0 else "**N/A**"
        vms_average = f"**VMs Average:**\n*CPU Usage:*\n{avg_vms_cpu}\n*Memory Usage:*\n{avg_vms_memory}"

        
        embed = discord.Embed(
            title=f"VM Info on Node: {node}",
            description="\n\n".join(vm_list) + "\n\n" + vms_average,
            color=discord.Color.purple()  
        )
        embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.reply(embed=embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))



@bot.command()
async def ctinfo(ctx, node: str = None):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    if node is None:
        await ctx.reply(embed=get_embed("Usage Error", "You must provide a node name.\nExample: `!ctinfo <node_name>`", discord.Color.orange()))
        return

    try:
        ensure_proxmox_connection()  
        cts = proxmox.nodes(node).lxc.get()
        if not cts:
            await ctx.reply(embed=get_embed(f"No CTs on {node}", f"The node `{node}` has no containers.", discord.Color.yellow()))
            return

        total_cts_cpu_usage = 0
        total_cts_memory_usage = 0
        total_cts_count = 0
        ct_list = []

        for ct in cts:
            ct_name = ct.get("name", "Unnamed")
            ct_id = ct.get("vmid", "Unknown")
            ct_status = "\U0001F7E2 Online" if ct["status"] == "running" else "\U0001F534 Offline"
            ct_uptime = f"{round(ct.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in ct else "**N/A**"
            ct_cpu_usage = round(ct.get("cpu", 0) * 100, 1) if "cpu" in ct else 0
            ct_memory_usage = round(ct.get("mem", 0) / 1024 / 1024, 0) if "mem" in ct else 0

            total_cts_cpu_usage += ct_cpu_usage
            total_cts_memory_usage += ct_memory_usage
            total_cts_count += 1

            ct_list.append(
                f"**Name:** {ct_name}\n"
                f"**CT ID:**\n```{ct_id}```\n"  
                f"**Status:** {ct_status}\n"
                f"**Uptime:** {ct_uptime}\n"
                f"*CPU Usage:* {ct_cpu_usage:.1f}%, *Memory Usage:* {ct_memory_usage} MB\n"
                "------------------------------------"
            )

        
        avg_cts_cpu = f"{round(total_cts_cpu_usage / total_cts_count, 1):.1f}%" if total_cts_count > 0 else "**N/A**"
        avg_cts_memory = f"{round(total_cts_memory_usage / total_cts_count, 0):.0f} MB" if total_cts_count > 0 else "**N/A**"
        cts_average = f"**CTs Average:**\n*CPU Usage:*\n{avg_cts_cpu}\n*Memory Usage:*\n{avg_cts_memory}"

        
        embed = discord.Embed(
            title=f"Container Info on Node: {node}",
            description="\n\n".join(ct_list) + "\n\n" + cts_average,
            color=discord.Color.teal()  
        )
        embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.reply(embed=embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def startct(ctx, node: str, ct_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to start this container.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    try:
        ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
        if ct_status["status"] == "running":
            await ctx.reply(embed=get_embed("Error", "Container is already running.", discord.Color.red()))
            return

        status_message = await ctx.reply(embed=get_embed(
            "Container is Starting...",
            "⏳ Preparing to start container...",
            discord.Color.orange()
        ))

        for step, text in enumerate(["Preparing resources...", "Booting up..."], 1):
            await asyncio.sleep(2)
            await status_message.edit(embed=get_embed(
                "Container is Starting...",
                f"⏳ {text}",
                discord.Color.orange()
            ))

        proxmox.nodes(node).lxc(ct_id).status.start.post()

        await status_message.edit(embed=get_embed(
            "Success",
            f"🎉 Container `{ct_id}` on `{node}` has started successfully.",
            discord.Color.green()
        ))

        if has_permission(ctx.author.id, "admin"):
            admin_id = list(config["admin"].keys())[0]
            admin = await bot.fetch_user(int(admin_id))
            await admin.send(embed=get_embed(
                "Container Started",
                f"The container `{ct_id}` on `{node}` was started by `{ctx.author}`.",
                discord.Color.blue()
            ))

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def restartct(ctx, node: str, ct_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to restart this container.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    try:
        ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
        if ct_status["status"] != "running":
            await ctx.reply(embed=get_embed("Error", "Container is not running, cannot restart.", discord.Color.red()))
            return

        status_message = await ctx.reply(embed=get_embed(
            "Container is Restarting...",
            "⏳ Shutting down container...",
            discord.Color.orange()
        ))

        proxmox.nodes(node).lxc(ct_id).status.stop.post()
        await asyncio.sleep(2)

        await status_message.edit(embed=get_embed(
            "Container is Restarting...",
            "⏳ Preparing to start container...",
            discord.Color.orange()
        ))
        await asyncio.sleep(2)

        proxmox.nodes(node).lxc(ct_id).status.start.post()

        await status_message.edit(embed=get_embed(
            "Success",
            f"🎉 Container `{ct_id}` on `{node}` has been successfully restarted.",
            discord.Color.green()
        ))

        if has_permission(ctx.author.id, "admin"):
            admin_id = list(config["admin"].keys())[0]
            admin = await bot.fetch_user(int(admin_id))
            await admin.send(embed=get_embed(
                "Container Restarted",
                f"The container `{ct_id}` on `{node}` was restarted by `{ctx.author}`.",
                discord.Color.blue()
            ))

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def stopct(ctx, node: str, ct_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to stop this container.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    try:
        ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
        if ct_status["status"] != "running":
            await ctx.reply(embed=get_embed("Error", "Container is not running, cannot stop.", discord.Color.red()))
            return

        status_message = await ctx.reply(embed=get_embed(
            "Container is Stopping...",
            "⏳ Shutting down container...",
            discord.Color.orange()
        ))

        proxmox.nodes(node).lxc(ct_id).status.stop.post()
        await asyncio.sleep(2)

        await status_message.edit(embed=get_embed(
            "Container is Stopping...",
            "⏳ Finalizing shutdown process...",
            discord.Color.orange()
        ))
        await asyncio.sleep(2)

        await status_message.edit(embed=get_embed(
            "Success",
            f"🎉 Container `{ct_id}` on `{node}` has been successfully stopped.",
            discord.Color.green()
        ))

        if has_permission(ctx.author.id, "admin"):
            admin_id = list(config["admin"].keys())[0]
            admin = await bot.fetch_user(int(admin_id))
            await admin.send(embed=get_embed(
                "Container Stopped",
                f"The container `{ct_id}` on `{node}` was stopped by `{ctx.author}`.",
                discord.Color.blue()
            ))

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))









# ----------------------------
# Do not take it out and edit it because it is a debug and authentication section!!!

@bot.event
async def on_ready():

    print("\033c", end="")

    
    print("\033[1;32m" + "=" * 50)
    print(f"\033[1;36mBot Status:\033[1;32m RUNNING! 🎉")
    print(f"\033[1;33mLogged in as:\033[1;37m {bot.user.name}#{bot.user.discriminator}")
    print(f"\033[1;33mBot ID:\033[1;37m {bot.user.id}")
    print(f"\033[1;33mDiscord.py Version:\033[1;37m {discord.__version__}")
    print("\033[1;32m" + "=" * 50)

    
    print(f"\033[1;34m[INFO]\033[1;37m Starting Proxmox reauthentication loop...")
    auto_reconnect_proxmox.start()  
    print("\033[1;32m[OK]\033[1;37m Proxmox reauthentication is running.")
    
    
    rotate_status.start()
    
    
    print("\n\033[1;37mMADE BY: \033[1;36mBENCE\033[0m")
    print("\033[1;32m" + "=" * 50)


status_messages = cycle([
    "Made by Bence",
    "!listcommands",
    "!startvm",
    "!restartvm",
    "!stopvm",
    "!serverinfo ",
    "!vminfo",
    "Made by Bence",
    "!ctinfo",
    "!startct",
    "!restartct",
    "!stopct"
])

@tasks.loop(seconds=4)
async def rotate_status():
    current_status = next(status_messages)
    await bot.change_presence(activity=discord.Game(name=current_status))



bot.run(TOKEN)
