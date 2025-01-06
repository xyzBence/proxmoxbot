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
import os


script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")

# JSON configuration
with open(config_path, "r") as config_file:
    config = json.load(config_file)

TOKEN = config["bot_token"]
proxmox = ProxmoxAPI(
    config["proxmox"]["host"],
    user=config["proxmox"]["user"],
    password=config["proxmox"]["password"],
    verify_ssl=config["proxmox"]["verify_ssl"]
)

intents = discord.Intents.all()  # All intents
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


@bot.command()
async def listcommands(ctx):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.send(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    commands_list = (
        "**!listcommands** - List all commands\n"
        "**!listnodes** - List all nodes\n"
        "**!listvms <node>** - List all VMs on a node\n"
        "**!startvm <node> <vm_id>** - Start a VM\n"
        "**!restartvm <node> <vm_id>** - Restart a VM\n"
        "**!stopvm <node> <vm_id>** - Stop a VM\n"
        "**!serverinfo** - Get server info\n"
        "**!vminfo <node>** - Get VM info"
    )
    await ctx.send(embed=get_embed("Commands", commands_list, discord.Color.blue()))

@bot.command()
async def listnodes(ctx):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

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

        embed = discord.Embed(
            title="Available Nodes",
            description="\n\n".join(node_list),
            color=discord.Color.green()  
        )
        embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.reply(embed=embed)
    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def listvms(ctx, node: str = None):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

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

        await ctx.reply(
            embed=discord.Embed(
                title=f"Virtual Machines on Node: {node}",
                description="\n\n".join(vm_list),
                color=discord.Color.green()
            ).set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        )
    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def startvm(ctx, node: str, vm_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
        await ctx.send(embed=get_embed("Error", "You are not authorized to start this VM.", discord.Color.red()))
        return

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        if vm_status["status"] == "running":
            await ctx.send(embed=get_embed("Error", "VM is already running.", discord.Color.red()))
        else:
            proxmox.nodes(node).qemu(vm_id).status.start.post()
            await ctx.send(embed=get_embed("Success", f"VM {vm_id} on {node} started.", discord.Color.green()))
            if has_permission(ctx.author.id, "admin"):
                await ctx.author.send(embed=get_embed("Notification", f"You started VM {vm_id} on {node}.", discord.Color.blue()))
    except Exception as e:
        await ctx.send(embed=get_embed("Error", str(e), discord.Color.red()))

@bot.command()
async def restartvm(ctx, node: str, vm_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
        await ctx.send(embed=get_embed("Error", "You are not authorized to restart this VM.", discord.Color.red()))
        return

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        if vm_status["status"] != "running":
            await ctx.send(embed=get_embed("Error", "VM is not running, cannot restart.", discord.Color.red()))
        else:
            proxmox.nodes(node).qemu(vm_id).status.reboot.post()
            await ctx.send(embed=get_embed("Success", f"VM {vm_id} on {node} restarted.", discord.Color.green()))
    except Exception as e:
        await ctx.send(embed=get_embed("Error", str(e), discord.Color.red()))

@bot.command()
async def stopvm(ctx, node: str, vm_id: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
        await ctx.send(embed=get_embed("Error", "You are not authorized to stop this VM.", discord.Color.red()))
        return

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        if vm_status["status"] != "running":
            await ctx.send(embed=get_embed("Error", "VM is not running, cannot stop.", discord.Color.red()))
        else:
            proxmox.nodes(node).qemu(vm_id).status.stop.post()
            await ctx.send(embed=get_embed("Success", f"VM {vm_id} on {node} stopped.", discord.Color.green()))
    except Exception as e:
        await ctx.send(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def serverinfo(ctx):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    try:
        nodes = proxmox.nodes.get()
        info_list = []
        total_vms_cpu_usage = 0
        total_vms_memory_usage = 0
        total_vms_count = 0

        for node in nodes:
            node_name = node.get("node", "N/A")
            try:
                node_status = proxmox.nodes(node_name).status.get()
                online_status = "\U00002705 **Online**" if node_status else "**N/A**"
                cpu_usage = f"{round(node_status.get('cpu', 0) * 100, 1):.1f}%" if "cpu" in node_status and node_status.get('cpu') > 0 else "**N/A**"
                memory_used = f"{round(node_status['memory']['used'] / 1024 / 1024, 0):.0f}" if "memory" in node_status and "used" in node_status["memory"] else "**N/A**"
                memory_total = f"{round(node_status['memory']['total'] / 1024 / 1024, 0):.0f}" if "memory" in node_status and "total" in node_status["memory"] else "**N/A**"
                uptime = f"{round(node_status['uptime'] / 3600, 1):.1f} hours" if "uptime" in node_status else "**N/A**"

                
                disk_usage = []
                storage_list = proxmox.nodes(node_name).storage.get()
                for storage in storage_list:
                    storage_name = storage.get("storage", "**N/A**")
                    used = f"{round(storage.get('used', 0) / 1024 / 1024 / 1024, 1):.1f} GB" if "used" in storage else "**N/A**"
                    total = f"{round(storage.get('total', 0) / 1024 / 1024 / 1024, 1):.1f} GB" if "total" in storage else "**N/A**"
                    disk_usage.append(f"{storage_name}: {used}/{total}")

                
                try:
                    net_io = psutil.net_io_counters()
                    network_stats = f"**Network:** Received: {net_io.bytes_recv // (1024 ** 2)} MB, Sent: {net_io.bytes_sent // (1024 ** 2)} MB"
                except Exception as e:
                    network_stats = f"Error retrieving network stats: {str(e)}"

                
                def calculate_avg_ping(host, count=3):
                    ping_times = []
                    for _ in range(count):
                        try:
                            ping_process = subprocess.run(["ping", "-n", "1", host], capture_output=True, text=True)
                            if "time=" in ping_process.stdout:
                                ping_time = float(ping_process.stdout.split("time=")[-1].split("ms")[0].strip())
                                ping_times.append(ping_time)
                        except Exception:
                            pass
                    return round(statistics.mean(ping_times), 1) if ping_times else None

                google_ping = calculate_avg_ping("google.com")
                kinopoisk_ping = calculate_avg_ping("debian.org")

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
                        f"```VM ID: {vm['vmid']}```\n"
                        f"*CPU Usage:* {vm_cpu_usage:.1f}%, *Memory Usage:* {vm_memory_usage} MB"
                    )

                
                info_list.append(
                    f"**Node:** {node_name} {online_status}\n\n"
                    f"**CPU:** {cpu_usage}\n"
                    f"**Memory:** {memory_used} MB / {memory_total} MB\n"
                    f"**Uptime:** {uptime}\n\n"
                    f"{network_stats}\n"
                    + "\n".join(ping_results) + "\n\n"
                    f"**VMs:**\n\n" + "\n\n".join(vm_list)
                )

            except Exception as e:
                info_list.append(f"**Node:** {node_name}\n**Error retrieving data:** {str(e)}")

        
        avg_vms_cpu = f"{round(total_vms_cpu_usage / total_vms_count, 1):.1f}%" if total_vms_count > 0 else "**N/A**"
        avg_vms_memory = f"{round(total_vms_memory_usage / total_vms_count, 0):.0f} MB" if total_vms_count > 0 else "**N/A**"
        vms_average = f"**VMs Average:**\n*CPU Usage:*\n{avg_vms_cpu}\n*Memory Usage:*\n{avg_vms_memory}"

        
        embed = discord.Embed(title="Server Info", description="\n\n".join(info_list) + "\n\n" + vms_average, color=0x1f8b4c)
        embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.reply(embed=embed)  

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))






@bot.command()
async def vminfo(ctx, node: str):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.send(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    try:
        vms = proxmox.nodes(node).qemu.get()
        vm_list = []
        for vm in vms:
            status = "\U0001F7E2 Online" if vm["status"] == "running" else "\U0001F534 Offline"
            vm_list.append(f"ID: {vm['vmid']}, Name: {vm['name']}, Status: {status}")
        await ctx.send(embed=get_embed(f"VM Info on {node}", "\n".join(vm_list), discord.Color.purple()))
    except Exception as e:
        await ctx.send(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.event
async def on_ready():
    print(f"Bot is running! Logged in as {bot.user}.")
    print("\033[1;37mMADE BY \033[1;36mBENCE\033[0m")
    


bot.run(TOKEN)
