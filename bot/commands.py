import discord
from discord.ext import commands
from bot import config

class AutoReplyCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @discord.app_commands.command(name="autoreply", description="控制自动回复功能")
    @discord.app_commands.describe(
        action="操作: enable/disable/status",
        channel="频道ID (可选)",
        chance="回复概率 0.0-1.0 (可选)"
    )
    async def autoreply(
        self, 
        interaction: discord.Interaction, 
        action: str,
        channel: str = None,
        chance: float = None
    ):
        # Check permissions (only admins can modify)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理员可以控制自动回复功能", ephemeral=True)
            return
        
        if action.lower() == "status":
            embed = discord.Embed(title="🤖 自动回复状态", color=0x00ff00)
            embed.add_field(name="启用状态", value="✅ 已启用" if config.AUTO_REPLY_ENABLED else "❌ 已禁用", inline=False)
            embed.add_field(name="回复概率", value=f"{config.AUTO_REPLY_CHANCE*100}%", inline=True)
            embed.add_field(name="限制频道", value=", ".join(config.AUTO_REPLY_CHANNELS) if config.AUTO_REPLY_CHANNELS else "所有频道", inline=True)
            embed.add_field(name="关键词", value=", ".join(config.AUTO_REPLY_KEYWORDS) if config.AUTO_REPLY_KEYWORDS else "无", inline=True)
            
            await interaction.response.send_message(embed=embed)
            
        elif action.lower() == "enable":
            config.AUTO_REPLY_ENABLED = True
            if chance is not None:
                if 0 <= chance <= 1:
                    config.AUTO_REPLY_CHANCE = chance
                else:
                    await interaction.response.send_message("❌ 概率必须在 0.0-1.0 之间")
                    return
            
            if channel:
                if channel not in config.AUTO_REPLY_CHANNELS:
                    config.AUTO_REPLY_CHANNELS.append(channel)
            
            await interaction.response.send_message(f"✅ 自动回复已启用 (概率: {config.AUTO_REPLY_CHANCE*100}%)")
            
        elif action.lower() == "disable":
            config.AUTO_REPLY_ENABLED = False
            await interaction.response.send_message("❌ 自动回复已禁用")
            
        else:
            await interaction.response.send_message("❌ 无效操作，请使用: enable/disable/status")


async def setup(bot):
    await bot.add_cog(AutoReplyCommands(bot))
