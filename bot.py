import discord
from discord.ext import commands
import aiohttp
import asyncio
import json
import logging
import sqlite3
from collections import deque
import random
import traceback
from datetime import datetime
import requests
from deep_translator import GoogleTranslator
import sys
import io
import ssl

# Tắt xác minh SSL cho các yêu cầu aiohttp
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Cấu hình logging nâng cao
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Cấu hình Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Cấu hình Gemini API
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
GEMINI_API_KEY = "AIzaSyAOJ9gfKhJjwrGa4UDxh8_y4iHY6ebKI88"  # Thay thế bằng API key của bạn

# Bộ nhớ ngắn hạn và trạng thái hoạt động của bot
short_term_memory = {}
bot_active = {}
fact_tasks = {}

# Kết nối đến cơ sở dữ liệu SQLite
conn = sqlite3.connect('bot_memory.db')
cursor = conn.cursor()

# Tạo bảng cho bộ nhớ dài hạn
cursor.execute('''
CREATE TABLE IF NOT EXISTS long_term_memory
(user_id TEXT, context TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
''')
conn.commit()

# Prompt tối ưu
OPTIMIZED_PROMPT = """
Bạn là một trợ lý AI thông minh, hữu ích và thân thiện. Hãy trả lời các câu hỏi một cách ngắn gọn, chính xác và dễ hiểu. 
Sử dụng ngôn ngữ phù hợp với người dùng và bối cảnh. Nếu không chắc chắn về câu trả lời, hãy thừa nhận điều đó.
Luôn giữ thái độ tích cực và hỗ trợ. Nếu được yêu cầu thực hiện hành động không phù hợp hoặc nguy hiểm, hãy từ chối một cách lịch sự.
Sử dụng biểu tượng cảm xúc và định dạng markdown để làm nổi bật nội dung hoặc ý chính.
Tránh lặp lại quá nhiều nội dung trò chuyện, nắm bắt ý chính và trả lời một cách chính xác.

Ngữ cảnh cuộc trò chuyện:
{context}

Người dùng: {user_message}

Trợ lý AI:
"""

# Prompt cho trò chơi nối từ
WORD_CHAIN_PROMPT = """
Bạn đang tham gia trò chơi nối từ. Nhiệm vụ của bạn là đưa ra một từ hai chữ bắt đầu bằng chữ cuối cùng của từ được cung cấp.
Quy tắc:
1. Từ phải có chính xác hai chữ.
2. Từ phải bắt đầu bằng chữ cuối cùng của từ trước đó.
3. Từ phải có nghĩa và phổ biến trong tiếng Việt.
4. Không được lặp lại từ đã sử dụng trước đó.

Từ được cung cấp: {input_word}

Hãy đưa ra một từ phù hợp:
"""

class WordChainGame:
    def __init__(self):
        self.active_games = {}
        self.used_words = {}

    def start_game(self, user_id):
        self.active_games[user_id] = True
        self.used_words[user_id] = set()

    def stop_game(self, user_id):
        if user_id in self.active_games:
            del self.active_games[user_id]
        if user_id in self.used_words:
            del self.used_words[user_id]

    def is_game_active(self, user_id):
        return user_id in self.active_games

    def add_used_word(self, user_id, word):
        if user_id not in self.used_words:
            self.used_words[user_id] = set()
        self.used_words[user_id].add(word.lower())

    def is_word_used(self, user_id, word):
        return word.lower() in self.used_words.get(user_id, set())

    def is_valid_word(self, prev_word, new_word):
        return len(new_word) == 2 and prev_word[-1].lower() == new_word[0].lower()

word_chain_game = WordChainGame()

async def generate_gemini_response(prompt, context=""):
    headers = {
        "Content-Type": "application/json"
    }
    
    params = {
        "key": GEMINI_API_KEY
    }
    
    full_prompt = OPTIMIZED_PROMPT.format(context=context, user_message=prompt)
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": full_prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 1,
            "topK": 60,
            "topP": 1,
            "maxOutputTokens": 8092,
            "stopSequences": []
        },
        "safetySettings": [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, headers=headers, params=params, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("Nhận phản hồi từ Gemini API thành công")
                    return result['candidates'][0]['content']['parts'][0]['text']
                else:
                    error_text = await response.text()
                    logger.error(f"Lỗi Gemini API: Trạng thái {response.status}, Phản hồi: {error_text}")
                    return f"Xin lỗi, đã xảy ra lỗi (Mã lỗi {response.status}). Vui lòng thử lại sau hoặc liên hệ hỗ trợ."
    except Exception as e:
        logger.error(f"Lỗi không mong đợi khi gọi Gemini API: {str(e)}")
        return "Đã xảy ra lỗi không mong muốn. Vui lòng thử lại sau."

async def generate_word_chain_response(input_word):
    headers = {
        "Content-Type": "application/json"
    }
    
    params = {
        "key": GEMINI_API_KEY
    }
    
    full_prompt = WORD_CHAIN_PROMPT.format(input_word=input_word)
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": full_prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 100,
            "stopSequences": []
        },
        "safetySettings": [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, headers=headers, params=params, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("Nhận phản hồi từ Gemini API thành công cho trò chơi nối từ")
                    return result['candidates'][0]['content']['parts'][0]['text'].strip()
                else:
                    error_text = await response.text()
                    logger.error(f"Lỗi Gemini API (trò chơi nối từ): Trạng thái {response.status}, Phản hồi: {error_text}")
                    return f"Xin lỗi, đã xảy ra lỗi (Mã lỗi {response.status}). Vui lòng thử lại sau hoặc liên hệ hỗ trợ."
    except Exception as e:
        logger.error(f"Lỗi không mong đợi khi gọi Gemini API cho trò chơi nối từ: {str(e)}")
        return "Đã xảy ra lỗi không mong muốn. Vui lòng thử lại sau."

@bot.event
async def on_ready():
    logger.info(f'{bot.user} đã kết nối với Discord!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = str(message.author.id)
    if user_id not in bot_active:
        bot_active[user_id] = True

    if bot_active[user_id]:
        if message.content.startswith(bot.command_prefix):
            await bot.process_commands(message)
        else:
            try:
                async with message.channel.typing():
                    response = await generate_gemini_response(message.content, get_context(user_id))
                    update_memory(user_id, message.content, response)
                await message.channel.send(response)
            except Exception as e:
                logger.error(f"Lỗi xử lý tin nhắn: {str(e)}")
                await message.channel.send("Xin lỗi, đã xảy ra lỗi khi xử lý tin nhắn của bạn. Vui lòng thử lại sau.")
    else:
        if message.content.startswith(bot.command_prefix):
            await bot.process_commands(message)

# Lệnh Main
@bot.command(name="ping")
async def ping(ctx):
    """Kiểm tra độ trễ của bot."""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", description=f"Độ trễ: **{latency}ms**", color=discord.Color.green())
    embed.set_footer(text="Bot đang hoạt động tốt!")
    await ctx.send(embed=embed)
    logger.info(f"Lệnh ping được thực hiện bởi {ctx.author}. Độ trễ: {latency}ms")

@bot.command(name="helpme")
async def help_command(ctx):
    """Hiển thị danh sách các lệnh có sẵn."""
    embed = discord.Embed(title="📚 Danh sách lệnh", description="Dưới đây là các lệnh có sẵn:", color=discord.Color.blue())
    
    embed.add_field(name="🛠️ Main", value="`/ping`, `/helpme`, `/stop`, `/continue`, `/clearmemory`, `/clearall`", inline=False)
    embed.add_field(name="ℹ️ General", value="`/invite`, `/botinfo`, `/server`, `/serverinfo`", inline=False)
    embed.add_field(name="🎉 Fun", value="`/fact`, `/stopfact`, `/quote`, `/randomimage`, `/coinflip`", inline=False)
    embed.add_field(name="🎮 Game", value="`/noitu`, `/stopnoitu`", inline=False)
    embed.add_field(name="👑 Admin", value="`/shutdown`, `/kick`, `/ban`, `/warning`, `/say`, `/embed`, `/reload`, `/sendcontact`", inline=False)
    
    embed.set_footer(text="Sử dụng /helpme <lệnh> để biết thêm chi tiết về một lệnh cụ thể.")
    await ctx.send(embed=embed)
    logger.info(f"Lệnh help được thực hiện bởi {ctx.author}")

@bot.command(name="stop")
async def stop_conversation(ctx):
    """Dừng hoạt động của bot cho người dùng cụ thể."""
    user_id = str(ctx.author.id)
    bot_active[user_id] = False
    if user_id in fact_tasks:
        fact_tasks[user_id].cancel()
        del fact_tasks[user_id]
    word_chain_game.stop_game(user_id)
    embed = discord.Embed(title="🛑 Bot đã dừng hoạt động", description="Sử dụng `/continue` để tiếp tục.", color=discord.Color.red())
    embed.set_footer(text="Bot sẽ không phản hồi tin nhắn của bạn cho đến khi được kích hoạt lại.")
    await ctx.send(embed=embed)
    logger.info(f"Bot đã dừng hoạt động cho người dùng {ctx.author}")

@bot.command(name="continue")
async def continue_conversation(ctx):
    """Tiếp tục hoạt động của bot cho người dùng cụ thể."""
    user_id = str(ctx.author.id)
    bot_active[user_id] = True
    embed = discord.Embed(title="▶️ Bot đã tiếp tục hoạt động", description="Bạn có thể tiếp tục trò chuyện.", color=discord.Color.green())
    embed.set_footer(text="Hãy hỏi tôi bất cứ điều gì bạn muốn!")
    await ctx.send(embed=embed)
    logger.info(f"Bot đã tiếp tục hoạt động cho người dùng {ctx.author}")

@bot.command(name="clearmemory")
async def clear_memory(ctx):
    """Xóa bộ nhớ ngắn hạn của người dùng."""
    user_id = str(ctx.author.id)
    if user_id in short_term_memory:
        short_term_memory[user_id].clear()
        embed = discord.Embed(title="🧹 Xóa bộ nhớ", description="✅ Bộ nhớ ngắn hạn của bạn đã được xóa.", color=discord.Color.green())
        embed.set_footer(text="Bot sẽ bắt đầu cuộc trò chuyện mới với bạn.")
    else:
        embed = discord.Embed(title="🧹 Xóa bộ nhớ", description="❌ Không có bộ nhớ ngắn hạn nào để xóa.", color=discord.Color.red())
        embed.set_footer(text="Bạn chưa có cuộc trò chuyện nào với bot.")
    await ctx.send(embed=embed)
    logger.info(f"Bộ nhớ ngắn hạn đã được xóa cho người dùng {ctx.author}")

@bot.command(name="clearall")
async def clear_all_memory(ctx):
    """Xóa toàn bộ bộ nhớ của người dùng."""
    user_id = str(ctx.author.id)
    if user_id in short_term_memory:
        short_term_memory[user_id].clear()
    cursor.execute("DELETE FROM long_term_memory WHERE user_id = ?", (user_id,))
    conn.commit()
    embed = discord.Embed(title="🗑️ Xóa toàn bộ bộ nhớ", description="✅ Toàn bộ bộ nhớ của bạn đã được xóa.", color=discord.Color.green())
    embed.set_footer(text="Bot sẽ quên mọi cuộc trò chuyện trước đây với bạn.")
    await ctx.send(embed=embed)
    logger.info(f"Toàn bộ bộ nhớ đã được xóa cho người dùng {ctx.author}")

# Lệnh General
@bot.command(name="invite")
async def invite_link(ctx):
    """Lấy liên kết mời bot và gửi trong tin nhắn riêng."""
    invite_url = discord.utils.oauth_url(bot.user.id, permissions=discord.Permissions(8))
    embed = discord.Embed(title="🎉 Mời Bot Tham Gia Server Của Bạn!", color=discord.Color.blue())
    embed.description = (
        f"Xin chào {ctx.author.mention}! Cảm ơn bạn đã quan tâm đến bot của chúng tôi. "
        f"Dưới đây là một số lý do tuyệt vời để thêm bot vào server của bạn:\n\n"
        f"✨ Tính năng đa dạng và hữu ích\n"
        f"🚀 Hiệu suất cao và ổn định\n"
        f"🔒 An toàn và bảo mật\n"
        f"🆙 Cập nhật thường xuyên với tính năng mới\n"
        f"💬 Hỗ trợ 24/7 từ đội ngũ phát triển\n\n"
        f"[Nhấp vào đây để mời bot]({invite_url})\n\n"
        f"Nếu bạn cần hỗ trợ thêm, đừng ngần ngại sử dụng lệnh `/server` để tham gia server hỗ trợ của chúng tôi!"
    )
    embed.set_footer(text="Cảm ơn bạn đã lựa chọn bot của chúng tôi!")
    
    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📨 Tôi đã gửi thông tin mời bot vào tin nhắn riêng của bạn!")
    except discord.Forbidden:
        await ctx.send("❌ Không thể gửi tin nhắn riêng. Vui lòng kiểm tra cài đặt quyền riêng tư của bạn.")
    
    logger.info(f"Liên kết mời bot được yêu cầu bởi {ctx.author}")

@bot.command(name="botinfo")
async def bot_info(ctx):
    """Hiển thị thông tin về bot."""
    embed = discord.Embed(title="🤖 Thông tin Bot", color=discord.Color.blue())
    embed.add_field(name="Tên", value=bot.user.name, inline=True)
    embed.add_field(name="ID", value=bot.user.id, inline=True)
    embed.add_field(name="Phiên bản Discord.py", value=discord.__version__, inline=True)
    embed.add_field(name="Độ trễ", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="Số lượng server", value=len(bot.guilds), inline=True)
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(text="Bot luôn sẵn sàng phục vụ bạn!")
    await ctx.send(embed=embed)
    logger.info(f"Thông tin bot được yêu cầu bởi {ctx.author}")

@bot.command(name="server")
async def server_command(ctx):
    """Lấy liên kết đến server hỗ trợ của bot và gửi trong tin nhắn riêng."""
    support_server_link = "https://discord.gg/GknzmQmX"
    embed = discord.Embed(title="🌟 Tham Gia Server Hỗ Trợ Của Chúng Tôi!", color=discord.Color.gold())
    embed.description = (
        f"Xin chào {ctx.author.mention}! Chúng tôi rất vui khi bạn quan tâm đến cộng đồng của chúng tôi. "
        f"Dưới đây là một số lý do tuyệt vời để tham gia server hỗ trợ:\n\n"
        f"🆘 Hỗ trợ trực tiếp từ đội ngũ phát triển\n"
        f"💡 Chia sẻ ý tưởng và đề xuất tính năng mới\n"
        f"🎉 Tham gia các sự kiện và cuộc thi thú vị\n"
        f"🤝 Kết nối với những người dùng khác\n"
        f"🔔 Cập nhật tin tức và thông báo mới nhất\n\n"
        f"[Nhấp vào đây để tham gia server]({support_server_link})\n\n"
        f"Chúng tôi rất mong được gặp bạn ở đó!"
    )
    embed.set_footer(text="Cảm ơn bạn đã là một phần của cộng đồng chúng tôi!")
    
    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📨 Tôi đã gửi thông tin về server hỗ trợ vào tin nhắn riêng của bạn!")
    except discord.Forbidden:
        await ctx.send("❌ Không thể gửi tin nhắn riêng. Vui lòng kiểm tra cài đặt quyền riêng tư của bạn.")
    
    logger.info(f"Liên kết server hỗ trợ được yêu cầu bởi {ctx.author}")

@bot.command(name="serverinfo")
async def server_info(ctx):
    """Hiển thị thông tin về server hiện tại."""
    guild = ctx.guild
    embed = discord.Embed(title=f"ℹ️ Thông tin Server: {guild.name}", color=discord.Color.green())
    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="Chủ sở hữu", value=guild.owner, inline=True)
    embed.add_field(name="Số lượng thành viên", value=guild.member_count, inline=True)
    embed.add_field(name="Ngày tạo", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.set_footer(text="Cảm ơn bạn đã sử dụng bot trong server này!")
    await ctx.send(embed=embed)
    logger.info(f"Thông tin server được yêu cầu bởi {ctx.author}")

# Lệnh Fun
async def get_random_fact_or_joke():
    sources = [
        ("https://dog-api.kinduff.com/api/facts", lambda data: ("🐶 Sự thật về chó", data["facts"][0])),
        ("https://catfact.ninja/fact", lambda data: ("🐱 Sự thật về mèo", data["fact"])),
        ("http://numbersapi.com/random/trivia", lambda data: ("🔢 Sự thật về số", data)),
        ("https://uselessfacts.jsph.pl/random.json?language=en", lambda data: ("🤔 Sự thật thú vị", data["text"])),
        ("https://official-joke-api.appspot.com/random_joke", lambda data: ("😂 Câu chuyện cười", f"{data['setup']} {data['punchline']}"))
    ]
    random.shuffle(sources)
    
    async with aiohttp.ClientSession() as session:
        for source, extract_data in sources:
            try:
                async with session.get(source) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        title, content = extract_data(data)
                        return title, content
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu từ {source}: {str(e)}")
                continue
    
    return "Không thể lấy thông tin", "Xin lỗi, không thể lấy sự thật hoặc câu chuyện cười. Vui lòng thử lại sau."

@bot.command(name="fact")
async def random_fact(ctx):
    """Lấy sự thật hoặc câu chuyện cười ngẫu nhiên."""
    user_id = str(ctx.author.id)
    if user_id in fact_tasks:
        await ctx.send("Bạn đã đang nhận sự thật hoặc câu chuyện cười ngẫu nhiên. Sử dụng /stopfact để dừng.")
        return

    async def send_facts():
        while True:
            try:
                async with ctx.typing():
                    title, content = await get_random_fact_or_joke()
                    translator = GoogleTranslator(source='en', target='vi')
                    translated_content = translator.translate(content)
                    embed = discord.Embed(title=title, color=discord.Color.random())
                    embed.add_field(name="🇬🇧 English", value=content, inline=False)
                    embed.add_field(name="🇻🇳 Tiếng Việt", value=translated_content, inline=False)
                    embed.set_footer(text="Sử dụng /stopfact để dừng nhận thông tin.")
                    await ctx.send(embed=embed)
                await asyncio.sleep(30)  # Gửi mỗi 30 giây
            except Exception as e:
                logger.error(f"Lỗi trong quá trình gửi sự thật hoặc câu chuyện cười: {str(e)}")
                await ctx.send("Đã xảy ra lỗi khi gửi thông tin. Đang thử lại...")
                await asyncio.sleep(30)

    fact_tasks[user_id] = asyncio.create_task(send_facts())
    await ctx.send("Bắt đầu gửi sự thật hoặc câu chuyện cười ngẫu nhiên. Sử dụng /stopfact để dừng.")
    logger.info(f"Bắt đầu gửi sự thật hoặc câu chuyện cười ngẫu nhiên cho người dùng {ctx.author}")

@bot.command(name="stopfact")
async def stop_fact(ctx):
    """Dừng gửi sự thật hoặc câu chuyện cười ngẫu nhiên."""
    user_id = str(ctx.author.id)
    if user_id in fact_tasks:
        fact_tasks[user_id].cancel()
        del fact_tasks[user_id]
        embed = discord.Embed(title="🛑 Dừng gửi thông tin", description="✅ Đã dừng gửi sự thật hoặc câu chuyện cười ngẫu nhiên.", color=discord.Color.green())
        embed.set_footer(text="Bạn có thể sử dụng /fact để bắt đầu lại bất cứ lúc nào.")
        await ctx.send(embed=embed)
        logger.info(f"Dừng gửi sự thật hoặc câu chuyện cười ngẫu nhiên cho người dùng {ctx.author}")
    else:
        embed = discord.Embed(title="🛑 Dừng gửi thông tin", description="❌ Bạn chưa bắt đầu nhận sự thật hoặc câu chuyện cười ngẫu nhiên.", color=discord.Color.red())
        embed.set_footer(text="Sử dụng /fact để bắt đầu nhận thông tin ngẫu nhiên.")
        await ctx.send(embed=embed)

@bot.command(name="quote")
async def random_quote(ctx):
    """Lấy một trích dẫn ngẫu nhiên và dịch sang tiếng Việt."""
    quote_apis = [
        ("https://api.quotable.io/random", lambda data: (data["content"], data["author"], data.get("tags", []))),
        ("https://api.themotivate365.com/stoic-quote", lambda data: (data["quote"], data["author"], []))
    ]
    
    async with ctx.typing():
        for api, extract_data in quote_apis:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api, ssl=ssl_context) as response:
                        if response.status == 200:
                            data = await response.json()
                            quote, author, tags = extract_data(data)
                            
                            translator = GoogleTranslator(source='en', target='vi')
                            translated_quote = translator.translate(quote)
                            translated_author = translator.translate(author)
                            
                            embed = discord.Embed(title="💬 Trích dẫn ngẫu nhiên", color=discord.Color.gold())
                            embed.add_field(name="🇬🇧 English", value=f"\"{quote}\"", inline=False)
                            embed.add_field(name="🇻🇳 Tiếng Việt", value=f"\"{translated_quote}\"", inline=False)
                            embed.add_field(name="Tác giả", value=f"🇬🇧 {author} | 🇻🇳 {translated_author}", inline=False)
                            
                            if tags:
                                embed.add_field(name="Thẻ", value=", ".join(tags), inline=False)
                            
                            embed.set_footer(text=f"Nguồn: {api.split('//')[1].split('/')[0]}")
                            await ctx.send(embed=embed)
                            logger.info(f"Trích dẫn ngẫu nhiên được gửi cho người dùng {ctx.author}")
                            return
            except Exception as e:
                logger.error(f"Lỗi khi lấy trích dẫn từ {api}: {str(e)}")
                continue
    
    embed = discord.Embed(title="❌ Lỗi", description="Xin lỗi, không thể lấy trích dẫn ngẫu nhiên. Vui lòng thử lại sau.", color=discord.Color.red())
    await ctx.send(embed=embed)
    logger.error(f"Không thể lấy trích dẫn ngẫu nhiên từ tất cả các nguồn.")

@bot.command(name="randomimage")
async def random_image(ctx):
    """Lấy và gửi một hình ảnh ngẫu nhiên."""
    image_apis = [
        ("https://source.unsplash.com/random", "Unsplash"),
        ("https://picsum.photos/500", "Lorem Picsum"),
        ("https://api.thecatapi.com/v1/images/search", "The Cat API"),
        ("https://dog.ceo/api/breeds/image/random", "Dog CEO")
    ]
    
    async with ctx.typing():
        for api, source in random.sample(image_apis, len(image_apis)):
            try:
                async with aiohttp.ClientSession() as session:
                    if "thecatapi" in api or "dog.ceo" in api:
                        async with session.get(api) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                image_url = data[0]['url'] if "thecatapi" in api else data['message']
                                async with session.get(image_url) as img_resp:
                                    if img_resp.status == 200:
                                        data = await img_resp.read()
                                        with io.BytesIO(data) as image:
                                            file = discord.File(image, "random_image.png")
                                            embed = discord.Embed(title="🖼️ Hình ảnh ngẫu nhiên", color=discord.Color.random())
                                            embed.set_image(url="attachment://random_image.png")
                                            embed.set_footer(text=f"Nguồn: {source}")
                                            await ctx.send(file=file, embed=embed)
                                        logger.info(f"Hình ảnh ngẫu nhiên từ {source} được gửi cho người dùng {ctx.author}")
                                        return
                    else:
                        async with session.get(api) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                with io.BytesIO(data) as image:
                                    file = discord.File(image, "random_image.png")
                                    embed = discord.Embed(title="🖼️ Hình ảnh ngẫu nhiên", color=discord.Color.random())
                                    embed.set_image(url="attachment://random_image.png")
                                    embed.set_footer(text=f"Nguồn: {source}")
                                    await ctx.send(file=file, embed=embed)
                                logger.info(f"Hình ảnh ngẫu nhiên từ {source} được gửi cho người dùng {ctx.author}")
                                return
            except Exception as e:
                logger.error(f"Lỗi khi tải hình ảnh từ {api}: {str(e)}")
                continue
    
    await ctx.send("Xin lỗi, không thể tải hình ảnh ngẫu nhiên. Vui lòng thử lại sau.")
    logger.error("Không thể tải hình ảnh ngẫu nhiên từ tất cả các nguồn.")

@bot.command(name="coinflip")
async def coin_flip(ctx):
    """Tung đồng xu."""
    result = random.choice(["Mặt sấp", "Mặt ngửa"])
    embed = discord.Embed(title="🪙 Tung đồng xu", description=f"Kết quả: **{result}**!", color=discord.Color.gold())
    embed.set_footer(text="Thử vận may của bạn!")
    await ctx.send(embed=embed)
    logger.info(f"Kết quả tung đồng xu cho người dùng {ctx.author}: {result}")

# Lệnh Game
@bot.command(name="noitu")
async def word_chain(ctx, *, word):
    """Bắt đầu hoặc tiếp tục trò chơi nối từ."""
    user_id = str(ctx.author.id)
    
    if not word_chain_game.is_game_active(user_id):
        word_chain_game.start_game(user_id)
        embed = discord.Embed(title="🎮 Trò chơi Nối Từ", description="Trò chơi đã bắt đầu! Hãy nhập một từ có 2 chữ để bắt đầu.", color=discord.Color.green())
        await ctx.send(embed=embed)
        return

    if len(word.split()) != 2:
        embed = discord.Embed(title="❌ Lỗi", description="Vui lòng nhập một từ có đúng 2 chữ.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    if word_chain_game.is_word_used(user_id, word):
        embed = discord.Embed(title="❌ Lỗi", description="Từ này đã được sử dụng. Vui lòng chọn một từ khác.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    word_chain_game.add_used_word(user_id, word)

    try:
        bot_response = await generate_word_chain_response(word)
        if word_chain_game.is_valid_word(word, bot_response):
            word_chain_game.add_used_word(user_id, bot_response)
            embed = discord.Embed(title="🤖 Bot trả lời", description=f"Từ của bot: **{bot_response}**", color=discord.Color.blue())
            embed.set_footer(text="Nhập từ tiếp theo của bạn bằng lệnh /noitu")
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="🏆 Bạn thắng!", description="Bot không thể tìm được từ phù hợp. Bạn đã chiến thắng!", color=discord.Color.gold())
            await ctx.send(embed=embed)
            word_chain_game.stop_game(user_id)
    except Exception as e:
        logger.error(f"Lỗi trong trò chơi nối từ: {str(e)}")
        embed = discord.Embed(title="❌ Lỗi", description="Đã xảy ra lỗi trong trò chơi. Vui lòng thử lại sau.", color=discord.Color.red())
        await ctx.send(embed=embed)

@bot.command(name="stopnoitu")
async def stop_word_chain(ctx):
    """Dừng trò chơi nối từ."""
    user_id = str(ctx.author.id)
    if word_chain_game.is_game_active(user_id):
        word_chain_game.stop_game(user_id)
        embed = discord.Embed(title="🛑 Dừng trò chơi", description="Trò chơi Nối Từ đã được dừng lại.", color=discord.Color.red())
        embed.set_footer(text="Bạn có thể bắt đầu một trò chơi mới bằng lệnh /noitu")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="❓ Không có trò chơi", description="Bạn chưa bắt đầu trò chơi Nối Từ nào.", color=discord.Color.yellow())
        embed.set_footer(text="Sử dụng /noitu để bắt đầu một trò chơi mới")
        await ctx.send(embed=embed)

# Lệnh Admin
def is_admin():
    async def predicate(ctx):
        return await bot.is_owner(ctx.author) or ctx.author.guild_permissions.administrator
    return commands.check(predicate)

@bot.command(name="shutdown")
@is_admin()
async def shutdown(ctx):
    """Tắt bot (Chỉ dành cho chủ sở hữu hoặc admin)."""
    embed = discord.Embed(title="🔌 Tắt bot", description="Đang tắt bot...", color=discord.Color.red())
    embed.set_footer(text="Bot sẽ ngừng hoạt động sau khi lệnh này được thực hiện.")
    await ctx.send(embed=embed)
    logger.warning(f"Bot được tắt bởi {ctx.author}")
    await bot.close()

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    """Kick một thành viên khỏi server."""
    await member.kick(reason=reason)
    embed = discord.Embed(title="👢 Kick thành viên", description=f"{member.mention} đã bị kick. Lý do: {reason}", color=discord.Color.orange())
    embed.set_footer(text="Hành động này đã được ghi lại.")
    await ctx.send(embed=embed)
    logger.info(f"{member} đã bị kick bởi {ctx.author}. Lý do: {reason}")

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    """Ban một thành viên khỏi server."""
    await member.ban(reason=reason)
    embed = discord.Embed(title="🔨 Ban thành viên", description=f"{member.mention} đã bị ban. Lý do: {reason}", color=discord.Color.red())
    embed.set_footer(text="Hành động này đã được ghi lại.")
    await ctx.send(embed=embed)
    logger.info(f"{member} đã bị ban bởi {ctx.author}. Lý do: {reason}")

@bot.command(name="warning")
@commands.has_permissions(manage_messages=True)
async def warning(ctx, member: discord.Member, *, reason):
    """Cảnh cáo một thành viên."""
    embed = discord.Embed(title="⚠️ Cảnh cáo", description=f"{member.mention} đã bị cảnh cáo. Lý do: {reason}", color=discord.Color.yellow())
    embed.set_footer(text="Đây là một cảnh báo chính thức. Vui lòng tuân thủ quy tắc server.")
    await ctx.send(embed=embed)
    logger.info(f"{member} đã bị cảnh cáo bởi {ctx.author}. Lý do: {reason}")

@bot.command(name="say")
@is_admin()
async def say(ctx, *, message):
    """Làm cho bot nói điều gì đó (Chỉ dành cho chủ sở hữu hoặc admin)."""
    await ctx.message.delete()
    await ctx.send(message)
    logger.info(f"Bot đã nói: '{message}' theo yêu cầu của {ctx.author}")

@bot.command(name="embed")
@is_admin()
async def embed(ctx, *, message):
    """Gửi một tin nhắn nhúng (Chỉ dành cho chủ sở hữu hoặc admin)."""
    embed = discord.Embed(description=message, color=discord.Color.random())
    embed.set_footer(text=f"Tin nhắn được gửi bởi {ctx.author}")
    await ctx.send(embed=embed)
    logger.info(f"Tin nhắn nhúng được gửi bởi {ctx.author}")

@bot.command(name="reload")
@is_admin()
async def reload(ctx, extension):
    """Tải lại một phần mở rộng của bot (Chỉ dành cho chủ sở hữu hoặc admin)."""
    try:
        await bot.reload_extension(f"cogs.{extension}")
        embed = discord.Embed(title="🔄 Tải lại phần mở rộng", description=f"Phần mở rộng {extension} đã được tải lại.", color=discord.Color.green())
        embed.set_footer(text="Các thay đổi đã được áp dụng.")
        await ctx.send(embed=embed)
        logger.info(f"Phần mở rộng {extension} đã được tải lại bởi {ctx.author}")
    except commands.ExtensionError as e:
        embed = discord.Embed(title="❌ Lỗi tải lại", description=f"Đã xảy ra lỗi khi tải lại {extension}: {e}", color=discord.Color.red())
        embed.set_footer(text="Vui lòng kiểm tra lại tên phần mở rộng và thử lại.")
        await ctx.send(embed=embed)
        logger.error(f"Lỗi khi tải lại phần mở rộng {extension}: {str(e)}")

@bot.command(name="sendcontact")
@is_admin()
async def send_contact(ctx, user: discord.User, *, message):
    """Gửi tin nhắn trực tiếp đến một người dùng (Chỉ dành cho chủ sở hữu hoặc admin)."""
    try:
        await user.send(message)
        embed = discord.Embed(title="✉️ Gửi tin nhắn", description=f"Đã gửi tin nhắn đến {user.name}.", color=discord.Color.green())
        embed.set_footer(text="Tin nhắn đã được gửi thành công.")
        await ctx.send(embed=embed)
        logger.info(f"Tin nhắn được gửi đến {user.name} bởi {ctx.author}")
    except discord.Forbidden:
        embed = discord.Embed(title="❌ Lỗi gửi tin nhắn", description=f"Không thể gửi tin nhắn đến {user.name}. Họ có thể đã tắt DM.", color=discord.Color.red())
        embed.set_footer(text="Vui lòng kiểm tra cài đặt quyền riêng tư của người dùng.")
        await ctx.send(embed=embed)
        logger.error(f"Không thể gửi tin nhắn đến {user.name}. Người dùng có thể đã tắt DM.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(title="❓ Lỗi lệnh", description="Không tìm thấy lệnh. Sử dụng `/helpme` để xem danh sách các lệnh có sẵn.", color=discord.Color.red())
        embed.set_footer(text="Kiểm tra lại chính tả của lệnh và thử lại.")
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(title="⚠️ Lỗi lệnh", description="Thiếu tham số bắt buộc. Vui lòng kiểm tra cú pháp lệnh.", color=discord.Color.yellow())
        embed.set_footer(text="Sử dụng /helpme <lệnh> để xem cách sử dụng lệnh.")
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CheckFailure):
        embed = discord.Embed(title="🚫 Lỗi quyền hạn", description="Bạn không có quyền sử dụng lệnh này.", color=discord.Color.red())
        embed.set_footer(text="Liên hệ với quản trị viên nếu bạn cần quyền truy cập.")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="❌ Lỗi không xác định", description="Đã xảy ra lỗi khi thực hiện lệnh. Vui lòng thử lại sau.", color=discord.Color.red())
        embed.set_footer(text="Nếu lỗi vẫn tiếp tục, hãy báo cáo cho đội ngũ phát triển.")
        await ctx.send(embed=embed)
        logger.error(f"Lỗi lệnh không xử lý được: {str(error)}")

# Hàm hỗ trợ
def get_context(user_id):
    if user_id not in short_term_memory:
        short_term_memory[user_id] = deque(maxlen=5)
    context = "\n".join(short_term_memory[user_id])
    
    cursor.execute("SELECT context FROM long_term_memory WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (user_id,))
    long_term_context = cursor.fetchone()
    if long_term_context:
        context = f"{long_term_context[0]}\n\n{context}"
    
    return context

def update_memory(user_id, user_message, bot_response):
    if user_id not in short_term_memory:
        short_term_memory[user_id] = deque(maxlen=5)
    short_term_memory[user_id].append(f"Người dùng: {user_message}")
    short_term_memory[user_id].append(f"Trợ lý AI: {bot_response}")
    
    context = "\n".join(short_term_memory[user_id])
    cursor.execute("INSERT INTO long_term_memory (user_id, context) VALUES (?, ?)", (user_id, context))
    conn.commit()

# Chạy bot
bot.run('MTMzNDQzMzAyNjA5NTk3NjYxMg.GuSbOl.OjZQpo4S9WAjkedl6obWoPAy9yjMDt8tQx1zfM')

