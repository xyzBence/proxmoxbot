# Imports
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

# Configuration
with open("config.json", "r") as config_file:
    config = json.load(config_file)

TOKEN = config["bot_token"]
proxmox = ProxmoxAPI(
    config["proxmox"]["host"],
    user=config["proxmox"]["user"],
    password=config["proxmox"]["password"],
    verify_ssl=config["proxmox"]["verify_ssl"]
)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.INFO)

# Helper functions for config management
def load_config():
    try:
        with open("config.json", "r") as config_file:
            return json.load(config_file)
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}")
        return None

def save_config(config_data):
    try:
        with open("config.json", "w") as config_file:
            json.dump(config_data, config_file, indent=4)
    except Exception as e:
        logging.error(f"Failed to save config.json: {e}")

# Permission check
def has_permission(user_id, group, vm_id=None):
    config_data = load_config()
    if config_data is None:
        return False
    if str(user_id) in config_data[group]:
        if group == "user" and vm_id:
            return vm_id in config_data[group][str(user_id)]["allowed_vms"]
        return True
    return False

# Utility function to create embeds
def get_embed(title, description, color):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return embed

# Reauthentication
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
        logging.info("Reconnected to Proxmox API successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to reconnect to Proxmox API: {e}")
        return False

def ensure_proxmox_connection():
    """Ensure Proxmox connection is valid, reconnect if needed."""
    global proxmox
    try:
        
        proxmox.nodes.get()
        return True
    except Exception as e:
        logging.info(f"Proxmox connection invalid or expired: {e}, attempting to reconnect...")
        if reconnect_proxmox():
            try:
                
                proxmox.nodes.get()
                logging.info("New Proxmox connection verified.")
                return True
            except Exception as e:
                logging.error(f"Failed to verify new Proxmox connection: {e}")
                return False
        else:
            logging.error("Reconnection attempt failed.")
            return False

@tasks.loop(minutes=5)
async def auto_reconnect_proxmox():
    """Automatically reconnect to Proxmox API every 5 minutes."""
    config_data = load_config()
    if config_data is None:
        logging.error("Failed to load config.json for Proxmox reauthentication.")
        return

    try:
        global proxmox
        proxmox = ProxmoxAPI(
            host=config_data["proxmox"]["host"],
            user=config_data["proxmox"]["user"],
            password=config_data["proxmox"]["password"],
            verify_ssl=config_data["proxmox"]["verify_ssl"]
        )
        logging.info("Proxmox API reconnected successfully.")
    except Exception as e:
        logging.error(f"Failed to reconnect to Proxmox API: {e}")
        logging.info("Proxmox API reconnected automatically.")





# Commands

@bot.command(name="setlog")
async def setlog(ctx, channel_id: str = None):
    """Set a channel as the log channel."""
    if not has_permission(ctx.author.id, "admin"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this command. Admin access required.", discord.Color.red()))
        return

    config_data = load_config()
    if config_data is None:
        await ctx.reply(embed=get_embed("Error", "Failed to load configuration file.", discord.Color.red()))
        return

 
    if "log_channel" in config_data and config_data["log_channel"] is not None:
        await ctx.reply(embed=get_embed(
            title="🚫 Error",
            description=f"A log channel is already set: <#{config_data['log_channel']}>. Please delete it first using ```/deletelog``` before setting a new one.",
            color=discord.Color.red()
        ))
        return

    if channel_id is None:
        embed = get_embed(
            title="🚫 Error",
            description="You did not provide a channel ID.\nCorrect usage:\n```/setlog```\n``/setlog <channel ID>``",
            color=discord.Color.red()
        )
        view = View()

        green_button = Button(label="Set Current Channel", style=discord.ButtonStyle.green)
        red_button = Button(label="Cancel", style=discord.ButtonStyle.red)

        async def green_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message(embed=get_embed("Error", "Only the command issuer can interact with this.", discord.Color.red()), ephemeral=True)
                return
            channel = ctx.channel
            config_data["log_channel"] = str(channel.id)
            save_config(config_data)
            await interaction.response.edit_message(embed=get_embed("✅ Success", f"Log channel set to {channel.mention} (ID: {channel.id}).", discord.Color.green()), view=None)
            logging.info(f"Log channel set to {channel.id} by Admin={ctx.author.id}")

        async def red_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message(embed=get_embed("Error", "Only the command issuer can interact with this.", discord.Color.red()), ephemeral=True)
                return
            await interaction.message.delete() 
            await ctx.message.delete()         

        green_button.callback = green_callback
        red_button.callback = red_callback
        view.add_item(green_button)
        view.add_item(red_button)
        await ctx.reply(embed=embed, view=view)
        return

  
    try:
        channel = await bot.fetch_channel(int(channel_id))
        if channel.guild.id != ctx.guild.id:
            await ctx.reply(embed=get_embed("Error", f"Channel ID **{channel_id}** is not in this server.", discord.Color.red()))
            return
    except (discord.NotFound, ValueError):
        await ctx.reply(embed=get_embed("Error", f"Channel ID **{channel_id}** is invalid or not found.", discord.Color.red()))
        return


    config_data["log_channel"] = channel_id
    save_config(config_data)
    logging.info(f"Log channel set to {channel_id} by Admin={ctx.author.id}")

    embed = get_embed(
        title="✅ Success",
        description=f"Log channel set to <#{channel_id}> (ID: {channel_id}).",
        color=discord.Color.green()
    )
    await ctx.reply(embed=embed)


@bot.command(name="deletelog")
async def deletelog(ctx):
    """Delete the configured log channel."""
    if not has_permission(ctx.author.id, "admin"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this command. Admin access required.", discord.Color.red()))
        return

    config_data = load_config()
    if config_data is None:
        await ctx.reply(embed=get_embed("Error", "Failed to load configuration file.", discord.Color.red()))
        return

    if "log_channel" not in config_data or config_data["log_channel"] is None:
        await ctx.reply(embed=get_embed("Error", "No log channel is currently set.", discord.Color.red()))
        return

    embed = get_embed(
        title="⚠️ Confirm Deletion",
        description=f"Are you sure you want to delete the log channel <#{config_data['log_channel']}>?",
        color=discord.Color.orange()
    )
    view = View()

    green_button = Button(label="Confirm", style=discord.ButtonStyle.green)
    red_button = Button(label="Cancel", style=discord.ButtonStyle.red)

    async def green_callback(interaction):
        if interaction.user.id != ctx.author.id:
            await interaction.response.send_message(embed=get_embed("Error", "Only the command issuer can interact with this.", discord.Color.red()), ephemeral=True)
            return
        old_channel_id = config_data["log_channel"]
        config_data["log_channel"] = None
        save_config(config_data)
        await interaction.response.edit_message(embed=get_embed("✅ Success", f"Log channel <#{old_channel_id}> has been deleted.", discord.Color.green()), view=None)
        logging.info(f"Log channel {old_channel_id} deleted by Admin={ctx.author.id}")

    async def red_callback(interaction):
        if interaction.user.id != ctx.author.id:
            await interaction.response.send_message(embed=get_embed("Error", "Only the command issuer can interact with this.", discord.Color.red()), ephemeral=True)
            return
        await interaction.message.delete()  
        await ctx.message.delete()          

    green_button.callback = green_callback
    red_button.callback = red_callback
    view.add_item(green_button)
    view.add_item(red_button)

    await ctx.reply(embed=embed, view=view)

async def send_log_message(embed):
    config_data = load_config()
    if config_data and "log_channel" in config_data and config_data["log_channel"]:
        try:
            channel = await bot.fetch_channel(int(config_data["log_channel"]))
            await channel.send(embed=embed)
        except Exception as e:
            logging.error(f"Failed to send log message: {str(e)}")


@bot.command(name="setuser")
async def setuser(ctx, member: discord.Member = None, vm_ct_id: str = None):
    """Add a new user with allowed VM/CT IDs to the config."""
    if not has_permission(ctx.author.id, "admin"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this command. Admin access required.", discord.Color.red()))
        return

    if member is None or vm_ct_id is None:
        await ctx.reply(embed=get_embed("Error", "Please provide a valid Discord ID, username, or mention a user, and a VM/CT ID.\nCorrect usage: ```/setuser <dc ID, username, or mention> <VM/CT ID>```", discord.Color.red()))
        return

    config_data = load_config()
    if config_data is None:
        await ctx.reply(embed=get_embed("Error", "Failed to load configuration file.", discord.Color.red()))
        return

    member_id = str(member.id)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


    ensure_proxmox_connection()
    vm_exists = False
    ct_exists = False
    try:
        nodes = proxmox.nodes.get()
        for node in nodes:
            node_name = node["node"]
            vms = proxmox.nodes(node_name).qemu.get()
            cts = proxmox.nodes(node_name).lxc.get()
            if any(vm["vmid"] == int(vm_ct_id) for vm in vms):
                vm_exists = True
                break
            if any(ct["vmid"] == int(vm_ct_id) for ct in cts):
                ct_exists = True
                break
    except Exception as e:
        await ctx.reply(embed=get_embed("Error", f"Failed to verify VM/CT ID: {str(e)}", discord.Color.red()))
        return

    if not vm_exists and not ct_exists:
        await ctx.reply(embed=get_embed("Error", f"VM/CT ID **{vm_ct_id}** does not exist in Proxmox.", discord.Color.red()))
        return

    if member_id in config_data["admin"]:
        await ctx.reply(embed=get_embed("Error", f"**{member.display_name}** (ID: {member_id}) is an admin and cannot be added as a user.", discord.Color.red()))
        return
    if member_id in config_data["staff"]:
        await ctx.reply(embed=get_embed("Error", f"**{member.display_name}** (ID: {member_id}) is a staff member and cannot be added as a user.", discord.Color.red()))
        return

    action = "added"
    if member_id not in config_data["user"]:
        config_data["user"][member_id] = {"allowed_vms": [vm_ct_id]}
    else:
        if vm_ct_id not in config_data["user"][member_id]["allowed_vms"]:
            config_data["user"][member_id]["allowed_vms"].append(vm_ct_id)
            action = "updated"
        else:
            await ctx.reply(embed=get_embed("Error", f"VM/CT ID **{vm_ct_id}** is already assigned to **{member.display_name}** (ID: {member_id}).", discord.Color.red()))
            return

    save_config(config_data)
    logging.info(f"User {action}: ID={member_id}, Name={member.display_name}, VM/CT ID={vm_ct_id}, by Admin={ctx.author.id}")


    log_embed = discord.Embed(
        title="📝 User Configuration Log",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.fromtimestamp(time.time())
    )
    log_embed.add_field(
        name="Admin",
        value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
        inline=False
    )
    log_embed.add_field(
        name="Command Used",
        value="``/setuser``",
        inline=False
    )
    log_embed.add_field(
        name="Action",
        value=f"{ctx.author.display_name} used the ``/setuser`` command on {timestamp} to {action} a user.",
        inline=False
    )
    log_embed.add_field(
        name="Affected User",
        value=f"{member.display_name} (ID: {member_id})",
        inline=False
    )
    log_embed.add_field(
        name="VM/CT ID",
        value=f"**{vm_ct_id}**",
        inline=False
    )
    await send_log_message(log_embed)

    embed = get_embed(
        title="✅ Success",
        description=f"**{member.display_name}** (ID: {member_id}) has been {action} as a user with VM/CT ID **{vm_ct_id}**.",
        color=discord.Color.green()
    )
    await ctx.reply(embed=embed)

@bot.command(name="setstaff")
async def setstaff(ctx, member: discord.Member = None):
    """Add a new staff member to the config."""
    if not has_permission(ctx.author.id, "admin"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this command. Admin access required.", discord.Color.red()))
        return

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


    if member is None:
        await ctx.reply(embed=get_embed("Error", "Please provide a valid Discord ID, username, or mention a user.\nCorrect usage: ```/setstaff <dc ID, username, or mention>```", discord.Color.red()))


        log_embed = discord.Embed(
            title="📝 Staff Configuration Log",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="Admin",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/setstaff``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} attempted to use the ``/setstaff`` command on {timestamp} but provided an invalid argument.",
            inline=False
        )
        await send_log_message(log_embed)
        return

    config_data = load_config()
    if config_data is None:
        await ctx.reply(embed=get_embed("Error", "Failed to load configuration file.", discord.Color.red()))
        return

    member_id = str(member.id)

 
    if member_id in config_data["staff"]:
        await ctx.reply(embed=get_embed("Error", f"**{member.display_name}** (ID: {member_id}) is already a staff member.", discord.Color.red()))

  
        log_embed = discord.Embed(
            title="📝 Staff Configuration Log",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="Admin",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/setstaff``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} attempted to use the ``/setstaff`` command on {timestamp} to add a staff member.",
            inline=False
        )
        log_embed.add_field(
            name="Affected Staff",
            value=f"{member.display_name} (ID: {member_id})",
            inline=False
        )
        log_embed.add_field(
            name="Result",
            value="Failed: User is already a staff member.",
            inline=False
        )
        await send_log_message(log_embed)
        return

    if member_id in config_data["admin"]:
        await ctx.reply(embed=get_embed("Error", f"**{member.display_name}** (ID: {member_id}) is an admin and cannot be added as staff.", discord.Color.red()))
        return

    config_data["staff"][member_id] = "Staff ID"
    save_config(config_data)
    logging.info(f"Staff added: ID={member_id}, Name={member.display_name}, by Admin={ctx.author.id}")


    log_embed = discord.Embed(
        title="📝 Staff Configuration Log",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.fromtimestamp(time.time())
    )
    log_embed.add_field(
        name="Admin",
        value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
        inline=False
    )
    log_embed.add_field(
        name="Command Used",
        value="``/setstaff``",
        inline=False
    )
    log_embed.add_field(
        name="Action",
        value=f"{ctx.author.display_name} used the ``/setstaff`` command on {timestamp} to add a staff member.",
        inline=False
    )
    log_embed.add_field(
        name="Affected Staff",
        value=f"{member.display_name} (ID: {member_id})",
        inline=False
    )
    await send_log_message(log_embed)

    embed = get_embed(
        title="✅ Success",
        description=f"**{member.display_name}** (ID: {member_id}) has been added as a staff member.",
        color=discord.Color.green()
    )
    await ctx.reply(embed=embed)

@bot.command()
async def config(ctx):
    """Show and manage bot configuration."""
    if not has_permission(ctx.author.id, "admin"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this command. Admin access required.", discord.Color.red()))
        return

    config_data = load_config()
    if config_data is None:
        await ctx.reply(embed=get_embed("Error", "Failed to load configuration file.", discord.Color.red()))
        return

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


    log_embed = discord.Embed(
        title="📝 Config Command Log",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.fromtimestamp(time.time())
    )
    log_embed.add_field(
        name="Admin",
        value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
        inline=False
    )
    log_embed.add_field(
        name="Command Used",
        value="``/config``",
        inline=False
    )
    log_embed.add_field(
        name="Action",
        value=f"{ctx.author.display_name} used the ``/config`` command on {timestamp} to view or manage the configuration.",
        inline=False
    )
    await send_log_message(log_embed)


    admin_list = "\n".join([f"<@{admin_id}> (ID: {admin_id})" for admin_id in config_data["admin"].keys()]) or "None"
    staff_list = "\n".join([f"<@{staff_id}> (ID: {staff_id})" for staff_id in config_data["staff"].keys()]) or "None"
    user_list = "\n".join([f"<@{user_id}> (ID: {user_id}) - Allowed VMs/CTs: {', '.join(config_data['user'][user_id]['allowed_vms'])}" for user_id in config_data["user"].keys()]) or "None"

    description = (
        "🔧 **Bot Configuration** 🔧\n\n"
        "**Admins**\n"
        f"{admin_list}\n\n"
        "**Staff**\n"
        f"{staff_list}\n\n"
        "**Users**\n"
        f"{user_list}\n\n"
        "**Available Commands**\n"
        "```\n/setstaff\n```\n"
        "Add a new staff member to the config\n"
        "``/setstaff <discord ID, username, or mention>``\n\n"
        "```\n/setuser\n```\n"
        "Add a new user with allowed VM/CT IDs to the config\n"
        "``/setuser <discord ID, username, or mention> <vm/ct ID>``"
    )

    embed = get_embed(
        title="⚙️ Configuration Overview ⚙️",
        description=description,
        color=discord.Color.blue()
    )

    select = Select(
        placeholder="Select an action...",
        options=[
            discord.SelectOption(label="Delete Staff", value="delete_staff", description="Remove a staff member", emoji="🧑‍💼"),
            discord.SelectOption(label="Delete User/VM-CT ID", value="delete_user", description="Remove a user or their VM/CT ID", emoji="👤")
        ]
    )

    async def show_config_message(interaction=None):
        embed = get_embed(
            title="⚙️ Configuration Overview ⚙️",
            description=description,
            color=discord.Color.blue()
        )
        view = View()
        view.add_item(select)
        if interaction:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            return await ctx.reply(embed=embed, view=view)

    async def show_delete_staff_message(interaction):
        config_data = load_config()
        if config_data is None:
            embed = get_embed("Error", "Failed to load configuration file.", discord.Color.red())
            await interaction.response.edit_message(embed=embed, view=None)
            return

        staff_options = [
            discord.SelectOption(label=f"Staff: {ctx.guild.get_member(int(staff_id)).display_name if ctx.guild.get_member(int(staff_id)) else 'Unknown'}", value=staff_id)
            for staff_id in config_data["staff"].keys()
        ]

        if not staff_options:
            embed = get_embed("Error", "No staff members to delete.", discord.Color.red())
            await interaction.response.edit_message(embed=embed, view=None)
            return

        embed = get_embed(
            title="🧑‍💼 Staff Deletion Section 🧑‍💼",
            description="Select a staff member to delete:",
            color=discord.Color.orange()
        )

        staff_select = Select(placeholder="Select a staff member...", options=staff_options)

        async def staff_select_callback(interaction):
            staff_id = staff_select.values[0]
            staff_name = ctx.guild.get_member(int(staff_id)).display_name if ctx.guild.get_member(int(staff_id)) else "Unknown"

            embed = get_embed(
                title="⚠️ Confirm Deletion",
                description=f"Are you sure you want to delete **{staff_name}** (ID: {staff_id}) from staff?",
                color=discord.Color.red()
            )

            view = View()
            back_button = Button(label="Back", style=discord.ButtonStyle.grey)
            confirm_button = Button(label="Confirm", style=discord.ButtonStyle.green)

            async def back_to_delete_staff(interaction):
                await show_delete_staff_message(interaction)

            async def confirm_staff_deletion(interaction):
                config_data = load_config()
                if config_data is None:
                    embed = get_embed("Error", "Failed to load configuration file.", discord.Color.red())
                    await interaction.response.edit_message(embed=embed, view=None)
                    return

                if staff_id in config_data["staff"]:
                    del config_data["staff"][staff_id]
                    save_config(config_data)
                    logging.info(f"Staff deleted: ID={staff_id}, Name={staff_name}, by Admin={ctx.author.id}")


                    log_embed = discord.Embed(
                        title="📝 Staff Configuration Log",
                        color=discord.Color.blue(),
                        timestamp=datetime.datetime.fromtimestamp(time.time())
                    )
                    log_embed.add_field(
                        name="Admin",
                        value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                        inline=False
                    )
                    log_embed.add_field(
                        name="Command Used",
                        value="``/config``",
                        inline=False
                    )
                    log_embed.add_field(
                        name="Action",
                        value=f"{ctx.author.display_name} used the ``/config`` command on {timestamp} to delete a staff member.",
                        inline=False
                    )
                    log_embed.add_field(
                        name="Deleted Staff",
                        value=f"{staff_name} (ID: {staff_id})",
                        inline=False
                    )
                    await send_log_message(log_embed)

                    embed = get_embed(
                        title="✅ Success",
                        description=f"**{staff_name}** (ID: {staff_id}) has been removed from staff.",
                        color=discord.Color.green()
                    )
                    view = View()
                    back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                    back_button.callback = back_to_delete_staff
                    view.add_item(back_button)
                    await interaction.response.edit_message(embed=embed, view=view)
                else:
                    embed = get_embed("Error", "Staff member not found.", discord.Color.red())
                    await interaction.response.edit_message(embed=embed, view=None)

            back_button.callback = back_to_delete_staff
            confirm_button.callback = confirm_staff_deletion
            view.add_item(back_button)
            view.add_item(confirm_button)

            await interaction.response.edit_message(embed=embed, view=view)

        staff_select.callback = staff_select_callback
        view = View()
        view.add_item(staff_select)
        back_button = Button(label="Back", style=discord.ButtonStyle.grey)
        back_button.callback = show_config_message
        view.add_item(back_button)
        await interaction.response.edit_message(embed=embed, view=view)

    async def show_delete_user_message(interaction):
        embed = get_embed(
            title="👤 User/VM-CT Deletion Section 👤",
            description="What would you like to do?",
            color=discord.Color.orange()
        )

        user_select = Select(
            placeholder="Select an action...",
            options=[
                discord.SelectOption(label="Delete User", value="delete_full_user", description="Remove the entire user", emoji="🗑️"),
                discord.SelectOption(label="Delete VM/CT ID", value="delete_vm_ct", description="Remove a specific VM/CT ID from a user", emoji="🔧")
            ]
        )

        async def user_select_callback(interaction):
            config_data = load_config()
            if config_data is None:
                embed = get_embed("Error", "Failed to load configuration file.", discord.Color.red())
                await interaction.response.edit_message(embed=embed, view=None)
                return

            if user_select.values[0] == "delete_full_user":
                user_options = [
                    discord.SelectOption(label=f"User: {ctx.guild.get_member(int(user_id)).display_name if ctx.guild.get_member(int(user_id)) else 'Unknown'}", value=user_id)
                    for user_id in config_data["user"].keys()
                ]

                if not user_options:
                    embed = get_embed("Error", "No users to delete.", discord.Color.red())
                    await interaction.response.edit_message(embed=embed, view=None)
                    return

                embed = get_embed(
                    title="🗑️ Delete User",
                    description="Select a user to delete:",
                    color=discord.Color.orange()
                )

                user_delete_select = Select(placeholder="Select a user...", options=user_options)

                async def user_delete_select_callback(interaction):
                    user_id = user_delete_select.values[0]
                    user_name = ctx.guild.get_member(int(user_id)).display_name if ctx.guild.get_member(int(user_id)) else "Unknown"

                    embed = get_embed(
                        title="⚠️ Confirm Deletion",
                        description=f"Are you sure you want to delete **{user_name}** (ID: {user_id}) and all their allowed VMs/CTs?",
                        color=discord.Color.red()
                    )

                    view = View()
                    back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                    confirm_button = Button(label="Confirm", style=discord.ButtonStyle.green)

                    async def back_to_delete_user(interaction):
                        await show_delete_user_message(interaction)

                    async def confirm_user_deletion(interaction):
                        config_data = load_config()
                        if config_data is None:
                            embed = get_embed("Error", "Failed to load configuration file.", discord.Color.red())
                            await interaction.response.edit_message(embed=embed, view=None)
                            return

                        if user_id in config_data["user"]:
                            del config_data["user"][user_id]
                            save_config(config_data)
                            logging.info(f"User deleted: ID={user_id}, Name={user_name}, by Admin={ctx.author.id}")


                            log_embed = discord.Embed(
                                title="📝 User Configuration Log",
                                color=discord.Color.blue(),
                                timestamp=datetime.datetime.fromtimestamp(time.time())
                            )
                            log_embed.add_field(
                                name="Admin",
                                value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                                inline=False
                            )
                            log_embed.add_field(
                                name="Command Used",
                                value="``/config``",
                                inline=False
                            )
                            log_embed.add_field(
                                name="Action",
                                value=f"{ctx.author.display_name} used the ``/config`` command on {timestamp} to delete a user.",
                                inline=False
                            )
                            log_embed.add_field(
                                name="Deleted User",
                                value=f"{user_name} (ID: {user_id})",
                                inline=False
                            )
                            await send_log_message(log_embed)

                            embed = get_embed(
                                title="✅ Success",
                                description=f"**{user_name}** (ID: {user_id}) has been removed from users.",
                                color=discord.Color.green()
                            )
                            view = View()
                            back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                            back_button.callback = back_to_delete_user
                            view.add_item(back_button)
                            await interaction.response.edit_message(embed=embed, view=view)
                        else:
                            embed = get_embed("Error", "User not found.", discord.Color.red())
                            await interaction.response.edit_message(embed=embed, view=None)

                    back_button.callback = back_to_delete_user
                    confirm_button.callback = confirm_user_deletion
                    view.add_item(back_button)
                    view.add_item(confirm_button)

                    await interaction.response.edit_message(embed=embed, view=view)

                user_delete_select.callback = user_delete_select_callback
                view = View()
                view.add_item(user_delete_select)
                back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                back_button.callback = show_delete_user_message
                view.add_item(back_button)
                await interaction.response.edit_message(embed=embed, view=view)

            elif user_select.values[0] == "delete_vm_ct":
                user_options = [
                    discord.SelectOption(label=f"User: {ctx.guild.get_member(int(user_id)).display_name if ctx.guild.get_member(int(user_id)) else 'Unknown'}", value=user_id)
                    for user_id in config_data["user"].keys()
                ]

                if not user_options:
                    embed = get_embed("Error", "No users to modify.", discord.Color.red())
                    await interaction.response.edit_message(embed=embed, view=None)
                    return

                embed = get_embed(
                    title="🔧 Delete VM/CT ID",
                    description="Select a user to modify their allowed VMs/CTs:",
                    color=discord.Color.orange()
                )

                user_vm_select = Select(placeholder="Select a user...", options=user_options)

                async def user_vm_select_callback(interaction):
                    user_id = user_vm_select.values[0]
                    user_name = ctx.guild.get_member(int(user_id)).display_name if ctx.guild.get_member(int(user_id)) else "Unknown"
                    config_data = load_config()
                    if config_data is None:
                        embed = get_embed("Error", "Failed to load configuration file.", discord.Color.red())
                        await interaction.response.edit_message(embed=embed, view=None)
                        return

                    vm_ct_options = [
                        discord.SelectOption(label=f"VM/CT ID: {vm_id}", value=vm_id)
                        for vm_id in config_data["user"][user_id]["allowed_vms"]
                    ]

                    if not vm_ct_options:
                        embed = get_embed("Error", f"**{user_name}** has no allowed VMs/CTs to delete.", discord.Color.red())
                        await interaction.response.edit_message(embed=embed, view=None)
                        return

                    embed = get_embed(
                        title="🔧 Delete VM/CT ID",
                        description=f"Select a VM/CT ID to remove from **{user_name}** (ID: {user_id}):",
                        color=discord.Color.orange()
                    )

                    vm_ct_select = Select(placeholder="Select a VM/CT ID...", options=vm_ct_options)

                    async def vm_ct_select_callback(interaction):
                        vm_ct_id = vm_ct_select.values[0]

                        embed = get_embed(
                            title="⚠️ Confirm Deletion",
                            description=f"Are you sure you want to remove VM/CT ID **{vm_ct_id}** from **{user_name}** (ID: {user_id})?",
                            color=discord.Color.red()
                        )

                        view = View()
                        back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                        confirm_button = Button(label="Confirm", style=discord.ButtonStyle.green)

                        async def back_to_vm_ct_select(interaction):
                            await user_vm_select_callback(interaction)

                        async def confirm_vm_ct_deletion(interaction):
                            config_data = load_config()
                            if config_data is None:
                                embed = get_embed("Error", "Failed to load configuration file.", discord.Color.red())
                                await interaction.response.edit_message(embed=embed, view=None)
                                return

                            if user_id in config_data["user"] and vm_ct_id in config_data["user"][user_id]["allowed_vms"]:
                                config_data["user"][user_id]["allowed_vms"].remove(vm_ct_id)
                                if not config_data["user"][user_id]["allowed_vms"]:
                                    del config_data["user"][user_id]
                                save_config(config_data)
                                logging.info(f"VM/CT ID deleted: ID={vm_ct_id}, from User={user_id}, Name={user_name}, by Admin={ctx.author.id}")


                                log_embed = discord.Embed(
                                    title="📝 User Configuration Log",
                                    color=discord.Color.blue(),
                                    timestamp=datetime.datetime.fromtimestamp(time.time())
                                )
                                log_embed.add_field(
                                    name="Admin",
                                    value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                                    inline=False
                                )
                                log_embed.add_field(
                                    name="Command Used",
                                    value="``/config``",
                                    inline=False
                                )
                                log_embed.add_field(
                                    name="Action",
                                    value=f"{ctx.author.display_name} used the ``/config`` command on {timestamp} to delete a VM/CT ID.",
                                    inline=False
                                )
                                log_embed.add_field(
                                    name="Affected User",
                                    value=f"{user_name} (ID: {user_id})",
                                    inline=False
                                )
                                log_embed.add_field(
                                    name="Deleted VM/CT ID",
                                    value=f"**{vm_ct_id}**",
                                    inline=False
                                )
                                await send_log_message(log_embed)

                                embed = get_embed(
                                    title="✅ Success",
                                    description=f"VM/CT ID **{vm_ct_id}** has been removed from **{user_name}** (ID: {user_id}).",
                                    color=discord.Color.green()
                                )
                                view = View()
                                back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                                back_button.callback = back_to_vm_ct_select
                                view.add_item(back_button)
                                await interaction.response.edit_message(embed=embed, view=view)
                            else:
                                embed = get_embed("Error", "VM/CT ID not found for this user.", discord.Color.red())
                                await interaction.response.edit_message(embed=embed, view=None)

                        back_button.callback = back_to_vm_ct_select
                        confirm_button.callback = confirm_vm_ct_deletion
                        view.add_item(back_button)
                        view.add_item(confirm_button)

                        await interaction.response.edit_message(embed=embed, view=view)

                    vm_ct_select.callback = vm_ct_select_callback
                    view = View()
                    view.add_item(vm_ct_select)
                    back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                    back_button.callback = show_delete_user_message
                    view.add_item(back_button)
                    await interaction.response.edit_message(embed=embed, view=view)

                user_vm_select.callback = user_vm_select_callback
                view = View()
                view.add_item(user_vm_select)
                back_button = Button(label="Back", style=discord.ButtonStyle.grey)
                back_button.callback = show_delete_user_message
                view.add_item(back_button)
                await interaction.response.edit_message(embed=embed, view=view)

        user_select.callback = user_select_callback
        view = View()
        view.add_item(user_select)
        back_button = Button(label="Back", style=discord.ButtonStyle.grey)
        back_button.callback = show_config_message
        view.add_item(back_button)
        await interaction.response.edit_message(embed=embed, view=view)

    async def select_callback(interaction):
        if select.values[0] == "delete_staff":
            await show_delete_staff_message(interaction)
        elif select.values[0] == "delete_user":
            await show_delete_user_message(interaction)

    select.callback = select_callback
    view = View()
    view.add_item(select)

    await ctx.reply(embed=embed, view=view)



@bot.command()
async def listcommands(ctx):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    is_admin = has_permission(ctx.author.id, "admin")

    commands_list = (
        "🌟 **Proxmox Bot Commands** 🌟\n"
        "Control your Proxmox server with ease:\n\n"
        
        "__📋 General Commands__\n"
        "```/listcommands```\n"
        "_Show this command list_\n"
        "`Usage:` /listcommands\n\n"
        "```/listnodes```\n"
        "_List all available nodes_\n"
        "`Usage:` /listnodes\n\n"
        
        "__🖥️ VM Management__\n"
        "```/listvms```\n"
        "_List VMs on a specific node_\n"
        "`Usage:` /listvms <node_name>\n\n"
        "```/vmavg```\n"
        "_Get average VM stats for a node_\n"
        "`Usage:` /vmavg <node_name>\n\n"
        "```/startvm```\n"
        "_Start a VM_\n"
        "`Usage:` /startvm <node_name> <vm_id>\n\n"
        "```/restartvm```\n"
        "_Restart a VM_\n"
        "`Usage:` /restartvm <node_name> <vm_id>\n\n"
        "```/stopvm```\n"
        "_Stop a VM_\n"
        "`Usage:` /stopvm <node_name> <vm_id>\n\n"
        
        "__📦 Container (CT) Management__\n"
        "```/listcts```\n"
        "_List containers on a specific node_\n"
        "`Usage:` /listcts <node_name>\n\n"
        "```/ctavg```\n"
        "_Get average CT stats for a node_\n"
        "`Usage:` /ctavg <node_name>\n\n"
        "```/startct```\n"
        "_Start a container_\n"
        "`Usage:` /startct <node_name> <ct_id>\n\n"
        "```/restartct```\n"
        "_Restart a container_\n"
        "`Usage:` /restartct <node_name> <ct_id>\n\n"
        "```/stopct```\n"
        "_Stop a container_\n"
        "`Usage:` /stopct <node_name> <ct_id>\n\n"
        
        "__ℹ️ Server Info__\n"
        "```/serverinfo```\n"
        "_Get detailed server stats_\n"
        "`Usage:` /serverinfo\n"
    )

    if is_admin:
        commands_list += (
            "\n__🔧 Admin Commands__\n"
            "```/setlog```\n"
            "_Set a channel as the log channel_\n"
            "`Usage:` /setlog [channel_id]\n\n"
            "```/deletelog```\n"
            "_Delete the configured log channel_\n"
            "`Usage:` /deletelog\n\n"
            "```/setuser```\n"
            "_Add a user with allowed VM/CT IDs_\n"
            "`Usage:` /setuser <user> <vm_ct_id>\n\n"
            "```/setstaff```\n"
            "_Add a new staff member_\n"
            "`Usage:` /setstaff <user>\n\n"
            "```/config```\n"
            "_Show and manage bot configuration_\n"
            "`Usage:` /config\n"
        )

    embed = get_embed(
        title="✨ Proxmox Command Hub ✨",
        description=commands_list,
        color=discord.Color.teal()
    )

    select = Select(
        placeholder="Browse categories...",
        options=[
            discord.SelectOption(label="General Commands", value="general", description="Basic bot commands", emoji="📋"),
            discord.SelectOption(label="VM Management", value="vm", description="Manage your VMs", emoji="🖥️"),
            discord.SelectOption(label="Container Management", value="ct", description="Manage your containers", emoji="📦"),
            discord.SelectOption(label="Server Info", value="server", description="Check server stats", emoji="ℹ️")
        ] + ([discord.SelectOption(label="Admin Commands", value="admin", description="Admin-only commands", emoji="🔧")] if is_admin else [])
    )

    async def select_callback(interaction):
        if select.values[0] == "general":
            desc = (
                "__📋 General Commands__\n"
                "```/listcommands```\n"
                "_Show this command list_\n"
                "`Usage:` /listcommands\n\n"
                "```/listnodes```\n"
                "_List all available nodes_\n"
                "`Usage:` /listnodes"
            )
        elif select.values[0] == "vm":
            desc = (
                "__🖥️ VM Management__\n"
                "```/listvms```\n"
                "_List VMs on a node_\n"
                "`Usage:` /listvms <node_name>\n\n"
                "```/vmavg```\n"
                "_Get average VM stats for a node_\n"
                "`Usage:` /vmavg <node_name>\n\n"
                "```/startvm```\n"
                "_Start a VM_\n"
                "`Usage:` /startvm <node_name> <vm_id>\n\n"
                "```/restartvm```\n"
                "_Restart a VM_\n"
                "`Usage:` /restartvm <node_name> <vm_id>\n\n"
                "```/stopvm```\n"
                "_Stop a VM_\n"
                "`Usage:` /stopvm <node_name> <vm_id>"
            )
        elif select.values[0] == "ct":
            desc = (
                "__📦 Container Management__\n"
                "```/listcts```\n"
                "_List containers on a node_\n"
                "`Usage:` /listcts <node_name>\n\n"
                "```/ctavg```\n"
                "_Get average CT stats for a node_\n"
                "`Usage:` /ctavg <node_name>\n\n"
                "```/startct```\n"
                "_Start a container_\n"
                "`Usage:` /startct <node_name> <ct_id>\n\n"
                "```/restartct```\n"
                "_Restart a container_\n"
                "`Usage:` /restartct <node_name> <ct_id>\n\n"
                "```/stopct```\n"
                "_Stop a container_\n"
                "`Usage:` /stopct <node_name> <ct_id>"
            )
        elif select.values[0] == "server":
            desc = (
                "__ℹ️ Server Info__\n"
                "```/serverinfo```\n"
                "_Get server stats_\n"
                "`Usage:` /serverinfo"
            )
        elif select.values[0] == "admin" and is_admin:
            desc = (
                "__🔧 Admin Commands__\n"
                "```/setlog```\n"
                "_Set a channel as the log channel_\n"
                "`Usage:` /setlog [channel_id]\n\n"
                "```/deletelog```\n"
                "_Delete the configured log channel_\n"
                "`Usage:` /deletelog\n\n"
                "```/setuser```\n"
                "_Add a user with allowed VM/CT IDs_\n"
                "`Usage:` /setuser <user> <vm_ct_id>\n\n"
                "```/setstaff```\n"
                "_Add a new staff member_\n"
                "`Usage:` /setstaff <user>\n\n"
                "```/config```\n"
                "_Show and manage bot configuration_\n"
                "`Usage:` /config"
            )
        else:
            desc = "🚫 Unauthorized or invalid selection."

        await interaction.response.edit_message(embed=get_embed(
            title="✨ Proxmox Command Hub ✨",
            description=desc,
            color=discord.Color.teal()
        ))

    select.callback = select_callback
    view = View()
    view.add_item(select)

    await ctx.reply(embed=embed, view=view)

@bot.command()
async def listnodes(ctx):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    try:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes Found", "No nodes are available on this server.", discord.Color.yellow()))
            return

        node_list = []
        for node in nodes:
            node_name = node.get("node", "Unnamed")
            status = "🟢 Online" if node.get("status", "unknown") == "online" else "🔴 Offline"
            uptime = f"{round(node.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in node else "N/A"
            
            try:
                vms = proxmox.nodes(node_name).qemu.get()
                vm_count = len(vms)
            except Exception:
                vm_count = "N/A"
            
            try:
                cts = proxmox.nodes(node_name).lxc.get()
                ct_count = len(cts)
            except Exception:
                ct_count = "N/A"


            node_list.append(
                f"**Node:** ```{node_name}```\n"
                f"Status: {status}\n"
                f"Uptime: {uptime}\n"
                f"VMs: {vm_count} | CTs: {ct_count}\n"
            )


        embed_max_length = 4000  
        embeds = []
        current_description = ""

        for node_info in node_list:
            if len(current_description) + len(node_info) + 2 > embed_max_length:
                embeds.append(get_embed(
                    title="✨ Node Overview ✨",
                    description=current_description,
                    color=discord.Color.teal()
                ))
                current_description = node_info
            else:
                if current_description:
                    current_description += "\n"
                current_description += node_info

        if current_description:
            embeds.append(get_embed(
                title="✨ Node Overview ✨",
                description=current_description,
                color=discord.Color.teal()
            ))

        for embed in embeds:
            await ctx.reply(embed=embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("🚨 Error", f"Something went wrong: {str(e)}", discord.Color.red()))


@bot.command()
async def listvms(ctx, node: str = None):
    """List and manage VMs on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return
        
        node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
        embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/listvms <node_name>`", discord.Color.orange())
        
        select = Select(placeholder="Select a node...", options=node_options[:25])  
        async def select_callback(interaction):
            selected_node = select.values[0]
            await listvms(ctx, selected_node)  
            await interaction.response.edit_message(embed=get_embed("Processing", f"Fetching VMs for `{selected_node}`...", discord.Color.teal()), view=None)
        
        select.callback = select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        vms = proxmox.nodes(node).qemu.get()
        if not vms:
            await ctx.reply(embed=get_embed(f"🚫 No VMs on {node}", f"The node `{node}` has no virtual machines.", discord.Color.yellow()))
            return

        vm_list = []
        vm_options = []
        for vm in vms:
            vm_name = vm.get("name", "Unnamed")
            vm_id = vm.get("vmid", "Unknown")
            vm_status = "🟢 Online" if vm["status"] == "running" else "🔴 Offline"
            vm_uptime = f"{round(vm.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in vm else "N/A"
            
            try:
                vm_status_data = proxmox.nodes(node).qemu(vm_id).status.current.get()
                vm_cpu_usage = f"{round(vm_status_data.get('cpu', 0) * 100, 1):.1f}%" if "cpu" in vm_status_data else "N/A"
                vm_memory_usage = f"{round(vm_status_data.get('mem', 0) / 1024 / 1024, 0)} MB" if "mem" in vm_status_data else "N/A"
            except Exception:
                vm_cpu_usage = "N/A"
                vm_memory_usage = "N/A"

            vm_list.append(
                f"**Name:** {vm_name}\n"
                f"**ID:** ```{vm_id}```\n"
                f"Status: {vm_status}\n"
                f"Uptime: {vm_uptime}\n"
                f"CPU Usage: {vm_cpu_usage} | Memory: {vm_memory_usage}\n"
            )
            vm_options.append(discord.SelectOption(label=f"{vm_name} ({vm_id})", value=str(vm_id), description=f"Status: {vm_status[2:]}"))

        
        embed_max_length = 4000
        embeds = []
        current_description = ""
        for vm_info in vm_list:
            if len(current_description) + len(vm_info) + 2 > embed_max_length:
                embeds.append(get_embed(
                    title=f"✨ VMs on Node: {node} ✨",
                    description=current_description,
                    color=discord.Color.teal()
                ))
                current_description = vm_info
            else:
                if current_description:
                    current_description += "\n"
                current_description += vm_info

        if current_description:
            embeds.append(get_embed(
                title=f"✨ VMs on Node: {node} ✨",
                description=current_description,
                color=discord.Color.teal()
            ))

        
        select = Select(
            placeholder="Select a VM to manage...",
            options=vm_options[:25]  
        )

        async def select_callback(interaction):
            vm_id = select.values[0]
            vm_name = next((vm["name"] for vm in vms if str(vm["vmid"]) == vm_id), "Unnamed")
            vm_status_data = proxmox.nodes(node).qemu(vm_id).status.current.get()
            vm_status = "🟢 Online" if vm_status_data["status"] == "running" else "🔴 Offline"
            vm_uptime = f"{round(vm_status_data.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in vm_status_data else "N/A"
            vm_cpu_usage = f"{round(vm_status_data.get('cpu', 0) * 100, 1):.1f}%"
            vm_memory_usage = f"{round(vm_status_data.get('mem', 0) / 1024 / 1024, 0)} MB"

            embed = get_embed(
                title=f"✨ VM Config: {vm_name} ✨",
                description=(
                    f"**ID:** ```{vm_id}```\n"
                    f"Status: {vm_status}\n"
                    f"Uptime: {vm_uptime}\n"
                    f"CPU Usage: {vm_cpu_usage} | Memory: {vm_memory_usage}"
                ),
                color=discord.Color.teal()
            )

            view = View()
            start_button = Button(label="Start", style=discord.ButtonStyle.green, custom_id="start")
            async def start_callback(interaction):
                if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
                    await interaction.response.send_message(embed=get_embed("Error", "You are not authorized to start this VM.", discord.Color.red()), ephemeral=True)
                    return
                vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
                if vm_status["status"] == "running":
                    await interaction.response.send_message(embed=get_embed("Error", "VM is already running.", discord.Color.red()), ephemeral=True)
                    return
                if vm_status.get("lock"):
                    proxmox.nodes(node).qemu(vm_id).status.unlock.post()
                proxmox.nodes(node).qemu(vm_id).status.start.post()
                await interaction.response.edit_message(embed=get_embed("Success", f"🎉 VM `{vm_id}` started!", discord.Color.green()))


                log_embed = discord.Embed(
                    title="📝 VM Operation Log",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.fromtimestamp(time.time())
                )
                log_embed.add_field(
                    name="User",
                    value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                    inline=False
                )
                log_embed.add_field(
                    name="Command Used",
                    value="``/listvms``",
                    inline=False
                )
                log_embed.add_field(
                    name="Action",
                    value=f"{ctx.author.display_name} used the ``/listvms`` command on {timestamp} to start a VM.",
                    inline=False
                )
                log_embed.add_field(
                    name="Node",
                    value=f"`{node}`",
                    inline=False
                )
                log_embed.add_field(
                    name="VM ID",
                    value=f"`{vm_id}`",
                    inline=False
                )
                await send_log_message(log_embed)

            restart_button = Button(label="Restart", style=discord.ButtonStyle.blurple, custom_id="restart")
            async def restart_callback(interaction):
                if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
                    await interaction.response.send_message(embed=get_embed("Error", "You are not authorized to restart this VM.", discord.Color.red()), ephemeral=True)
                    return
                vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
                if vm_status["status"] != "running":
                    await interaction.response.send_message(embed=get_embed("Error", "VM is not running, cannot restart.", discord.Color.red()), ephemeral=True)
                    return
                if vm_status.get("lock"):
                    proxmox.nodes(node).qemu(vm_id).status.unlock.post()
                proxmox.nodes(node).qemu(vm_id).status.stop.post()
                await asyncio.sleep(2)
                proxmox.nodes(node).qemu(vm_id).status.start.post()
                await interaction.response.edit_message(embed=get_embed("Success", f"🎉 VM `{vm_id}` restarted!", discord.Color.green()))


                log_embed = discord.Embed(
                    title="📝 VM Operation Log",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.fromtimestamp(time.time())
                )
                log_embed.add_field(
                    name="User",
                    value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                    inline=False
                )
                log_embed.add_field(
                    name="Command Used",
                    value="``/listvms``",
                    inline=False
                )
                log_embed.add_field(
                    name="Action",
                    value=f"{ctx.author.display_name} used the ``/listvms`` command on {timestamp} to restart a VM.",
                    inline=False
                )
                log_embed.add_field(
                    name="Node",
                    value=f"`{node}`",
                    inline=False
                )
                log_embed.add_field(
                    name="VM ID",
                    value=f"`{vm_id}`",
                    inline=False
                )
                await send_log_message(log_embed)

            stop_button = Button(label="Stop", style=discord.ButtonStyle.red, custom_id="stop")
            async def stop_callback(interaction):
                if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
                    await interaction.response.send_message(embed=get_embed("Error", "You are not authorized to stop this VM.", discord.Color.red()), ephemeral=True)
                    return
                vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
                if vm_status["status"] != "running":
                    await interaction.response.send_message(embed=get_embed("Error", "VM is not running, cannot stop.", discord.Color.red()), ephemeral=True)
                    return
                if vm_status.get("lock"):
                    proxmox.nodes(node).qemu(vm_id).status.unlock.post()
                proxmox.nodes(node).qemu(vm_id).status.stop.post()
                await interaction.response.edit_message(embed=get_embed("Success", f"🎉 VM `{vm_id}` stopped!", discord.Color.green()))


                log_embed = discord.Embed(
                    title="📝 VM Operation Log",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.fromtimestamp(time.time())
                )
                log_embed.add_field(
                    name="User",
                    value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                    inline=False
                )
                log_embed.add_field(
                    name="Command Used",
                    value="``/listvms``",
                    inline=False
                )
                log_embed.add_field(
                    name="Action",
                    value=f"{ctx.author.display_name} used the ``/listvms`` command on {timestamp} to stop a VM.",
                    inline=False
                )
                log_embed.add_field(
                    name="Node",
                    value=f"`{node}`",
                    inline=False
                )
                log_embed.add_field(
                    name="VM ID",
                    value=f"`{vm_id}`",
                    inline=False
                )
                await send_log_message(log_embed)

            start_button.callback = start_callback
            restart_button.callback = restart_callback
            stop_button.callback = stop_callback
            view.add_item(start_button)
            view.add_item(restart_button)
            view.add_item(stop_button)

            await interaction.response.edit_message(embed=embed, view=view)

        select.callback = select_callback
        view = View()
        view.add_item(select)

        for embed in embeds:
            await ctx.reply(embed=embed, view=view if embed == embeds[-1] else None)

    except Exception as e:
        await ctx.reply(embed=get_embed("🚨 Error", f"Something went wrong: {str(e)}", discord.Color.red()))

@bot.command()
async def listcts(ctx, node: str = None):
    """List and manage CTs on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return
        
        node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
        embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/listcts <node_name>`", discord.Color.orange())
        
        select = Select(placeholder="Select a node...", options=node_options[:25])  
        async def select_callback(interaction):
            selected_node = select.values[0]
            await listcts(ctx, selected_node)  
            await interaction.response.edit_message(embed=get_embed("Processing", f"Fetching CTs for `{selected_node}`...", discord.Color.teal()), view=None)
        
        select.callback = select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        cts = proxmox.nodes(node).lxc.get()
        if not cts:
            await ctx.reply(embed=get_embed(f"🚫 No CTs on {node}", f"The node `{node}` has no containers.", discord.Color.yellow()))
            return

        ct_list = []
        ct_options = []
        for ct in cts:
            ct_name = ct.get("name", "Unnamed")
            ct_id = ct.get("vmid", "Unknown")
            ct_status = "🟢 Online" if ct["status"] == "running" else "🔴 Offline"
            ct_uptime = f"{round(ct.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in ct else "N/A"
            
            try:
                ct_status_data = proxmox.nodes(node).lxc(ct_id).status.current.get()
                ct_cpu_usage = f"{round(ct_status_data.get('cpu', 0) * 100, 1):.1f}%" if "cpu" in ct_status_data else "N/A"
                ct_memory_usage = f"{round(ct_status_data.get('mem', 0) / 1024 / 1024, 0)} MB" if "mem" in ct_status_data else "N/A"
            except Exception:
                ct_cpu_usage = "N/A"
                ct_memory_usage = "N/A"

            ct_list.append(
                f"**Name:** {ct_name}\n"
                f"**ID:** ```{ct_id}```\n"
                f"Status: {ct_status}\n"
                f"Uptime: {ct_uptime}\n"
                f"CPU Usage: {ct_cpu_usage} | Memory: {ct_memory_usage}\n"
            )
            ct_options.append(discord.SelectOption(label=f"{ct_name} ({ct_id})", value=str(ct_id), description=f"Status: {ct_status[2:]}"))

        
        embed_max_length = 4000
        embeds = []
        current_description = ""
        for ct_info in ct_list:
            if len(current_description) + len(ct_info) + 2 > embed_max_length:
                embeds.append(get_embed(
                    title=f"✨ CTs on Node: {node} ✨",
                    description=current_description,
                    color=discord.Color.teal()
                ))
                current_description = ct_info
            else:
                if current_description:
                    current_description += "\n"
                current_description += ct_info

        if current_description:
            embeds.append(get_embed(
                title=f"✨ CTs on Node: {node} ✨",
                description=current_description,
                color=discord.Color.teal()
            ))

        
        select = Select(
            placeholder="Select a CT to manage...",
            options=ct_options[:25]  
        )

        async def select_callback(interaction):
            ct_id = select.values[0]
            ct_name = next((ct["name"] for ct in cts if str(ct["vmid"]) == ct_id), "Unnamed")
            ct_status_data = proxmox.nodes(node).lxc(ct_id).status.current.get()
            ct_status = "🟢 Online" if ct_status_data["status"] == "running" else "🔴 Offline"
            ct_uptime = f"{round(ct_status_data.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in ct_status_data else "N/A"
            ct_cpu_usage = f"{round(ct_status_data.get('cpu', 0) * 100, 1):.1f}%"
            ct_memory_usage = f"{round(ct_status_data.get('mem', 0) / 1024 / 1024, 0)} MB"

            embed = get_embed(
                title=f"✨ CT Config: {ct_name} ✨",
                description=(
                    f"**ID:** ```{ct_id}```\n"
                    f"Status: {ct_status}\n"
                    f"Uptime: {ct_uptime}\n"
                    f"CPU Usage: {ct_cpu_usage} | Memory: {ct_memory_usage}"
                ),
                color=discord.Color.teal()
            )

            view = View()
            
            start_button = Button(label="Start", style=discord.ButtonStyle.green, custom_id="start")
            async def start_callback(interaction):
                if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
                    await interaction.response.send_message(embed=get_embed("Error", "You are not authorized to start this CT.", discord.Color.red()), ephemeral=True)
                    return
                ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
                if ct_status["status"] == "running":
                    await interaction.response.send_message(embed=get_embed("Error", "CT is already running.", discord.Color.red()), ephemeral=True)
                    return
                if ct_status.get("lock"):
                    proxmox.nodes(node).lxc(ct_id).status.unlock.post()
                proxmox.nodes(node).lxc(ct_id).status.start.post()
                await interaction.response.edit_message(embed=get_embed("Success", f"🎉 CT `{ct_id}` started!", discord.Color.green()))


                log_embed = discord.Embed(
                    title="📝 CT Operation Log",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.fromtimestamp(time.time())
                )
                log_embed.add_field(
                    name="User",
                    value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                    inline=False
                )
                log_embed.add_field(
                    name="Command Used",
                    value="``/listcts``",
                    inline=False
                )
                log_embed.add_field(
                    name="Action",
                    value=f"{ctx.author.display_name} used the ``/listcts`` command on {timestamp} to start a container.",
                    inline=False
                )
                log_embed.add_field(
                    name="Node",
                    value=f"`{node}`",
                    inline=False
                )
                log_embed.add_field(
                    name="CT ID",
                    value=f"`{ct_id}`",
                    inline=False
                )
                await send_log_message(log_embed)

            
            restart_button = Button(label="Restart", style=discord.ButtonStyle.blurple, custom_id="restart")
            async def restart_callback(interaction):
                if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
                    await interaction.response.send_message(embed=get_embed("Error", "You are not authorized to restart this CT.", discord.Color.red()), ephemeral=True)
                    return
                ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
                if ct_status["status"] != "running":
                    await interaction.response.send_message(embed=get_embed("Error", "CT is not running, cannot restart.", discord.Color.red()), ephemeral=True)
                    return
                if ct_status.get("lock"):
                    proxmox.nodes(node).lxc(ct_id).status.unlock.post()
                proxmox.nodes(node).lxc(ct_id).status.stop.post()
                await asyncio.sleep(2)
                proxmox.nodes(node).lxc(ct_id).status.start.post()
                await interaction.response.edit_message(embed=get_embed("Success", f"🎉 CT `{ct_id}` restarted!", discord.Color.green()))


                log_embed = discord.Embed(
                    title="📝 CT Operation Log",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.fromtimestamp(time.time())
                )
                log_embed.add_field(
                    name="User",
                    value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                    inline=False
                )
                log_embed.add_field(
                    name="Command Used",
                    value="``/listcts``",
                    inline=False
                )
                log_embed.add_field(
                    name="Action",
                    value=f"{ctx.author.display_name} used the ``/listcts`` command on {timestamp} to restart a container.",
                    inline=False
                )
                log_embed.add_field(
                    name="Node",
                    value=f"`{node}`",
                    inline=False
                )
                log_embed.add_field(
                    name="CT ID",
                    value=f"`{ct_id}`",
                    inline=False
                )
                await send_log_message(log_embed)

            
            stop_button = Button(label="Stop", style=discord.ButtonStyle.red, custom_id="stop")
            async def stop_callback(interaction):
                if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
                    await interaction.response.send_message(embed=get_embed("Error", "You are not authorized to stop this CT.", discord.Color.red()), ephemeral=True)
                    return
                ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
                if ct_status["status"] != "running":
                    await interaction.response.send_message(embed=get_embed("Error", "CT is not running, cannot stop.", discord.Color.red()), ephemeral=True)
                    return
                if ct_status.get("lock"):
                    proxmox.nodes(node).lxc(ct_id).status.unlock.post()
                proxmox.nodes(node).lxc(ct_id).status.stop.post()
                await interaction.response.edit_message(embed=get_embed("Success", f"🎉 CT `{ct_id}` stopped!", discord.Color.green()))


                log_embed = discord.Embed(
                    title="📝 CT Operation Log",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.fromtimestamp(time.time())
                )
                log_embed.add_field(
                    name="User",
                    value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
                    inline=False
                )
                log_embed.add_field(
                    name="Command Used",
                    value="``/listcts``",
                    inline=False
                )
                log_embed.add_field(
                    name="Action",
                    value=f"{ctx.author.display_name} used the ``/listcts`` command on {timestamp} to stop a container.",
                    inline=False
                )
                log_embed.add_field(
                    name="Node",
                    value=f"`{node}`",
                    inline=False
                )
                log_embed.add_field(
                    name="CT ID",
                    value=f"`{ct_id}`",
                    inline=False
                )
                await send_log_message(log_embed)

            start_button.callback = start_callback
            restart_button.callback = restart_callback
            stop_button.callback = stop_callback
            view.add_item(start_button)
            view.add_item(restart_button)
            view.add_item(stop_button)

            await interaction.response.edit_message(embed=embed, view=view)

        select.callback = select_callback
        view = View()
        view.add_item(select)

        for embed in embeds:
            await ctx.reply(embed=embed, view=view if embed == embeds[-1] else None)

    except Exception as e:
        await ctx.reply(embed=get_embed("🚨 Error", f"Something went wrong: {str(e)}", discord.Color.red()))


@bot.command()
async def startvm(ctx, node: str = None, vm_id: str = None):
    """Start a VM on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None or vm_id is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return

        if node is None:
            node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
            embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/startvm <node_name> <vm_id>`", discord.Color.orange())
            select = Select(placeholder="Select a node...", options=node_options[:25])
            
            async def node_select_callback(interaction):
                selected_node = select.values[0]
                await interaction.response.send_message(embed=get_embed("Processing", f"Selected node: `{selected_node}`...", discord.Color.teal()), ephemeral=True)
                await startvm(ctx, selected_node, None)
            
            select.callback = node_select_callback
            view = View()
            view.add_item(select)
            await ctx.reply(embed=embed, view=view)
            return

        vms = proxmox.nodes(node).qemu.get()
        if not vms:
            await ctx.reply(embed=get_embed(f"🚫 No VMs on {node}", f"The node `{node}` has no virtual machines.", discord.Color.yellow()))
            return
        
        vm_options = [discord.SelectOption(label=f"{vm.get('name', 'Unnamed')} ({vm['vmid']})", value=str(vm["vmid"])) for vm in vms]
        embed = get_embed("🚫 Usage Error", f"You must provide a VM ID for node `{node}`.\nExample: `/startvm {node} <vm_id>`", discord.Color.orange())
        select = Select(placeholder="Select a VM to start...", options=vm_options[:25])
        
        async def vm_select_callback(interaction):
            selected_vm_id = select.values[0]
            await interaction.response.send_message(embed=get_embed("Processing", f"Starting VM `{selected_vm_id}` on `{node}`...", discord.Color.teal()), ephemeral=True)
            await startvm(ctx, node, selected_vm_id)
        
        select.callback = vm_select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        
        if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
            await ctx.reply(embed=get_embed("Error", "You are not authorized to start this VM.", discord.Color.red()))
            return
        
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


        log_embed = discord.Embed(
            title="📝 VM Operation Log",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="User",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/startvm``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} used the ``/startvm`` command on {timestamp} to start a VM.",
            inline=False
        )
        log_embed.add_field(
            name="Node",
            value=f"`{node}`",
            inline=False
        )
        log_embed.add_field(
            name="VM ID",
            value=f"`{vm_id}`",
            inline=False
        )
        await send_log_message(log_embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))

@bot.command()
async def restartvm(ctx, node: str = None, vm_id: str = None):
    """Restart a VM on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None or vm_id is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return

        if node is None:
            node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
            embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/restartvm <node_name> <vm_id>`", discord.Color.orange())
            select = Select(placeholder="Select a node...", options=node_options[:25])
            
            async def node_select_callback(interaction):
                selected_node = select.values[0]
                await interaction.response.send_message(embed=get_embed("Processing", f"Selected node: `{selected_node}`...", discord.Color.teal()), ephemeral=True)
                await restartvm(ctx, selected_node, None)
            
            select.callback = node_select_callback
            view = View()
            view.add_item(select)
            await ctx.reply(embed=embed, view=view)
            return

        vms = proxmox.nodes(node).qemu.get()
        if not vms:
            await ctx.reply(embed=get_embed(f"🚫 No VMs on {node}", f"The node `{node}` has no virtual machines.", discord.Color.yellow()))
            return
        
        vm_options = [discord.SelectOption(label=f"{vm.get('name', 'Unnamed')} ({vm['vmid']})", value=str(vm["vmid"])) for vm in vms]
        embed = get_embed("🚫 Usage Error", f"You must provide a VM ID for node `{node}`.\nExample: `/restartvm {node} <vm_id>`", discord.Color.orange())
        select = Select(placeholder="Select a VM to restart...", options=vm_options[:25])
        
        async def vm_select_callback(interaction):
            selected_vm_id = select.values[0]
            await interaction.response.send_message(embed=get_embed("Processing", f"Restarting VM `{selected_vm_id}` on `{node}`...", discord.Color.teal()), ephemeral=True)
            await restartvm(ctx, node, selected_vm_id)
        
        select.callback = vm_select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        
        if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
            await ctx.reply(embed=get_embed("Error", "You are not authorized to restart this VM.", discord.Color.red()))
            return
        
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


        log_embed = discord.Embed(
            title="📝 VM Operation Log",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="User",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/restartvm``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} used the ``/restartvm`` command on {timestamp} to restart a VM.",
            inline=False
        )
        log_embed.add_field(
            name="Node",
            value=f"`{node}`",
            inline=False
        )
        log_embed.add_field(
            name="VM ID",
            value=f"`{vm_id}`",
            inline=False
        )
        await send_log_message(log_embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def stopvm(ctx, node: str = None, vm_id: str = None):
    """Stop a VM on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None or vm_id is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return

        if node is None:
            node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
            embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/stopvm <node_name> <vm_id>`", discord.Color.orange())
            select = Select(placeholder="Select a node...", options=node_options[:25])
            
            async def node_select_callback(interaction):
                selected_node = select.values[0]
                await interaction.response.send_message(embed=get_embed("Processing", f"Selected node: `{selected_node}`...", discord.Color.teal()), ephemeral=True)
                await stopvm(ctx, selected_node, None)
            
            select.callback = node_select_callback
            view = View()
            view.add_item(select)
            await ctx.reply(embed=embed, view=view)
            return

        vms = proxmox.nodes(node).qemu.get()
        if not vms:
            await ctx.reply(embed=get_embed(f"🚫 No VMs on {node}", f"The node `{node}` has no virtual machines.", discord.Color.yellow()))
            return
        
        vm_options = [discord.SelectOption(label=f"{vm.get('name', 'Unnamed')} ({vm['vmid']})", value=str(vm["vmid"])) for vm in vms]
        embed = get_embed("🚫 Usage Error", f"You must provide a VM ID for node `{node}`.\nExample: `/stopvm {node} <vm_id>`", discord.Color.orange())
        select = Select(placeholder="Select a VM to stop...", options=vm_options[:25])
        
        async def vm_select_callback(interaction):
            selected_vm_id = select.values[0]
            await interaction.response.send_message(embed=get_embed("Processing", f"Stopping VM `{selected_vm_id}` on `{node}`...", discord.Color.teal()), ephemeral=True)
            await stopvm(ctx, node, selected_vm_id)
        
        select.callback = vm_select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        vm_status = proxmox.nodes(node).qemu(vm_id).status.current.get()
        
        if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", vm_id):
            await ctx.reply(embed=get_embed("Error", "You are not authorized to stop this VM.", discord.Color.red()))
            return
        
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


        log_embed = discord.Embed(
            title="📝 VM Operation Log",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="User",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/stopvm``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} used the ``/stopvm`` command on {timestamp} to stop a VM.",
            inline=False
        )
        log_embed.add_field(
            name="Node",
            value=f"`{node}`",
            inline=False
        )
        log_embed.add_field(
            name="VM ID",
            value=f"`{vm_id}`",
            inline=False
        )
        await send_log_message(log_embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))

@bot.command()
async def serverinfo(ctx):
    """Display detailed server information for all Proxmox nodes."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    try:
        ensure_proxmox_connection()
        nodes = proxmox.nodes.get()
        info_list = []
        total_vms_cpu_usage = total_vms_memory_usage = total_cts_memory_usage = 0
        total_vms_count = total_cts_count = 0

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

        for node in nodes:
            node_name = node.get("node", "N/A")
            try:
                node_status = proxmox.nodes(node_name).status.get()
                online_status = "Online" if node_status else "N/A"
                cpu_usage = f"{round(node_status.get('cpu', 0) * 100, 1):.1f}%"
                memory_used = f"{round(node_status['memory']['used'] / 1024 / 1024 / 1024, 1):.1f}" if "memory" in node_status else "N/A"
                memory_total = f"{round(node_status['memory']['total'] / 1024 / 1024 / 1024, 1):.1f}" if "memory" in node_status else "N/A"
                uptime = f"{round(node_status['uptime'] / 3600, 1):.1f} hours" if "uptime" in node_status else "N/A"

                storage_list = []
                storages = proxmox.nodes(node_name).storage.get()
                for storage in storages:
                    used_gb = round(storage.get("used", 0) / 1024 / 1024 / 1024, 1)
                    total_gb = round(storage.get("total", 0) / 1024 / 1024 / 1024, 1)
                    usage_percent = (used_gb / total_gb * 100) if total_gb > 0 else 0
                    if usage_percent <= 70:
                        status_emoji = "🟢"
                    elif usage_percent <= 90:
                        status_emoji = "🟡"
                    else:
                        status_emoji = "🔴"
                    storage_list.append(
                        f"**{storage['storage']}**: {used_gb} GB / {total_gb} GB ({round(usage_percent, 1)}%) {status_emoji}"
                    )

                try:
                    net_io = psutil.net_io_counters()
                    network_stats = f"Received: {net_io.bytes_recv // (1024 ** 2)} MB, Sent: {net_io.bytes_sent // (1024 ** 2)} MB"
                except Exception:
                    network_stats = "N/A"

                google_ping = calculate_avg_ping("google.com")
                kinopoisk_ping = calculate_avg_ping("kinopoisk.ru")
                ping_results = []
                if google_ping is not None and kinopoisk_ping is not None:
                    overall_avg_ping = round((google_ping + kinopoisk_ping) / 2, 1)
                    stability = "Stable" if overall_avg_ping < 100 else "Unstable"
                    ping_results.append(f"Ping: {overall_avg_ping} ms ({stability})")
                else:
                    ping_results.append("Ping: N/A")

                
                vms = proxmox.nodes(node_name).qemu.get()
                vm_list = []
                running_vms = 0
                for vm in vms:
                    vm_name = vm.get("name", "Unnamed")
                    vm_id = vm.get("vmid", "Unknown")
                    vm_status = "🟢" if vm["status"] == "running" else "🔴"
                    if vm["status"] == "running":
                        running_vms += 1
                    vm_uptime = f"{round(vm.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in vm else "N/A"
                    try:
                        vm_status_data = proxmox.nodes(node_name).qemu(vm_id).status.current.get()
                        vm_cpu_usage = round(vm_status_data.get("cpu", 0) * 100, 1) if "cpu" in vm_status_data else 0
                        vm_memory_usage = round(vm_status_data.get("mem", 0) / 1024 / 1024, 0) if "mem" in vm_status_data else 0
                    except Exception:
                        vm_cpu_usage = 0
                        vm_memory_usage = 0

                    total_vms_cpu_usage += vm_cpu_usage
                    total_vms_memory_usage += vm_memory_usage
                    total_vms_count += 1

                    vm_list.append(
                        f"**{vm_name}** {vm_status}\n"
                        f"**VM ID:** ```{vm_id}```\n"
                        f"Uptime: {vm_uptime}\n"
                        f"CPU Usage: {vm_cpu_usage:.1f}%, Memory Usage: {vm_memory_usage} MB"
                    )

                
                cts = proxmox.nodes(node_name).lxc.get()
                ct_list = []
                running_cts = 0
                for ct in cts:
                    ct_name = ct.get("name", "Unnamed")
                    ct_id = ct.get("vmid", "Unknown")
                    ct_status = "🟢" if ct["status"] == "running" else "🔴"
                    if ct["status"] == "running":
                        running_cts += 1
                    ct_uptime = f"{round(ct.get('uptime', 0) / 3600, 1):.1f} hours" if "uptime" in ct else "N/A"
                    try:
                        ct_status_data = proxmox.nodes(node_name).lxc(ct_id).status.current.get()
                        ct_cpu_usage = round(ct_status_data.get("cpu", 0) * 100, 1) if "cpu" in ct_status_data else 0
                        ct_memory_usage = round(ct_status_data.get("mem", 0) / 1024 / 1024, 0) if "mem" in ct_status_data else 0
                    except Exception:
                        ct_cpu_usage = 0
                        ct_memory_usage = 0

                    total_cts_memory_usage += ct_memory_usage
                    total_cts_count += 1

                    ct_list.append(
                        f"**{ct_name}** {ct_status}\n"
                        f"**CT ID:** ```{ct_id}```\n"
                        f"Uptime: {ct_uptime}\n"
                        f"CPU Usage: {ct_cpu_usage:.1f}%, Memory Usage: {ct_memory_usage} MB"
                    )

                
                node_info = (
                    f"**Node:** {node_name} ({online_status})\n\n"
                    f"**CPU Usage:** {cpu_usage}\n"
                    f"**Memory:** {memory_used} GB / {memory_total} GB\n"
                    f"**Uptime:** {uptime}\n"
                    f"**Network:** {network_stats}\n"
                    f"**Ping:** {' '.join(ping_results)}\n\n"
                    f"**Storage:**\n" + "\n".join(storage_list) + "\n\n"
                )

                
                vm_embeds = []
                current_vm_description = ""
                if vm_list:
                    for vm_info in vm_list:
                        if len(current_vm_description) + len(vm_info) + 2 > 1000:  
                            vm_embeds.append(f"**VMs ({running_vms}/{len(vms)} running):**\n{current_vm_description}")
                            current_vm_description = vm_info
                        else:
                            if current_vm_description:
                                current_vm_description += "\n\n"
                            current_vm_description += vm_info
                    if current_vm_description:
                        vm_embeds.append(f"**VMs ({running_vms}/{len(vms)} running):**\n{current_vm_description}")
                else:
                    vm_embeds.append("**VMs (0/0 running):** None")

                
                ct_embeds = []
                current_ct_description = ""
                if ct_list:
                    for ct_info in ct_list:
                        if len(current_ct_description) + len(ct_info) + 2 > 1000:  
                            ct_embeds.append(f"**CTs ({running_cts}/{len(cts)} running):**\n{current_ct_description}")
                            current_ct_description = ct_info
                        else:
                            if current_ct_description:
                                current_ct_description += "\n\n"
                            current_ct_description += ct_info
                    if current_ct_description:
                        ct_embeds.append(f"**CTs ({running_cts}/{len(cts)} running):**\n{current_ct_description}")
                else:
                    ct_embeds.append("**CTs (0/0 running):** None")

                
                vm_avg_stats = (
                    f"**VMs Average:**\n"
                    f"CPU Usage: {round(total_vms_cpu_usage / total_vms_count, 1) if total_vms_count > 0 else '0.0'}%\n"
                    f"Memory Usage: {round(total_vms_memory_usage / total_vms_count, 0) if total_vms_count > 0 else '0'} MB\n\n"
                )
                ct_avg_stats = (
                    f"**CTs Average:**\n"
                    f"CPU Usage: {round(total_vms_cpu_usage / total_cts_count, 1) if total_cts_count > 0 else '0.0'}%\n"
                    f"Memory Usage: {round(total_cts_memory_usage / total_cts_count, 0) if total_cts_count > 0 else '0'} MB"
                )

                
                for i, (vm_part, ct_part) in enumerate(zip(vm_embeds, ct_embeds + [None] * (len(vm_embeds) - len(ct_embeds)))):
                    info_part = node_info if i == 0 else ""  
                    info_part += vm_part + "\n\n"
                    if ct_part:
                        info_part += ct_part + "\n\n"
                    if i == 0:  
                        info_part += vm_avg_stats + ct_avg_stats
                    info_list.append(info_part)

            except Exception as e:
                info_list.append(f"**Node:** {node_name}\n**Error retrieving data:** {str(e)}")

        
        embed_max_length = 4000
        embeds = []
        current_description = ""

        for info in info_list:
            if len(current_description) + len(info) + 2 > embed_max_length:
                embed = discord.Embed(
                    title="✨ Server Info ✨",  
                    description=current_description,
                    color=discord.Color.teal()
                )
                embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
                embeds.append(embed)
                current_description = info
            else:
                if current_description:
                    current_description += "\n\n"
                current_description += info

        if current_description:
            embed = discord.Embed(
                title="✨ Server Info ✨",  #
                description=current_description,
                color=discord.Color.teal()
            )
            embed.set_footer(text=f"Made by Bence | {time.strftime('%Y-%m-%d %H:%M:%S')}")
            embeds.append(embed)

        for embed in embeds:
            await ctx.reply(embed=embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def vmavg(ctx, node: str = None):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    if node is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return
        
        node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
        embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/vmavg <node_name>`", discord.Color.orange())
        
        select = Select(placeholder="Select a node...", options=node_options[:25])  
        async def select_callback(interaction):
            selected_node = select.values[0]
            await vmavg(ctx, selected_node)  
            await interaction.response.edit_message(embed=get_embed("Processing", f"Fetching VM averages for `{selected_node}`...", discord.Color.teal()), view=None)
        
        select.callback = select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        vms = proxmox.nodes(node).qemu.get()
        if not vms:
            await ctx.reply(embed=get_embed(f"🚫 No VMs on {node}", f"The node `{node}` has no virtual machines.", discord.Color.yellow()))
            return

        total_vms_cpu_usage = 0
        total_vms_memory_usage = 0
        total_vms_count = 0
        online_vms_count = 0

        for vm in vms:
            vm_id = vm.get("vmid", "Unknown")
            try:
                vm_status_data = proxmox.nodes(node).qemu(vm_id).status.current.get()
                vm_cpu_usage = round(vm_status_data.get("cpu", 0) * 100, 1) if "cpu" in vm_status_data else 0
                vm_memory_usage = round(vm_status_data.get("mem", 0) / 1024 / 1024, 0) if "mem" in vm_status_data else 0
                if vm_status_data["status"] == "running":
                    online_vms_count += 1
            except Exception:
                vm_cpu_usage = 0
                vm_memory_usage = 0

            total_vms_cpu_usage += vm_cpu_usage
            total_vms_memory_usage += vm_memory_usage
            total_vms_count += 1

        avg_vms_cpu = f"{round(total_vms_cpu_usage / total_vms_count, 1):.1f}%" if total_vms_count > 0 else "N/A"
        avg_vms_memory = f"{round(total_vms_memory_usage / total_vms_count, 0):.0f} MB" if total_vms_count > 0 else "N/A"

        avg_info = (
            f"Average VM Usage on Node: ```{node}```\n"
            f"CPU Usage: {avg_vms_cpu}\n"
            f"Memory Usage: {avg_vms_memory}\n"
            f"Total VMs: {total_vms_count} (Online: {online_vms_count})"
        )

        await ctx.reply(embed=get_embed(
            title="✨ VM Average Stats ✨",
            description=avg_info,
            color=discord.Color.teal()
        ))

    except Exception as e:
        await ctx.reply(embed=get_embed("🚨 Error", f"Something went wrong: {str(e)}", discord.Color.red()))





@bot.command()
async def ctavg(ctx, node: str = None):
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()

    if node is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return
        
        node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
        embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/ctavg <node_name>`", discord.Color.orange())
        
        select = Select(placeholder="Select a node...", options=node_options[:25])  
        async def select_callback(interaction):
            selected_node = select.values[0]
            await ctavg(ctx, selected_node)  
            await interaction.response.edit_message(embed=get_embed("Processing", f"Fetching CT averages for `{selected_node}`...", discord.Color.teal()), view=None)
        
        select.callback = select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        cts = proxmox.nodes(node).lxc.get()
        if not cts:
            await ctx.reply(embed=get_embed(f"🚫 No CTs on {node}", f"The node `{node}` has no containers.", discord.Color.yellow()))
            return

        total_cts_cpu_usage = 0
        total_cts_memory_usage = 0
        total_cts_count = 0
        online_cts_count = 0

        for ct in cts:
            ct_id = ct.get("vmid", "Unknown")
            try:
                ct_status_data = proxmox.nodes(node).lxc(ct_id).status.current.get()
                ct_cpu_usage = round(ct_status_data.get("cpu", 0) * 100, 1) if "cpu" in ct_status_data else 0
                ct_memory_usage = round(ct_status_data.get("mem", 0) / 1024 / 1024, 0) if "mem" in ct_status_data else 0
                if ct_status_data["status"] == "running":
                    online_cts_count += 1
            except Exception:
                ct_cpu_usage = 0
                ct_memory_usage = 0

            total_cts_cpu_usage += ct_cpu_usage
            total_cts_memory_usage += ct_memory_usage
            total_cts_count += 1

        avg_cts_cpu = f"{round(total_cts_cpu_usage / total_cts_count, 1):.1f}%" if total_cts_count > 0 else "N/A"
        avg_cts_memory = f"{round(total_cts_memory_usage / total_cts_count, 0):.0f} MB" if total_cts_count > 0 else "N/A"

        avg_info = (
            f"Average CT Usage on Node: ```{node}```\n"
            f"CPU Usage: {avg_cts_cpu}\n"
            f"Memory Usage: {avg_cts_memory}\n"
            f"Total CTs: {total_cts_count} (Online: {online_cts_count})"
        )

        await ctx.reply(embed=get_embed(
            title="✨ CT Average Stats ✨",
            description=avg_info,
            color=discord.Color.teal()
        ))

    except Exception as e:
        await ctx.reply(embed=get_embed("🚨 Error", f"Something went wrong: {str(e)}", discord.Color.red()))



@bot.command()
async def startct(ctx, node: str = None, ct_id: str = None):
    """Start an LXC container on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None or ct_id is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return

        if node is None:
            node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
            embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/startct <node_name> <ct_id>`", discord.Color.orange())
            select = Select(placeholder="Select a node...", options=node_options[:25])
            
            async def node_select_callback(interaction):
                selected_node = select.values[0]
                await interaction.response.send_message(embed=get_embed("Processing", f"Selected node: `{selected_node}`...", discord.Color.teal()), ephemeral=True)
                await startct(ctx, selected_node, None)
            
            select.callback = node_select_callback
            view = View()
            view.add_item(select)
            await ctx.reply(embed=embed, view=view)
            return

        cts = proxmox.nodes(node).lxc.get()
        if not cts:
            await ctx.reply(embed=get_embed(f"🚫 No CTs on {node}", f"The node `{node}` has no containers.", discord.Color.yellow()))
            return
        
        ct_options = [discord.SelectOption(label=f"{ct.get('name', 'Unnamed')} ({ct['vmid']})", value=str(ct["vmid"])) for ct in cts]
        embed = get_embed("🚫 Usage Error", f"You must provide a CT ID for node `{node}`.\nExample: `/startct {node} <ct_id>`", discord.Color.orange())
        select = Select(placeholder="Select a CT to start...", options=ct_options[:25])
        
        async def ct_select_callback(interaction):
            selected_ct_id = select.values[0]
            await interaction.response.send_message(embed=get_embed("Processing", f"Starting CT `{selected_ct_id}` on `{node}`...", discord.Color.teal()), ephemeral=True)
            await startct(ctx, node, selected_ct_id)
        
        select.callback = ct_select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
        
        if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
            await ctx.reply(embed=get_embed("Error", "You are not authorized to start this container.", discord.Color.red()))
            return
        
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


        log_embed = discord.Embed(
            title="📝 CT Operation Log",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="User",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/startct``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} used the ``/startct`` command on {timestamp} to start a container.",
            inline=False
        )
        log_embed.add_field(
            name="Node",
            value=f"`{node}`",
            inline=False
        )
        log_embed.add_field(
            name="CT ID",
            value=f"`{ct_id}`",
            inline=False
        )
        await send_log_message(log_embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def restartct(ctx, node: str = None, ct_id: str = None):
    """Restart an LXC container on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None or ct_id is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return

        if node is None:
            node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
            embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/restartct <node_name> <ct_id>`", discord.Color.orange())
            select = Select(placeholder="Select a node...", options=node_options[:25])
            
            async def node_select_callback(interaction):
                selected_node = select.values[0]
                await interaction.response.send_message(embed=get_embed("Processing", f"Selected node: `{selected_node}`...", discord.Color.teal()), ephemeral=True)
                await restartct(ctx, selected_node, None)
            
            select.callback = node_select_callback
            view = View()
            view.add_item(select)
            await ctx.reply(embed=embed, view=view)
            return

        cts = proxmox.nodes(node).lxc.get()
        if not cts:
            await ctx.reply(embed=get_embed(f"🚫 No CTs on {node}", f"The node `{node}` has no containers.", discord.Color.yellow()))
            return
        
        ct_options = [discord.SelectOption(label=f"{ct.get('name', 'Unnamed')} ({ct['vmid']})", value=str(ct["vmid"])) for ct in cts]
        embed = get_embed("🚫 Usage Error", f"You must provide a CT ID for node `{node}`.\nExample: `/restartct {node} <ct_id>`", discord.Color.orange())
        select = Select(placeholder="Select a CT to restart...", options=ct_options[:25])
        
        async def ct_select_callback(interaction):
            selected_ct_id = select.values[0]
            await interaction.response.send_message(embed=get_embed("Processing", f"Restarting CT `{selected_ct_id}` on `{node}`...", discord.Color.teal()), ephemeral=True)
            await restartct(ctx, node, selected_ct_id)
        
        select.callback = ct_select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
        
        if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
            await ctx.reply(embed=get_embed("Error", "You are not authorized to restart this container.", discord.Color.red()))
            return
        
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


        log_embed = discord.Embed(
            title="📝 CT Operation Log",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="User",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/restartct``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} used the ``/restartct`` command on {timestamp} to restart a container.",
            inline=False
        )
        log_embed.add_field(
            name="Node",
            value=f"`{node}`",
            inline=False
        )
        log_embed.add_field(
            name="CT ID",
            value=f"`{ct_id}`",
            inline=False
        )
        await send_log_message(log_embed)

    except Exception as e:
        await ctx.reply(embed=get_embed("Error", str(e), discord.Color.red()))


@bot.command()
async def stopct(ctx, node: str = None, ct_id: str = None):
    """Stop an LXC container on a specified node."""
    if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user"):
        await ctx.reply(embed=get_embed("Error", "You are not authorized to use this bot.", discord.Color.red()))
        return

    ensure_proxmox_connection()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if node is None or ct_id is None:
        nodes = proxmox.nodes.get()
        if not nodes:
            await ctx.reply(embed=get_embed("🚫 No Nodes", "No nodes are available on this server.", discord.Color.yellow()))
            return

        if node is None:
            node_options = [discord.SelectOption(label=n["node"], value=n["node"]) for n in nodes]
            embed = get_embed("🚫 Usage Error", "You must provide a node name.\nExample: `/stopct <node_name> <ct_id>`", discord.Color.orange())
            select = Select(placeholder="Select a node...", options=node_options[:25])
            
            async def node_select_callback(interaction):
                selected_node = select.values[0]
                await interaction.response.send_message(embed=get_embed("Processing", f"Selected node: `{selected_node}`...", discord.Color.teal()), ephemeral=True)
                await stopct(ctx, selected_node, None)
            
            select.callback = node_select_callback
            view = View()
            view.add_item(select)
            await ctx.reply(embed=embed, view=view)
            return

        cts = proxmox.nodes(node).lxc.get()
        if not cts:
            await ctx.reply(embed=get_embed(f"🚫 No CTs on {node}", f"The node `{node}` has no containers.", discord.Color.yellow()))
            return
        
        ct_options = [discord.SelectOption(label=f"{ct.get('name', 'Unnamed')} ({ct['vmid']})", value=str(ct["vmid"])) for ct in cts]
        embed = get_embed("🚫 Usage Error", f"You must provide a CT ID for node `{node}`.\nExample: `/stopct {node} <ct_id>`", discord.Color.orange())
        select = Select(placeholder="Select a CT to stop...", options=ct_options[:25])
        
        async def ct_select_callback(interaction):
            selected_ct_id = select.values[0]
            await interaction.response.send_message(embed=get_embed("Processing", f"Stopping CT `{selected_ct_id}` on `{node}`...", discord.Color.teal()), ephemeral=True)
            await stopct(ctx, node, selected_ct_id)
        
        select.callback = ct_select_callback
        view = View()
        view.add_item(select)
        await ctx.reply(embed=embed, view=view)
        return

    try:
        ct_status = proxmox.nodes(node).lxc(ct_id).status.current.get()
        
        if not has_permission(ctx.author.id, "admin") and not has_permission(ctx.author.id, "staff") and not has_permission(ctx.author.id, "user", ct_id):
            await ctx.reply(embed=get_embed("Error", "You are not authorized to stop this container.", discord.Color.red()))
            return
        
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

 
        log_embed = discord.Embed(
            title="📝 CT Operation Log",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.fromtimestamp(time.time())
        )
        log_embed.add_field(
            name="User",
            value=f"{ctx.author.display_name} (ID: {ctx.author.id})",
            inline=False
        )
        log_embed.add_field(
            name="Command Used",
            value="``/stopct``",
            inline=False
        )
        log_embed.add_field(
            name="Action",
            value=f"{ctx.author.display_name} used the ``/stopct`` command on {timestamp} to stop a container.",
            inline=False
        )
        log_embed.add_field(
            name="Node",
            value=f"`{node}`",
            inline=False
        )
        log_embed.add_field(
            name="CT ID",
            value=f"`{ct_id}`",
            inline=False
        )
        await send_log_message(log_embed)

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
 
    print("\033[1;32m[OK]\033[1;37m Proxmox reauthentication is running.")
    
    
    rotate_status.start()
    
    
    print("\n\033[1;37mMADE BY: \033[1;36mBENCE\033[0m")
    print("\033[1;33mGithub: xyzBence\033[0m")
    print("\033[1;32m" + "=" * 50)


status_messages = cycle([
    "Made by Bence",
    "/listcommands",
    "/listnodes",
    "/listvms",
    "/vmavg",
    "/startvm",
    "/restartvm",
    "/stopvm",
    "/listcts",
    "/ctavg",
    "/startct",
    "/restartct",
    "/stopct",
    "/serverinfo",
    "/setlog",
    "/deletelog",
    "/setuser",
    "/setstaff",
    "/config",
    "Github: xyzBence"
])

@tasks.loop(seconds=4)
async def rotate_status():
    current_status = next(status_messages)
    await bot.change_presence(activity=discord.Game(name=current_status))



bot.run(TOKEN)
