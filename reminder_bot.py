import discord
from discord.ext import tasks, commands
import asyncio
from datetime import datetime, timedelta
from pytz import timezone, utc
import re
import os
from dotenv import load_dotenv

load_dotenv()

# Replace with your actual bot token and target channel ID
TOKEN = os.getenv('TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))


# Map common timezone abbreviations to full pytz names
TIMEZONE_ALIASES = {
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "UTC": "UTC",
    "GMT": "Etc/GMT"
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

user_reminders = []

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    reminder_scheduler.start()

@bot.command(name='remind')
async def remind(ctx, *, input_text: str):
    """
    Usage:
    !remind YYYY-MM-DD HH:MM TZ once @mention|@everyone|@dm Your reminder message
    !remind Mon,Tue HH:MM TZ weekly @mention|@everyone|@dm Your reminder message
    TZ must be a valid timezone abbreviation like PST, EST, UTC

    Example:
    !remind 2025-05-10 20:00 PST once @everyone Submit your assignment
    !remind Mon,Wed 08:30 EST weekly @123456789012345678 Gym time!
    """
    weekly_match = re.match(r'([A-Za-z]{3}(?:,[A-Za-z]{3})*)\s+(\d{1,2}:\d{2})\s+(\w+)\s+weekly\s+(@\S+)\s+(.+)', input_text)
    if weekly_match:
        days_str, time_str, tz_abbr, mention, message = weekly_match.groups()
        weekdays = [day.capitalize() for day in days_str.split(',')]
        hour, minute = map(int, time_str.split(':'))
        try:
            tz_name = TIMEZONE_ALIASES.get(tz_abbr.upper())
            if not tz_name:
                await ctx.send("❌ Invalid timezone abbreviation. Try PST, EST, UTC, etc.")
                return
            tz = timezone(tz_name)
        except Exception:
            await ctx.send("❌ Invalid timezone.")
            return
        user_reminders.append({
            'repeat': 'weekly', 'weekdays': weekdays, 'hour': hour, 'minute': minute, 'tz': tz,
            'message': message, 'mention': mention, 'user_id': ctx.author.id, 'sent': False
        })
        await ctx.send(f"✅ Weekly reminder set for {', '.join(weekdays)} at {time_str} {tz_abbr.upper()} → {message}")
        return

    match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s+(\w+)\s+once\s+(@\S+)\s+(.+)', input_text)
    if match:
        date_str, time_str, tz_abbr, mention, message = match.groups()
        try:
            tz_name = TIMEZONE_ALIASES.get(tz_abbr.upper())
            if not tz_name:
                await ctx.send("❌ Invalid timezone abbreviation. Try PST, EST, UTC, etc.")
                return
            tz = timezone(tz_name)
            dt = tz.localize(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M"))
            dt_utc = dt.astimezone(utc)
        except Exception:
            await ctx.send("❌ Invalid datetime or timezone.")
            return
        user_reminders.append({
            'repeat': 'once', 'datetime': dt_utc, 'message': message,
            'mention': mention, 'user_id': ctx.author.id, 'sent': False
        })
        await ctx.send(f"✅ One-time reminder set for {dt.strftime('%Y-%m-%d %H:%M %Z')} → {message}")
        return

    await ctx.send("❌ Invalid format. Use: `!remind YYYY-MM-DD HH:MM TZ once @mention Message` or `!remind Mon,Wed HH:MM TZ weekly @mention Message`")

@bot.command(name='reminders')
async def list_reminders(ctx):
    if ctx.author.guild_permissions.administrator:
        user_list = [r for r in user_reminders if not r.get('sent')]
    else:
        user_list = [r for r in user_reminders if r.get('user_id') == ctx.author.id and not r.get('sent')]
    if not user_list:
        await ctx.send("📭 No active reminders.")
        return
    response = "📝 Active reminders:\n"
    for i, r in enumerate(user_list):
        if r['repeat'] == 'once':
            response += f"`{i}` → {r['datetime'].strftime('%Y-%m-%d %H:%M %Z')} → {r['message']}\n"
        else:
            response += f"`{i}` → Weekly on {', '.join(r['weekdays'])} at {r['hour']:02d}:{r['minute']:02d} ({r['tz']}) → {r['message']}\n"
    await ctx.send(response)

@bot.command(name='remindremove')
async def remove_reminder(ctx, index: int):
    matching = [r for r in user_reminders if (r.get('user_id') == ctx.author.id or ctx.author.guild_permissions.administrator) and not r.get('sent')]
    if 0 <= index < len(matching):
        to_remove = matching[index]
        user_reminders.remove(to_remove)
        await ctx.send("🗑️ Reminder removed.")
    else:
        await ctx.send("❌ Invalid reminder index.")

@bot.command(name='remindedit')
async def edit_reminder(ctx, index: int, *, new_message: str):
    matching = [r for r in user_reminders if r.get('user_id') == ctx.author.id and not r.get('sent')]
    if 0 <= index < len(matching):
        matching[index]['message'] = new_message
        await ctx.send("✏️ Reminder updated.")
    else:
        await ctx.send("❌ Invalid index or no permission.")

@tasks.loop(minutes=1)
async def reminder_scheduler():
    now_utc = datetime.now(utc).replace(second=0, microsecond=0)
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
    for r in user_reminders:
        target = r.get('datetime') if r['repeat'] == 'once' else None
        if r['repeat'] == 'once' and target and target.replace(second=0, microsecond=0) == now_utc and not r['sent']:
            if r['mention'] == '@dm':
                user = await bot.fetch_user(r['user_id'])
                await user.send(f"🔔 Reminder: {r['message']}")
            else:
                await channel.send(f"🔔 {r['mention']} Reminder: {r['message']}")
            r['sent'] = True
            await channel.send("👍")
        elif r['repeat'] == 'weekly':
            now_local = now_utc.astimezone(r['tz'])
            weekday = now_local.strftime('%a')
            if weekday in r['weekdays'] and r['hour'] == now_local.hour and r['minute'] == now_local.minute:
                if r['mention'] == '@dm':
                    user = await bot.fetch_user(r['user_id'])
                    await user.send(f"🔔 Weekly Reminder: {r['message']}")
                else:
                    await channel.send(f"🔔 {r['mention']} Weekly Reminder: {r['message']}")
                await channel.send("👍")

@reminder_scheduler.before_loop
async def before():
    await bot.wait_until_ready()

bot.run(TOKEN)
