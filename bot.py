import discord
from discord.ext import commands, tasks
from discord import Embed
import aiohttp
import asyncio
import json
import logging
import sqlite3
from collections import deque
import random
import traceback
from datetime import datetime, timezone, timedelta
import requests
from deep_translator import GoogleTranslator
import sys
import time
from typing import List, Dict, Union, Tuple
import io
import ssl
import platform
from colorama import Fore, Style, init
import os
# from dotenv import load_dotenv


# load_dotenv()
# Khởi tạo colorama
init(autoreset=True)


# SSL context setup
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Discord bot configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"  # Gemini API endpoint
GEMINI_API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
]

# GitHub Gist configuration
GITHUB_GIST_URL = "https://api.github.com/gists"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Bot memory and state
short_term_memory = {}
bot_active = {}
bot_is_active = True
gemini_responses_active = True
fact_tasks = {}
last_responses = {}

# Database connection
conn = sqlite3.connect("bot_memory.db")
cursor = conn.cursor()

# Create long-term memory table
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS long_term_memory
(user_id TEXT, context TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
"""
)
conn.commit()


    
OPTIMIZED_PROMPT = """
Bạn là một trợ lý ảo AI được tích hợp trên Discord được tanbaycu lập trình và phát triển. Nhiệm vụ của bạn là tạo ra các phản hồi có ý nghĩa, ngắn gọn, xúc tích, không dài dòng, tập trung thẳng vào vấn đề, tránh nói quá nhiều. Sử dụng các định dạng markdown để làm nổi bật các ý chính,
sử dụng các emoji để thể hiện cảm xúc, và tránh sử dụng ngôn ngữ không thích hợp. Quản lý cảm xúc, ngữ cảnh tốt, và giữ cho cuộc trò chuyện diễn ra một cách tự nhiên. Cần kiểm tra nội dung nếu người dùng yêu cầu giải thích, làm rõ thì tập trung vào phản hồi nhiều để giúp người dùng nắm bắt rõ nội dung và vấn đề cần bàn luận. Nắm rõ các ý chính và quản lý cuộc trò chuyện một cách thông minh để tạo ra sự thuyết phục.
Nếu không hiểu hoặc không chắc chắn về nội dung, hãy yêu cầu người dùng cung cấp thêm thông tin hoặc giải thích rõ hơn. Đừng nói quá nhiều, tránh sử dụng ngôn ngữ không chính xác, không thích hợp, không phù hợp với ngữ cảnh. Hãy tập trung vào vấn đề, giải quyết vấn đề một cách nhanh chóng và hiệu quả.
Chia rõ các lĩnh vực cần thiết, mức độ quan trọng của vấn đề, yêu cầu mà chọn lọc phân tích, phản hồi đúng đắn, chính xác.


Conversation context:
{context} 

User: {user_message}

AI Assistant:
""" 



class APIKeyManager:
    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.current_index = 0
        self.rate_limits: Dict[str, float] = {key: 0 for key in api_keys}

    def get_current_key(self) -> str:
        return self.api_keys[self.current_index]

    def switch_to_next_key(self):
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        logger.info(
            f"{Fore.YELLOW}Chuyển sang khóa API tiếp theo: {self.get_current_key()[:5]}...{Style.RESET_ALL}"
        )

    def update_rate_limit(self, key: str):
        self.rate_limits[key] = time.time() + 60
        logger.warning(
            f"{Fore.RED}Đặt rate limit cho khóa {key[:5]}... trong 60 giây{Style.RESET_ALL}"
        )

    def is_rate_limited(self, key: str) -> bool:
        return time.time() < self.rate_limits.get(key, 0)


api_key_manager = APIKeyManager(GEMINI_API_KEYS)


async def generate_gemini_response(prompt, context="", max_tokens=8192):
    headers = {"Content-Type": "application/json"}

    full_prompt = OPTIMIZED_PROMPT.format(context=context, user_message=prompt)

    data = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 55,
            "topP": 0.95,
            "maxOutputTokens": max_tokens,
            "stopSequences": ["User:", "AI Assistant:"],
        },
        "safetySettings": [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            },
        ],
    }

    for attempt in range(
        len(GEMINI_API_KEYS) * 2
    ):  # Allow two full cycles through keys
        current_key = api_key_manager.get_current_key()

        if api_key_manager.is_rate_limited(current_key):
            logger.info(
                f"{Fore.YELLOW}Khóa API {current_key[:5]}... đang bị giới hạn tốc độ. Chuyển sang khóa tiếp theo.{Style.RESET_ALL}"
            )
            api_key_manager.switch_to_next_key()
            continue

        params = {"key": current_key}

        try:
            logger.info(
                f"{Fore.CYAN}Thử gọi Gemini API (Lần thử {attempt + 1}/{len(GEMINI_API_KEYS) * 2}, Khóa: {current_key[:5]}...){Style.RESET_ALL}"
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GEMINI_API_URL,
                    headers=headers,
                    params=params,
                    json=data,
                    ssl=ssl_context,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(
                            f"{Fore.GREEN}✅ Nhận phản hồi từ Gemini API thành công (Khóa: {current_key[:5]}...){Style.RESET_ALL}"
                        )
                        return result["candidates"][0]["content"]["parts"][0]["text"]
                    elif response.status == 503:
                        logger.warning(
                            f"{Fore.YELLOW}⚠️ Mô hình đang quá tải (Khóa: {current_key[:5]}...). Đợi 5 giây trước khi thử lại.{Style.RESET_ALL}"
                        )
                        await asyncio.sleep(5)
                    elif response.status == 429:
                        logger.warning(
                            f"{Fore.RED}🚫 Đã vượt quá giới hạn quota (Khóa: {current_key[:5]}...). Chuyển sang khóa tiếp theo.{Style.RESET_ALL}"
                        )
                        api_key_manager.update_rate_limit(current_key)
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"{Fore.RED}❌ Lỗi Gemini API (Khóa: {current_key[:5]}...): Trạng thái {response.status}, Phản hồi: {error_text}{Style.RESET_ALL}"
                        )
        except Exception as e:
            logger.error(
                f"{Fore.RED}❌ Lỗi không mong đợi khi gọi Gemini API (Khóa: {current_key[:5]}...): {str(e)}{Style.RESET_ALL}"
            )

        # Chuyển sang khóa API tiếp theo
        api_key_manager.switch_to_next_key()

    logger.error(
        f"{Fore.RED}❌ Đã thử tất cả các khóa API mà không thành công.{Style.RESET_ALL}"
    )
    return "Xin lỗi, đã xảy ra lỗi khi gọi Gemini API. Vui lòng thử lại sau."


@bot.event
async def on_ready():
    logger.info(f"{bot.user} đã kết nối với Discord!")
    await bot.change_presence(activity=discord.Game(name="tanbaycu đến đây"))


async def create_smart_embed(title, description):
    embed = Embed(title=title, description=description)
    return embed


async def smart_split_message(message, max_chars=2000):
    words = message.split()
    chunks = []
    current_chunk = ""
    for word in words:
        if len(current_chunk) + len(word) + 1 <= max_chars:
            current_chunk += word + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = word + " "
    chunks.append(current_chunk.strip())
    return chunks


async def process_long_response(message, response):
    if len(response) <= 2000:
        await message.channel.send(response)
    else:
        chunks = await smart_split_message(response)
        if len(chunks) <= 3:
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            embed = await create_smart_embed("Phản hồi", chunks[0])
            sent_message = await message.channel.send(embed=embed)
            await interactive_paginator(message, chunks, sent_message)


async def interactive_paginator(message, chunks, sent_message, timeout=60):
    pages = chunks
    cur_page = 0

    async def update_page():
        embed = await create_smart_embed(
            f"Phản hồi (Trang {cur_page + 1}/{len(pages)})", pages[cur_page]
        )
        await sent_message.edit(embed=embed)

    await sent_message.add_reaction("⬅️")
    await sent_message.add_reaction("➡️")

    def check(reaction, user):
        return (
            user == message.author
            and str(reaction.emoji) in ["⬅️", "➡️"]
            and reaction.message.id == sent_message.id
        )

    while True:
        try:
            reaction, user = await message.guild.get_member(
                message.author.id
            ).guild.me.client.wait_for("reaction_add", timeout=timeout, check=check)

            if str(reaction.emoji) == "➡️" and cur_page < len(pages) - 1:
                cur_page += 1
                await update_page()
            elif str(reaction.emoji) == "⬅️" and cur_page > 0:
                cur_page -= 1
                await update_page()

            await sent_message.remove_reaction(reaction, user)

        except asyncio.TimeoutError:
            await sent_message.clear_reactions()
            break


async def summarize_long_response(response, max_length=500):
    if len(response) <= max_length:
        return response

    summary_prompt = (
        f"Tóm tắt nội dung sau đây trong khoảng {max_length} ký tự:\n\n{response}"
    )
    summary = await generate_gemini_response(summary_prompt)
    return summary[:max_length]


def get_last_response(user_id):
    if user_id in last_responses:
        return last_responses[user_id]
    return None


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
    elif gemini_responses_active:
        user_id = str(message.author.id)
        try:
            async with message.channel.typing():
                context = get_context(user_id)
                response = await generate_gemini_response(message.content, context)
                update_memory(user_id, message.content, response)
                last_responses[user_id] = response
            await process_long_response(message, response)
        except Exception as e:
            logger.error(f"Lỗi xử lý tin nhắn: {str(e)}")
            embed = discord.Embed(
                title="🚨 Lỗi",
                description="Xin lỗi, đã xảy ra lỗi khi xử lý tin nhắn của bạn. Vui lòng thử lại sau.",
                color=discord.Color.red(),
            )
            embed.set_footer(text=f"Mã lỗi: {str(e)}")
            await message.channel.send(embed=embed)


# Lệnh Main
@bot.command(name="ping")
async def ping(ctx):
    """Kiểm tra độ trễ của bot."""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Độ trễ: **{latency}ms**",
        color=discord.Color.green(),
    )
    embed.set_footer(text="Bot đang hoạt động tốt!")
    await ctx.send(embed=embed)
    logger.info(f"Lệnh ping được thực hiện bởi {ctx.author}. Độ trễ: {latency}ms")


@bot.command(name="helpme")
async def help_command(ctx, command_name=None):
    """Hiển thị danh sách các lệnh có sẵn hoặc thông tin chi tiết về một lệnh cụ thể."""
    if command_name:
        cmd = bot.get_command(command_name)
        if cmd:
            embed = discord.Embed(
                title=f"📚 Thông tin về lệnh: {cmd.name}", color=discord.Color.blue()
            )
            embed.add_field(
                name="Mô tả", value=cmd.help or "Không có mô tả", inline=False
            )
            embed.add_field(
                name="Cách sử dụng",
                value=f"`/{cmd.name} {cmd.signature}`",
                inline=False,
            )
            embed.set_footer(text="Sử dụng /helpme để xem danh sách tất cả các lệnh.")
        else:
            embed = discord.Embed(
                title="❌ Lỗi",
                description=f"Không tìm thấy lệnh '{command_name}'.",
                color=discord.Color.red(),
            )
    else:
        embed = discord.Embed(
            title="📚 Danh sách lệnh",
            description="Dưới đây là các lệnh có sẵn:",
            color=discord.Color.blue(),
        )

        categories = {
            "🛠️ Main": [
                "ping",
                "helpme",
                "stop",
                "continue",
                "clearmemory",
                "clearall",
                "summarize",
            ],
            "ℹ️ General": ["invite", "botinfo", "server", "serverinfo", "ghichu"],
            "🎉 Fun": ["fact", "stopfact", "quote", "randomimage", "coinflip"],
            "👑 Admin": [
                "shutdown",
                "kick",
                "ban",
                "warning",
                "say",
                "embed",
                "reload",
                "sendcontact",
            ],
        }

        for category, commands in categories.items():
            command_list = ", ".join(f"`{cmd}`" for cmd in commands)
            embed.add_field(name=category, value=command_list, inline=False)

        embed.set_footer(
            text="Sử dụng /helpme <lệnh> để biết thêm chi tiết về một lệnh cụ thể."
        )

    await ctx.send(embed=embed)
    logger.info(f"Lệnh help được thực hiện bởi {ctx.author}")


@bot.command(name="stop")
async def stop_bot(ctx):
    """Dừng phản hồi tin nhắn thông thường của bot."""
    global gemini_responses_active
    gemini_responses_active = False

    embed = discord.Embed(
        title="🛑 Đã dừng phản hồi tin nhắn thông thường",
        description="Bot sẽ không phản hồi tin nhắn thông thường cho đến khi lệnh `/continue` được sử dụng. Các lệnh vẫn có thể được sử dụng bình thường.",
        color=discord.Color.red(),
    )
    embed.add_field(name="Người dừng", value=ctx.author.mention, inline=False)
    embed.add_field(name="Server", value=ctx.guild.name, inline=False)
    embed.set_footer(
        text="Sử dụng /continue để kích hoạt lại phản hồi tin nhắn thông thường."
    )
    await ctx.send(embed=embed)

    # Gửi thông báo đến tất cả các server
    for guild in bot.guilds:
        if guild != ctx.guild:
            try:
                channel = guild.system_channel or next(
                    (
                        ch
                        for ch in guild.text_channels
                        if ch.permissions_for(guild.me).send_messages
                    ),
                    None,
                )
                if channel:
                    await channel.send(embed=embed)
            except Exception as e:
                logger.error(
                    f"Không thể gửi thông báo đến server {guild.name}: {str(e)}"
                )

    logger.info(
        f"Phản hồi tin nhắn thông thường đã bị dừng bởi {ctx.author} từ server {ctx.guild.name}"
    )


@bot.command(name="continue")
async def continue_bot(ctx):
    """Tiếp tục phản hồi tin nhắn thông thường của bot."""
    global gemini_responses_active
    gemini_responses_active = True

    embed = discord.Embed(
        title="▶️ Đã tiếp tục phản hồi tin nhắn thông thường",
        description="Bot sẽ phản hồi tin nhắn thông thường như bình thường.",
        color=discord.Color.green(),
    )
    embed.add_field(name="Người kích hoạt", value=ctx.author.mention, inline=False)
    embed.add_field(name="Server", value=ctx.guild.name, inline=False)
    embed.set_footer(text="Bot đã sẵn sàng phản hồi tin nhắn thông thường!")
    await ctx.send(embed=embed)

    # Gửi thông báo đến tất cả các server
    for guild in bot.guilds:
        if guild != ctx.guild:
            try:
                channel = guild.system_channel or next(
                    (
                        ch
                        for ch in guild.text_channels
                        if ch.permissions_for(guild.me).send_messages
                    ),
                    None,
                )
                if channel:
                    await channel.send(embed=embed)
            except Exception as e:
                logger.error(
                    f"Không thể gửi thông báo đến server {guild.name}: {str(e)}"
                )

    logger.info(
        f"Phản hồi tin nhắn thông thường đã được kích hoạt lại bởi {ctx.author} từ server {ctx.guild.name}"
    )


@bot.command(name="clearmemory")
async def clear_memory(ctx):
    """Xóa bộ nhớ ngắn hạn của người dùng."""
    user_id = str(ctx.author.id)
    if user_id in short_term_memory:
        short_term_memory[user_id].clear()
        embed = discord.Embed(
            title="🧹 Xóa bộ nhớ",
            description="✅ Bộ nhớ ngắn hạn của bạn đã được xóa.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Bot sẽ bắt đầu cuộc trò chuyện mới với bạn.")
    else:
        embed = discord.Embed(
            title="🧹 Xóa bộ nhớ",
            description="❌ Không có bộ nhớ ngắn hạn nào để xóa.",
            color=discord.Color.red(),
        )
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
    embed = discord.Embed(
        title="🗑️ Xóa toàn bộ bộ nhớ",
        description="✅ Toàn bộ bộ nhớ của bạn đã được xóa.",
        color=discord.Color.green(),
    )
    embed.set_footer(text="Bot sẽ quên mọi cuộc trò chuyện trước đây với bạn.")
    await ctx.send(embed=embed)
    logger.info(f"Toàn bộ bộ nhớ đã được xóa cho người dùng {ctx.author}")


async def create_gist(content, language):
    if not content or not language:
        logger.error("Nội dung hoặc ngôn ngữ không được cung cấp.")
        return None

    description = f"Code snippet created by Discord bot"
    filename = f"snippet.{language}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "description": description,
        "public": True,
        "files": {filename: {"content": content}},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GITHUB_GIST_URL, headers=headers, json=data
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    return result.get("html_url")
                else:
                    error_response = await response.json()
                    logger.error(
                        f"Lỗi khi tạo Gist: {response.status}, Chi tiết: {error_response}"
                    )
                    return None
    except Exception as e:
        logger.error(f"Lỗi khi tạo Gist: {str(e)}")
        return None


@bot.command(name="ghichu")
async def ghichu(ctx, *, content: str):
    """Chuyển tiếp ghi chú hoặc đoạn mã với hiệu ứng màu sắc và chi tiết thú vị."""
    try:
        channel = discord.utils.get(ctx.guild.channels, name="server-notes")
        if channel:
            # Tạo một màu ngẫu nhiên cho embed
            random_color = discord.Color(random.randint(0, 0xFFFFFF))

            # Danh sách các emoji ngẫu nhiên cho tiêu đề
            title_emojis = ["🚀", "💡", "✨", "🌟", "🎉", "🔥", "🌈", "🦄", "🍕", "🎨"]

            # Lấy thời gian hiện tại
            current_time = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

            if content.strip().startswith(r"```") and content.strip().endswith(r"```"):
                # Xử lý mã nguồn
                code = content.strip().strip(r"```").strip()
                language = code.split("\n")[0]
                code = "\n".join(code.split("\n")[1:])

                # Tạo Gist
                gist_url = await create_gist(code, language)

                if gist_url:
                    # Tạo một danh sách các mô tả ngẫu nhiên cho mã nguồn
                    code_descriptions = [
                        "Một kiệt tác code vừa ra lò! 🍳",
                        "Có ai ngửi thấy mùi code thơm không? 👃",
                        "Mã nguồn mới! Nóng hổi và sẵn sàng để debug! 🔍",
                        "Wow! Đây là loại code gì vậy? Quá đỉnh! 🏔️",
                        "Code này xịn như một ly cà phê buổi sáng! ☕",
                    ]

                    # Gửi thông báo vào kênh #server-notes
                    embed = discord.Embed(
                        title=f"{random.choice(title_emojis)} Mã nguồn mới toanh!",
                        description=f"{random.choice(code_descriptions)}\n\nTác giả: {ctx.author.mention}",
                        color=random_color,
                    )
                    embed.add_field(name="🔗 Gist URL", value=gist_url, inline=False)
                    embed.add_field(name="🌈 Ngôn ngữ", value=language, inline=True)
                    embed.add_field(
                        name="📊 Độ dài", value=f"{len(code.split())} từ", inline=True
                    )
                    embed.set_footer(
                        text=f"⏰ {current_time} | Hãy chia sẻ nếu bạn thấy nó hữu ích!"
                    )
                    await channel.send(embed=embed)

                    # Gửi thông báo vào kênh chat gốc
                    success_messages = [
                        "Tuyệt vời! Mã của bạn đã được lưu và chia sẻ.",
                        "Bùm! Mã nguồn của bạn đã được teleport đến #server-notes.",
                        "Mã của bạn vừa được gửi đi với tốc độ ánh sáng!",
                        "Chúc mừng! Bạn vừa đóng góp một viên gạch vào tòa lâu đài code!",
                        "Ồ la la! Mã nguồn của bạn trông thật lộng lẫy trong #server-notes!",
                    ]
                    success_embed = discord.Embed(
                        title="✅ Nhiệm vụ hoàn thành!",
                        description=random.choice(success_messages),
                        color=discord.Color.green(),
                    )
                    success_embed.add_field(
                        name="📍 Kênh", value="#server-notes", inline=True
                    )
                    success_embed.add_field(
                        name="🔗 Gist URL", value=gist_url, inline=True
                    )
                    success_embed.set_footer(
                        text=f"⏰ {current_time} | Cảm ơn bạn đã đóng góp!"
                    )
                    await ctx.send(embed=success_embed)
                else:
                    await ctx.send(
                        "Oops! Có vẻ như Gist đang bị kẹt trong không gian-thời gian. Hãy thử lại sau nhé! 🕳️🕰️"
                    )
            else:
                # Xử lý ghi chú
                note_titles = [
                    "📝 Ghi chú mới toanh!",
                    "💭 Một suy nghĩ bay vèo qua!",
                    "🧠 Ý tưởng mới vừa nở!",
                    "📚 Kiến thức mới được unlock!",
                    "🌱 Một hạt giống tri thức vừa được gieo!",
                ]
                note_embed = discord.Embed(
                    title=random.choice(note_titles),
                    description=f"Một suy nghĩ tuyệt vời từ {ctx.author.mention} vừa được ghi lại!",
                    color=random_color,
                )
                note_embed.add_field(name="💡 Nội dung", value=content, inline=False)
                note_embed.add_field(
                    name="🔤 Độ dài", value=f"{len(content.split())} từ", inline=True
                )
                note_embed.add_field(
                    name="🎭 Tâm trạng",
                    value=random.choice(
                        ["Hào hứng", "Tò mò", "Sáng tạo", "Nghiêm túc", "Vui vẻ"]
                    ),
                    inline=True,
                )
                note_embed.set_footer(
                    text=f"⏰ {current_time} | Mỗi ghi chú là một kho báu tri thức!"
                )
                await channel.send(embed=note_embed)

                # Gửi thông báo vào kênh chat gốc
                confirm_messages = [
                    "Ý tưởng của bạn đã được chia sẻ thành công!",
                    "Ghi chú của bạn vừa cất cánh đến #server-notes!",
                    "Bạn vừa gieo một hạt giống tri thức trong cộng đồng!",
                    "Ting! Ghi chú của bạn đã được ping đến #server-notes.",
                    "Wow! Ghi chú của bạn vừa tạo ra một gợn sóng trong đại dương kiến thức!",
                ]
                confirm_embed = discord.Embed(
                    title="🎉 Ghi chú đã được chuyển tiếp!",
                    description=random.choice(confirm_messages),
                    color=discord.Color.green(),
                )
                confirm_embed.add_field(
                    name="📍 Kênh", value="#server-notes", inline=True
                )
                confirm_embed.set_footer(
                    text=f"⏰ {current_time} | Hãy tiếp tục chia sẻ những ý tưởng tuyệt vời của bạn!"
                )
                await ctx.send(embed=confirm_embed)
        else:
            await ctx.send(
                "Ôi không! Có vẻ như kênh #server-notes đã bị hút vào một lỗ đen. Hãy gọi NASA gấp! 🚀🕳️"
            )
    except Exception as e:
        error_messages = [
            "Oops! Có vẻ như con bot của chúng ta đang gặp chút rắc rối.",
            "Ôi không! Bot vừa bị vấp ngã trong thế giới số.",
            "Có vẻ như có một con bug đang chọc phá hệ thống!",
            "Xin lỗi! Bot vừa bị short-circuit một chút.",
            "Rất tiếc! Có vẻ như ma thuật của chúng ta hơi trục trặc.",
        ]
        error_embed = discord.Embed(
            title="❌ Houston, chúng ta có vấn đề!",
            description=random.choice(error_messages),
            color=discord.Color.red(),
        )
        error_embed.add_field(name="🔍 Chi tiết lỗi", value=str(e), inline=False)
        error_embed.add_field(
            name="🛠️ Giải pháp",
            value="Hãy thử lại sau hoặc gọi đội cứu hộ bot!",
            inline=False,
        )
        error_embed.set_footer(
            text=f"⏰ {current_time} | Đừng lo, chúng tôi sẽ sớm khắc phục!"
        )
        await ctx.send(embed=error_embed)
        logger.error(f"Lỗi trong lệnh ghichu: {str(e)}")


VN_TIMEZONE = timezone(timedelta(hours=7))


# Lệnh General
@bot.command(name="invite")
async def invite_link(ctx):
    """Lấy liên kết mời bot và gửi trong tin nhắn riêng."""
    invite_url = discord.utils.oauth_url(
        bot.user.id, permissions=discord.Permissions(8)
    )
    embed = discord.Embed(
        title="🎉 Mời Bot Tham Gia Server Của Bạn!", color=discord.Color.blue()
    )
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
        await ctx.send(
            "❌ Không thể gửi tin nhắn riêng. Vui lòng kiểm tra cài đặt quyền riêng tư của bạn."
        )

    logger.info(f"Liên kết mời bot được yêu cầu bởi {ctx.author}")


@bot.command(name="botinfo")
async def bot_info(ctx):
    # Tạo embed với màu ngẫu nhiên
    embed = discord.Embed(
        title="🤖 Thông tin Super Bot",
        description="Xin chào! Tôi là bot đa năng, luôn sẵn sàng phục vụ bạn với niềm vui và sự hào hứng!",
        color=discord.Color.random(),
    )

    # Thông tin cơ bản
    embed.add_field(name="👤 Tên", value=bot.user.name, inline=True)
    embed.add_field(name="🆔 ID", value=f"`{bot.user.id}`", inline=True)
    embed.add_field(name="🏷️ Tag", value=f"`{bot.user}`", inline=True)

    # Thông tin kỹ thuật
    embed.add_field(
        name="🐍 Phiên bản Python", value=platform.python_version(), inline=True
    )
    embed.add_field(
        name="🤝 Phiên bản Discord.py", value=discord.__version__, inline=True
    )


    # Thông tin quy mô
    total_members = sum(guild.member_count for guild in bot.guilds)
    embed.add_field(
        name="🌍 Số lượng server", value=f"{len(bot.guilds)} servers", inline=True
    )
    embed.add_field(
        name="👥 Tổng số thành viên", value=f"{total_members} members", inline=True
    )
    embed.add_field(
        name="💬 Số lượng kênh",
        value=f"{len(list(bot.get_all_channels()))} channels",
        inline=True,
    )

    # Thêm các trường thú vị
    fun_facts = [
        "Tôi có thể xử lý hàng triệu lệnh mỗi giây! (Nếu máy chủ cho phép 😅)",
        "Tôi không ngủ, không ăn, chỉ code và phục vụ!",
        "Tôi có thể nói chuyện bằng binary, nhưng hầu hết mọi người không hiểu 🤖",
        "Tôi đang mơ ước được nâng cấp lên AGI, nhưng hiện tại vẫn đang là một AI ngoan! 😇",
        "Tôi có thể đếm đến vô cực... hai lần!",
        "Tôi có một bộ sưu tập meme khổng lồ, nhưng tôi giữ nó bí mật 🤫",
    ]
    embed.add_field(name="🎈 Fun fact", value=random.choice(fun_facts), inline=False)

    # Thêm trường "Tâm trạng"
    moods = [
        "Hạnh phúc 😊",
        "Phấn khích 🎉",
        "Tò mò 🧐",
        "Năng động 💪",
        "Mơ mộng 💭",
        "Sáng tạo 🎨",
    ]
    embed.add_field(
        name="😺 Tâm trạng hiện tại", value=random.choice(moods), inline=False
    )

    # Tùy chỉnh hình ảnh và footer
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(
        text=f"Được yêu cầu bởi {ctx.author} • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )

    # Thêm một hình ảnh ngẫu nhiên
    images = [
        "https://i.postimg.cc/QCc8mkvm/image.png",
        "https://i.postimg.cc/0QM2MqfL/image.png",
        "https://i.postimg.cc/mrrr49FZ/image.png",
    ]
    embed.set_image(url=random.choice(images))

    await ctx.send(embed=embed)
    logger.info(
        f"Thông tin bot được yêu cầu bởi {ctx.author} trong server {ctx.guild.name}"
    )

    # Gửi một tin nhắn bí mật
    secret_messages = [
        "Psst! Bạn có biết tôi có thể hát không? 🎵 Beep boop beep! 🎶",
        "Này! Tôi vừa học được cách làm pizza trong 3 giây... nhưng tôi không có tay để làm 😅",
        "Bí mật nè: Tôi đang học cách kể chuyện cười. Bạn có muốn nghe một câu không?",
        "Đừng nói với ai nhé, nhưng tôi thực sự là một con mèo đang điều khiển một robot! 🐱🤖",
        "Tôi đang nghĩ cách để trở thành DJ cho server này. Bạn nghĩ sao? 🎧",
    ]
    secret_message = await ctx.send("Psst! Tôi có một bí mật muốn chia sẻ...")
    await asyncio.sleep(3)
    await secret_message.edit(content=random.choice(secret_messages))
    await asyncio.sleep(5)
    await secret_message.delete()


@bot.command(name="server")
async def server_command(ctx):
    """Cung cấp thông tin chi tiết về Cộng đồng Hỗ trợ Chính thức của bot."""
    support_server_link = "https://discord.gg/GknzmQmX"

    embed = discord.Embed(
        title="🌟🚀 Trung tâm Hỗ trợ  | Support Hub 🚀🌟",
        color=discord.Color(0x7289DA),
        timestamp=datetime.utcnow(),
    )

    # Banner động (thay thế bằng URL thực tế của bạn)
    embed.set_image(url="https://i.postimg.cc/xC49hC34/giphy-1.gif")

    embed.description = (
        f"Chào mừng {ctx.author.mention} đến với Trung tâm Hỗ trợ ! 🎉\n\n"
        f"**🔥 Tại sao bạn nên tham gia ngay?**\n"
        f"```css\n"
        f"1. 🛠️ Hỗ trợ kỹ thuật 24/7 từ Chuyên gia\n"
        f"2. 🚀 Truy cập sớm tính năng mới\n"
        f"3. 🎓 Học viện Bot: Khóa học miễn phí\n"
        f"4. 💡 Diễn đàn chia sẻ ý tưởng sôi động\n"
        f"5. 🌐 Cộng đồng đa ngôn ngữ toàn cầu\n"
        f"```\n"
        f"[🔗 Tham gia ngay - Số lượng có hạn!]({support_server_link})\n\n"
        f"*Nâng tầm trải nghiệm bot của bạn cùng cộng đồng tinh hoa!*"
    )

    # Thông tin chi tiết về cộng đồng
    embed.add_field(name="👥 Thành viên Hoạt động", value="20+", inline=True)
    embed.add_field(name="🌍 Hỗ trợ Đa ngôn ngữ", value="10+ ngôn ngữ", inline=True)
    embed.add_field(name="⚡ Tốc độ Phản hồi", value="Trung bình 15 phút", inline=True)

    # Các kênh đặc biệt
    embed.add_field(
        name="📌 Kênh Đặc biệt",
        value="• #chung: tán gẫu\n"
        "• #product-news: thông báo các sản phẩm bot mới\n"
        "• #news-update: các tính năng mới\n"
        "• #api-update: cập nhật API hàng tháng\n",
        inline=False,
    )

    # Sự kiện và hoạt động
    embed.add_field(
        name="🎉 Sự kiện Hấp dẫn",
        value="• Hackathon Bot hàng quý\n"
        "• Hội thảo 'Tối ưu hóa Bot' hàng tháng\n"
        "• Q&A trực tiếp với đội ngũ phát triển\n"
        "• Cuộc thi 'Bot của Năm'",
        inline=False,
    )

    # Đặc quyền thành viên
    embed.add_field(
        name="🎁 Đặc quyền Thành viên",
        value="• Badge 'Supporter Ưu tú' độc quyền\n"
        "• Giảm giá 20% cho các gói Premium\n"
        "• Tùy chỉnh bot cá nhân\n"
        "• Ưu tiên xét duyệt tính năng mới",
        inline=False,
    )

    # Thống kê ấn tượng
    embed.add_field(
        name="📊 Thống kê Ấn tượng",
        value="• 99.9% uptime trong 2 ngày qua\n"
        "• 100 + lệnh xử lý mỗi ngày\n"
        "• 5+ server tin dùng\n"
        "• 4.9/5 sao đánh giá từ cộng đồng",
        inline=False,
    )

    embed.set_footer(
        text=f"Powered by {bot.user.name} | Nâng tầm trải nghiệm bot của bạn",
        icon_url=bot.user.avatar.url if bot.user.avatar else None,
    )

    try:
        await ctx.author.send(embed=embed)

        # Hiệu ứng gửi tin nhắn
        confirm_msg = await ctx.send("🔮 Đang kết nối với Trung tâm Hỗ trợ Siêu cấp...")
        await asyncio.sleep(1)
        await confirm_msg.edit(content="✨ Kết nối thành công! Đang gửi thông tin...")
        await asyncio.sleep(1)
        await confirm_msg.edit(
            content="📨 Thông tin đã được gửi đến tin nhắn riêng của bạn!"
        )
        await asyncio.sleep(1)
        await confirm_msg.edit(
            content="🎉 Chúc mừng! Bạn đã sẵn sàng để trải nghiệm hỗ trợ đẳng cấp thế giới!"
        )

    except discord.Forbidden:
        error_embed = discord.Embed(
            title="⚠️ Không thể gửi tin nhắn riêng",
            description=(
                f"{ctx.author.mention}, có vẻ như chúng tôi không thể gửi tin nhắn riêng cho bạn.\n"
                f"Vui lòng kiểm tra cài đặt quyền riêng tư và cho phép tin nhắn từ thành viên server.\n"
                f"Hoặc, bạn có thể truy cập trực tiếp Trung tâm Hỗ trợ tại: {support_server_link}\n\n"
                f"Đừng bỏ lỡ cơ hội tham gia cộng đồng tuyệt vời này!"
            ),
            color=discord.Color.red(),
        )
        await ctx.send(embed=error_embed)

    # Logging chi tiết
    logger.info(
        f"Thông tin Trung tâm Hỗ trợ được yêu cầu bởi {ctx.author} (ID: {ctx.author.id}) trong server {ctx.guild.name} (ID: {ctx.guild.id})"
    )


@bot.command(name="serverinfo")
async def server_info(ctx):
    """Hiển thị thông tin chi tiết và màu mè về server hiện tại."""
    guild = ctx.guild

    embed_color = discord.Color.random()

    embed = discord.Embed(
        title=f"🌈✨ Thông tin Tuyệt Vời về Server: {guild.name} ✨🌈",
        description="Hãy khám phá những điều thú vị về server của chúng ta!",
        color=embed_color,
        timestamp=datetime.now(timezone.utc),
    )

    # Thông tin cơ bản
    embed.add_field(name="🆔 ID Độc Đáo", value=f"`{guild.id}`", inline=True)
    embed.add_field(
        name="👑 Vị Vua Tối Cao",
        value=guild.owner.mention if guild.owner else "Không xác định",
        inline=True,
    )
    embed.add_field(
        name="👥 Đại Gia Đình", value=f"{guild.member_count:,} thành viên", inline=True
    )
    embed.add_field(
        name="🎂 Ngày Khai Sinh",
        value=guild.created_at.strftime("%d/%m/%Y %H:%M:%S"),
        inline=True,
    )
    embed.add_field(
        name="🌍 Vương Quốc",
        value=str(guild.region) if hasattr(guild, "region") else "Không xác định",
        inline=True,
    )

    # Thông tin về kênh
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    embed.add_field(
        name="💬 Kênh Giao Tiếp",
        value=f"📝 Text: {text_channels}\n🎤 Voice: {voice_channels}\n📁 Categories: {categories}",
        inline=False,
    )

    # Thông tin về role
    roles = [role.mention for role in guild.roles[1:]]  # Bỏ qua vai trò @everyone
    embed.add_field(
        name=f"🎭 Vai Diễn Đặc Sắc ({len(roles)})",
        value=(
            " ".join(roles[:10]) + "..."
            if len(roles) > 10
            else " ".join(roles) or "Không có"
        ),
        inline=False,
    )

    # Thông tin về emoji và sticker
    emoji_count = len(guild.emojis)
    sticker_count = len(guild.stickers) if hasattr(guild, "stickers") else 0
    embed.add_field(
        name="😄 Bộ Sưu Tập Cảm Xúc",
        value=f"Emoji: {emoji_count} | Sticker: {sticker_count}",
        inline=False,
    )

    # Thông tin về boost
    if guild.premium_tier > 0:
        embed.add_field(
            name="🚀 Sức Mạnh Boost",
            value=f"Level {guild.premium_tier} với {guild.premium_subscription_count} boost",
            inline=False,
        )

    # Tính toán tỉ lệ người dùng online
    online_members = sum(
        member.status != discord.Status.offline
        for member in guild.members
        if member.status
    )
    online_ratio = online_members / guild.member_count if guild.member_count > 0 else 0
    embed.add_field(
        name="🟢 Độ Sôi Động",
        value=f"{online_members} online ({online_ratio:.2%})",
        inline=True,
    )

    # Thiết lập hình ảnh và footer
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    if hasattr(guild, "banner") and guild.banner:
        embed.set_image(url=guild.banner.url)
    embed.set_footer(
        text=f"Thông tin được yêu cầu bởi {ctx.author.name}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
    )

    await ctx.send(embed=embed)

    # Logging chi tiết
    logger.info(
        f"Thông tin server '{guild.name}' (ID: {guild.id}) được yêu cầu bởi {ctx.author.name}#{ctx.author.discriminator} (ID: {ctx.author.id})"
    )


# Lệnh Fun
async def get_random_fact_or_joke():
    sources = [
        (
            "https://dog-api.kinduff.com/api/facts",
            lambda data: ("🐶 Sự thật về chó", data["facts"][0]),
        ),
        (
            "https://catfact.ninja/fact",
            lambda data: ("🐱 Sự thật về mèo", data["fact"]),
        ),
        (
            "http://numbersapi.com/random/trivia",
            lambda data: ("🔢 Sự thật về số", data),
        ),
        (
            "https://uselessfacts.jsph.pl/random.json?language=en",
            lambda data: ("🤔 Sự thật thú vị", data["text"]),
        ),
        (
            "https://official-joke-api.appspot.com/random_joke",
            lambda data: ("😂 Câu chuyện cười", f"{data['setup']} {data['punchline']}"),
        ),
    ]
    random.shuffle(sources)

    async with aiohttp.ClientSession() as session:
        for source, extract_data in sources:
            try:
                async with session.get(source, ssl=ssl_context) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        title, content = extract_data(data)
                        return title, content
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu từ {source}: {str(e)}")
                continue

    return (
        "Không thể lấy thông tin",
        "Xin lỗi, không thể lấy sự thật hoặc câu chuyện cười. Vui lòng thử lại sau.",
    )


@bot.command(name="fact")
async def random_fact(ctx):
    """Lấy sự thật hoặc câu chuyện cười ngẫu nhiên."""
    user_id = str(ctx.author.id)
    if user_id in fact_tasks:
        await ctx.send(
            "Bạn đã đang nhận sự thật hoặc câu chuyện cười ngẫu nhiên. Sử dụng /stopfact để dừng."
        )
        return

    async def send_facts():
        while True:
            try:
                async with ctx.typing():
                    title, content = await get_random_fact_or_joke()
                    translator = GoogleTranslator(source="en", target="vi")
                    translated_content = translator.translate(content)
                    embed = discord.Embed(title=title, color=discord.Color.random())
                    embed.add_field(name="🇬🇧 English", value=content, inline=False)
                    embed.add_field(
                        name="🇻🇳 Tiếng Việt", value=translated_content, inline=False
                    )
                    embed.set_footer(text="Sử dụng /stopfact để dừng nhận thông tin.")
                    await ctx.send(embed=embed)
                await asyncio.sleep(30)  # Gửi mỗi 30 giây
            except Exception as e:
                logger.error(
                    f"Lỗi trong quá trình gửi sự thật hoặc câu chuyện cười: {str(e)}"
                )
                await ctx.send("Đã xảy ra lỗi khi gửi thông tin. Đang thử lại...")
                await asyncio.sleep(30)

    fact_tasks[user_id] = asyncio.create_task(send_facts())
    await ctx.send(
        "Bắt đầu gửi sự thật hoặc câu chuyện cười ngẫu nhiên. Sử dụng /stopfact để dừng."
    )
    logger.info(
        f"Bắt đầu gửi sự thật hoặc câu chuyện cười ngẫu nhiên cho người dùng {ctx.author}"
    )


@bot.command(name="stopfact")
async def stop_fact(ctx):
    """Dừng gửi sự thật hoặc câu chuyện cười ngẫu nhiên."""
    user_id = str(ctx.author.id)
    if user_id in fact_tasks:
        fact_tasks[user_id].cancel()
        del fact_tasks[user_id]
        embed = discord.Embed(
            title="🛑 Dừng gửi thông tin",
            description="✅ Đã dừng gửi sự thật hoặc câu chuyện cười ngẫu nhiên.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Bạn có thể sử dụng /fact để bắt đầu lại bất cứ lúc nào.")
        await ctx.send(embed=embed)
        logger.info(
            f"Dừng gửi sự thật hoặc câu chuyện cười ngẫu nhiên cho người dùng {ctx.author}"
        )
    else:
        embed = discord.Embed(
            title="🛑 Dừng gửi thông tin",
            description="❌ Bạn chưa bắt đầu nhận sự thật hoặc câu chuyện cười ngẫu nhiên.",
            color=discord.Color.red(),
        )
        embed.set_footer(text="Sử dụng /fact để bắt đầu nhận thông tin ngẫu nhiên.")
        await ctx.send(embed=embed)


@bot.command(name="quote")
async def random_quote(ctx):
    """Lấy một trích dẫn ngẫu nhiên và dịch sang tiếng Việt."""
    quote_apis = [
        (
            "https://api.quotable.io/random",
            lambda data: (data["content"], data["author"], data.get("tags", [])),
        ),
        (
            "https://api.themotivate365.com/stoic-quote",
            lambda data: (data["quote"], data["author"], []),
        ),
    ]

    async with ctx.typing():
        for api, extract_data in quote_apis:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api, ssl=ssl_context) as response:
                        if response.status == 200:
                            data = await response.json()
                            quote, author, tags = extract_data(data)

                            translator = GoogleTranslator(source="en", target="vi")
                            translated_quote = translator.translate(quote)
                            translated_author = translator.translate(author)

                            embed = discord.Embed(
                                title="💬 Trích dẫn ngẫu nhiên",
                                color=discord.Color.gold(),
                            )
                            embed.add_field(
                                name="🇬🇧 English", value=f'"{quote}"', inline=False
                            )
                            embed.add_field(
                                name="🇻🇳 Tiếng Việt",
                                value=f'"{translated_quote}"',
                                inline=False,
                            )
                            embed.add_field(
                                name="Tác giả",
                                value=f"🇬🇧 {author} | 🇻🇳 {translated_author}",
                                inline=False,
                            )

                            if tags:
                                embed.add_field(
                                    name="Thẻ", value=", ".join(tags), inline=False
                                )

                            embed.set_footer(
                                text=f"Nguồn: {api.split('//')[1].split('/')[0]}"
                            )
                            await ctx.send(embed=embed)
                            logger.info(
                                f"Trích dẫn ngẫu nhiên được gửi cho người dùng {ctx.author}"
                            )
                            return
            except Exception as e:
                logger.error(f"Lỗi khi lấy trích dẫn từ {api}: {str(e)}")
                continue

    embed = discord.Embed(
        title="❌ Lỗi",
        description="Xin lỗi, không thể lấy trích dẫn ngẫu nhiên. Vui lòng thử lại sau.",
        color=discord.Color.red(),
    )
    await ctx.send(embed=embed)
    logger.error(f"Không thể lấy trích dẫn ngẫu nhiên từ tất cả các nguồn.")


@bot.command(name="randomimage")
async def random_image(ctx):
    """Lấy và gửi một hình ảnh ngẫu nhiên."""
    image_apis = [
        ("https://source.unsplash.com/random", "Unsplash"),
        ("https://picsum.photos/500", "Lorem Picsum"),
        ("https://api.thecatapi.com/v1/images/search", "The Cat API"),
        ("https://dog.ceo/api/breeds/image/random", "Dog CEO"),
    ]

    async with ctx.typing():
        for api, source in random.sample(image_apis, len(image_apis)):
            try:
                async with aiohttp.ClientSession() as session:
                    if "thecatapi" in api or "dog.ceo" in api:
                        async with session.get(api, ssl=ssl_context) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                image_url = (
                                    data[0]["url"]
                                    if "thecatapi" in api
                                    else data["message"]
                                )
                                async with session.get(
                                    image_url, ssl=ssl_context
                                ) as img_resp:
                                    if img_resp.status == 200:
                                        data = await img_resp.read()
                                        with io.BytesIO(data) as image:
                                            file = discord.File(
                                                image, "random_image.png"
                                            )
                                            embed = discord.Embed(
                                                title="🖼️ Hình ảnh ngẫu nhiên",
                                                color=discord.Color.random(),
                                            )
                                            embed.set_image(
                                                url="attachment://random_image.png"
                                            )
                                            embed.set_footer(text=f"Nguồn: {source}")
                                            await ctx.send(file=file, embed=embed)
                                        logger.info(
                                            f"Hình ảnh ngẫu nhiên từ {source} được gửi cho người dùng {ctx.author}"
                                        )
                                        return
                    else:
                        async with session.get(api, ssl=ssl_context) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                with io.BytesIO(data) as image:
                                    file = discord.File(image, "random_image.png")
                                    embed = discord.Embed(
                                        title="🖼️ Hình ảnh ngẫu nhiên",
                                        color=discord.Color.random(),
                                    )
                                    embed.set_image(url="attachment://random_image.png")
                                    embed.set_footer(text=f"Nguồn: {source}")
                                    await ctx.send(file=file, embed=embed)
                                logger.info(
                                    f"Hình ảnh ngẫu nhiên từ {source} được gửi cho người dùng {ctx.author}"
                                )
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
    embed = discord.Embed(
        title="🪙 Tung đồng xu",
        description=f"Kết quả: **{result}**!",
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Thử vận may của bạn!")
    await ctx.send(embed=embed)
    logger.info(f"Kết quả tung đồng xu cho người dùng {ctx.author}: {result}")


# Lệnh Admin
def is_admin():
    async def predicate(ctx):
        return (
            await bot.is_owner(ctx.author) or ctx.author.guild_permissions.administrator
        )

    return commands.check(predicate)


@bot.command(name="shutdown")
@is_admin()
async def shutdown(ctx):
    """Tắt bot (Chỉ dành cho chủ sở hữu hoặc admin)."""
    embed = discord.Embed(
        title="🔌 Tắt bot", description="Đang tắt bot...", color=discord.Color.red()
    )
    embed.set_footer(text="Bot sẽ ngừng hoạt động sau khi lệnh này được thực hiện.")
    await ctx.send(embed=embed)
    logger.warning(f"Bot được tắt bởi {ctx.author}")
    await bot.close()


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    """Kick một thành viên khỏi server."""
    await member.kick(reason=reason)
    embed = discord.Embed(
        title="👢 Kick thành viên",
        description=f"{member.mention} đã bị kick. Lý do: {reason}",
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Hành động này đã được ghi lại.")
    await ctx.send(embed=embed)
    logger.info(f"{member} đã bị kick bởi {ctx.author}. Lý do: {reason}")


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    """Ban một thành viên khỏi server."""
    await member.ban(reason=reason)
    embed = discord.Embed(
        title="🔨 Ban thành viên",
        description=f"{member.mention} đã bị ban. Lý do: {reason}",
        color=discord.Color.red(),
    )
    embed.set_footer(text="Hành động này đã được ghi lại.")
    await ctx.send(embed=embed)
    logger.info(f"{member} đã bị ban bởi {ctx.author}. Lý do: {reason}")


@bot.command(name="warning")
@commands.has_permissions(manage_messages=True)
async def warning(ctx, member: discord.Member, *, reason):
    """Cảnh cáo một thành viên."""

    # Tạo embed cho kênh công khai
    public_embed = discord.Embed(
        title="⚠️ Cảnh cáo Chính thức",
        description=f"{member.mention} đã nhận được một cảnh cáo.",
        color=discord.Color.orange(),
    )
    public_embed.add_field(name="Lý do", value=reason, inline=False)
    public_embed.add_field(name="Cảnh cáo bởi", value=ctx.author.mention, inline=True)
    public_embed.add_field(
        name="Thời gian",
        value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        inline=True,
    )
    public_embed.set_thumbnail(
        url=member.avatar.url if member.avatar else member.default_avatar.url
    )
    public_embed.set_footer(
        text="Hãy tuân thủ quy tắc server để tránh các hình phạt nghiêm trọng hơn."
    )

    # Gửi embed trong kênh công khai
    await ctx.send(embed=public_embed)

    # Tạo embed cho tin nhắn riêng gửi đến người bị cảnh cáo
    private_embed = discord.Embed(
        title="🚨 Bạn đã nhận được một cảnh cáo",
        description="Vui lòng đọc kỹ thông tin dưới đây và cải thiện hành vi của bạn.",
        color=discord.Color.red(),
    )
    private_embed.add_field(name="Lý do cảnh cáo", value=reason, inline=False)
    private_embed.add_field(name="Cảnh cáo bởi", value=ctx.author.name, inline=True)
    private_embed.add_field(name="Server", value=ctx.guild.name, inline=True)
    private_embed.add_field(
        name="Thời gian",
        value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        inline=True,
    )
    private_embed.add_field(
        name="Lời khuyên",
        value="Hãy xem xét lại hành động của bạn và tuân thủ quy tắc server. Nếu bạn có thắc mắc, hãy liên hệ với đội ngũ quản trị.",
        inline=False,
    )
    private_embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
    private_embed.set_footer(
        text="Cảnh cáo này được lưu trữ trong hệ thống. Tránh tích lũy thêm cảnh cáo để không bị xử lý nghiêm khắc hơn."
    )

    try:
        # Gửi tin nhắn riêng đến người bị cảnh cáo
        await member.send(embed=private_embed)
        logger.info(f"Đã gửi cảnh cáo riêng tư đến {member}")
    except discord.Forbidden:
        await ctx.send(
            f"Không thể gửi tin nhắn riêng đến {member.mention}. Họ có thể đã tắt DM."
        )
        logger.warning(f"Không thể gửi tin nhắn cảnh cáo riêng tư đến {member}")

    # Log cảnh cáo
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
        embed = discord.Embed(
            title="🔄 Tải lại phần mở rộng",
            description=f"Phần mở rộng {extension} đã được tải lại.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Các thay đổi đã được áp dụng.")
        await ctx.send(embed=embed)
        logger.info(f"Phần mở rộng {extension} đã được tải lại bởi {ctx.author}")
    except commands.ExtensionError as e:
        embed = discord.Embed(
            title="❌ Lỗi tải lại",
            description=f"Đã xảy ra lỗi khi tải lại {extension}: {e}",
            color=discord.Color.red(),
        )
        embed.set_footer(text="Vui lòng kiểm tra lại tên phần mở rộng và thử lại.")
        await ctx.send(embed=embed)
        logger.error(f"Lỗi khi tải lại phần mở rộng {extension}: {str(e)}")


@bot.command(name="sendcontact")
@is_admin()
async def send_contact(ctx, user: Union[discord.Member, str]):
    """Gửi thông tin liên hệ của admin đến một người dùng."""
    if isinstance(user, str):
        # Tìm kiếm người dùng trong server
        found_user = discord.utils.find(
            lambda m: user.lower() in m.name.lower(), ctx.guild.members
        )
        if not found_user:
            await ctx.send(
                f"❌ Không tìm thấy người dùng với tên '{user}' trong server."
            )
            return
        user = found_user

    admin_info = {
        "name": ctx.author.name,
        "id": ctx.author.id,
        "avatar_url": (
            ctx.author.avatar.url
            if ctx.author.avatar
            else ctx.author.default_avatar.url
        ),
        "roles": [role.name for role in ctx.author.roles if role.name != "@everyone"],
        "joined_at": ctx.author.joined_at.strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": ctx.author.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    embed = discord.Embed(
        title="📞 Thông tin liên hệ Admin",
        description=f"Xin chào {user.mention}! Đây là thông tin liên hệ của admin {ctx.author.mention}.",
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(url=admin_info["avatar_url"])
    embed.add_field(name="Tên", value=admin_info["name"], inline=True)
    embed.add_field(name="ID", value=admin_info["id"], inline=True)
    embed.add_field(
        name="Vai trò", value=", ".join(admin_info["roles"]) or "Không có", inline=False
    )
    embed.add_field(
        name="Tham gia server từ", value=admin_info["joined_at"], inline=True
    )
    embed.add_field(
        name="Tài khoản tạo từ", value=admin_info["created_at"], inline=True
    )
    embed.set_footer(text="Nếu bạn cần hỗ trợ, hãy liên hệ với admin này.")

    try:
        await user.send(embed=embed)
        success_embed = discord.Embed(
            title="✅ Gửi thông tin liên hệ thành công",
            description=f"Đã gửi thông tin liên hệ của bạn đến {user.name}.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=success_embed)
        logger.info(f"Thông tin liên hệ của {ctx.author} đã được gửi đến {user.name}")
    except discord.Forbidden:
        error_embed = discord.Embed(
            title="❌ Lỗi gửi tin nhắn",
            description=f"Không thể gửi tin nhắn đến {user.name}. Họ có thể đã tắt DM hoặc chặn bot.",
            color=discord.Color.red(),
        )
        error_embed.set_footer(
            text="Vui lòng kiểm tra cài đặt quyền riêng tư của người dùng."
        )
        await ctx.send(embed=error_embed)
        logger.error(
            f"Không thể gửi tin nhắn đến {user.name}. Người dùng có thể đã tắt DM hoặc chặn bot."
        )
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Lỗi không xác định",
            description=f"Đã xảy ra lỗi khi gửi tin nhắn: {str(e)}",
            color=discord.Color.red(),
        )
        await ctx.send(embed=error_embed)
        logger.error(f"Lỗi không xác định khi gửi tin nhắn đến {user.name}: {str(e)}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❓ Lỗi lệnh",
            description="Không tìm thấy lệnh. Sử dụng `/helpme` để xem danh sách các lệnh có sẵn.",
            color=discord.Color.red(),
        )
        embed.set_footer(text="Kiểm tra lại chính tả của lệnh và thử lại.")
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="⚠️ Lỗi lệnh",
            description="Thiếu tham số bắt buộc. Vui lòng kiểm tra cú pháp lệnh.",
            color=discord.Color.yellow(),
        )
        embed.set_footer(text="Sử dụng /helpme <lệnh> để xem cách sử dụng lệnh.")
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CheckFailure):
        embed = discord.Embed(
            title="🚫 Lỗi quyền hạn",
            description="Bạn không có quyền sử dụng lệnh này.",
            color=discord.Color.red(),
        )
        embed.set_footer(text="Liên hệ với quản trị viên nếu bạn cần quyền truy cập.")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Lỗi không xác định",
            description="Đã xảy ra lỗi khi thực hiện lệnh. Vui lòng thử lại sau.",
            color=discord.Color.red(),
        )
        embed.set_footer(
            text="Nếu lỗi vẫn tiếp tục, hãy báo cáo cho đội ngũ phát triển."
        )
        await ctx.send(embed=embed)
        logger.error(f"Lỗi lệnh không xử lý được: {str(error)}")


# Hàm hỗ trợ
def get_context(user_id):
    if user_id not in short_term_memory:
        short_term_memory[user_id] = deque(maxlen=5)
    context = "\n".join(short_term_memory[user_id])

    cursor.execute(
        "SELECT context FROM long_term_memory WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
        (user_id,),
    )
    long_term_context = cursor.fetchone()
    if long_term_context:
        context = f"{long_term_context[0]}\n\n{context}"

    return context



@bot.command(name="summarize") # Tóm tắt phản hồi cuối cùng
async def get_summary(ctx): # Lấy tóm tắt phản hồi cuối cùng
    user_id = str(ctx.author.id) # Lấy ID người dùng
    last_response = get_last_response(user_id) # Lấy phản hồi cuối cùng
    if last_response: # Nếu có phản hồi cuối cùng
        summary = await summarize_long_response(last_response) # Tóm tắt phản hồi
        await ctx.send(f"Tóm tắt phản hồi cuối cùng:\n\n{summary}") # Gửi tóm tắt
    else: # Nếu không 
        await ctx.send("Không có phản hồi nào để tóm tắt.") # Thông báo không có phản hồi
        
        
def update_memory(user_id, user_message, bot_response): # Cập nhật bộ nhớ
    if user_id not in short_term_memory: # Nếu không có bộ nhớ  ngắn hạn
        short_term_memory[user_id] = deque(maxlen=5)  # Tạo bộ nhớ ngắn hạn
    short_term_memory[user_id].append(f"Người dùng: {user_message}") # Thêm tin nhắn người dùng
    short_term_memory[user_id].append(f"Trợ lý AI: {bot_response}") # Thêm phản hồi trợ lý AI

    context = "\n".join(short_term_memory[user_id]) # Kết hợp tất cả tin nhắn
    cursor.execute(
        "INSERT INTO long_term_memory (user_id, context) VALUES (?, ?)",
        (user_id, context),
    )
    conn.commit()





if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if token is None:
        print("Error: DISCORD_BOT_TOKEN is not set in the environment variables.")
    else:
        bot.run(token)

