import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime
import google.generativeai as genai
import database as db  # ← ОБЩАЯ БАЗА ДАННЫХ

TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

OWNER_ID = int(os.environ.get("OWNER_ID", "920268444983775252"))

def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID

# ========== ПРОВЕРКА ПРЕМИУМА ==========
def is_premium(user_id: str) -> bool:
    return db.is_premium(user_id)  # ← проверка из общей БД

# ========== КОМАНДЫ ==========

@bot.tree.command(name="status", description="Проверить статус подписки")
async def status_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if is_premium(user_id):
        expiry = db.get_expiry(user_id)
        embed = discord.Embed(
            title="💎 Статус подписки",
            description=f"✅ Премиум **активен**\n📅 Действует до: {expiry}",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title="💎 Статус подписки",
            description="❌ Премиум **не активен**\n\nКупить: `/buy` или напишите в Telegram @LawyerPayBot",
            color=discord.Color.orange()
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="give", description="[АДМИН] Выдать премиум")
@app_commands.describe(user="Пользователь", days="Количество дней")
async def give_cmd(interaction: discord.Interaction, user: discord.User, days: int = 30):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    
    db.set_premium(str(user.id), days)
    embed = discord.Embed(
        title="✅ Премиум выдан",
        description=f"{user.mention} получил премиум на **{days}** дней",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="list", description="[АДМИН] Список активных подписок")
async def list_cmd(interaction: discord.Interaction):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    
    users = db.get_all_premium()
    if not users:
        await interaction.response.send_message("Нет активных подписок", ephemeral=True)
        return
    
    text = "**💎 Активные подписки:**\n"
    for discord_id, expires_at in users[:20]:
        try:
            user = await bot.fetch_user(int(discord_id))
            name = user.name
        except:
            name = discord_id
        expires = expires_at[:10]
        text += f"• {name} — до {expires}\n"
    
    await interaction.response.send_message(text, ephemeral=True)

# ========== ПОИСК ПО УК ==========
@bot.tree.command(name="ук", description="Поиск по Уголовному кодексу")
@app_commands.describe(query="Номер статьи или название")
async def uk_cmd(interaction: discord.Interaction, query: str):
    user_id = str(interaction.user.id)
    
    # Проверка премиума и лимитов
    if not is_premium(user_id):
        # Здесь можно добавить проверку лимитов бесплатных запросов
        pass
    
    # ... остальной код поиска ...

# ========== ЗАПУСК ==========
@bot.event
async def on_ready():
    print(f"✅ Discord бот {bot.user} готов!")

bot.run(TOKEN)
