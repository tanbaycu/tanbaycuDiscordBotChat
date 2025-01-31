# 🤖 Discord Bot Thông Minh với Tích Hợp AI

## 📚 Giới thiệu

Đây là một Discord bot đa chức năng, được phát triển bằng Python, tích hợp với API Gemini để cung cấp trải nghiệm tương tác thông minh và đa dạng. Bot này được thiết kế để nâng cao trải nghiệm người dùng trên các server Discord thông qua việc kết hợp khả năng trò chuyện AI, quản lý bộ nhớ thông minh, và nhiều tính năng giải trí hấp dẫn.

## 🌟 Tính năng chính

### 1. 💬 Trò chuyện AI Thông Minh
- Sử dụng API Gemini để tạo ra các phản hồi tự nhiên và thông minh
- Xử lý ngữ cảnh cuộc trò chuyện để đảm bảo tính nhất quán

### 2. 🧠 Quản lý Bộ Nhớ Tiên Tiến
- Bộ nhớ ngắn hạn: Lưu trữ ngữ cảnh gần đây trong RAM
- Bộ nhớ dài hạn: Sử dụng SQLite để lưu trữ lịch sử cuộc trò chuyện

### 3. 🛠️ Lệnh Quản Trị Mạnh Mẽ
- Các công cụ để quản lý server và thành viên một cách hiệu quả
- Kiểm soát quyền truy cập cho các lệnh nhạy cảm

### 4. 🎉 Lệnh Giải Trí Đa Dạng
- Tung đồng xu, lấy trích dẫn ngẫu nhiên, hiển thị hình ảnh ngẫu nhiên
- Cung cấp sự thật thú vị và câu chuyện cười

### 5. 🔒 Bảo Mật và Kiểm Soát
- Hệ thống phân quyền chi tiết cho các lệnh admin
- Khả năng tạm dừng và tiếp tục hoạt động của bot

### 6. 📊 Logging và Theo Dõi
- Ghi lại chi tiết các hoạt động và lỗi để dễ dàng debug

## 🚀 Cài đặt và Cấu Hình

### Yêu cầu hệ thống
- Python 3.8+
- pip (Python package manager)

### Bước 1: Clone Repository
```bash
git clone https://github.com/tanbaycu/tanbaycuDiscordBotChat.git
cd tanbaycuDiscordBotChat
```

### Bước 2: Cài đặt Dependencies
```bash
pip install -r requirements.txt
```

### Bước 3: Cấu hình Bot
1. Tạo file `.env` trong thư mục gốc
2. Thêm các thông tin sau vào file `.env`:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   GEMINI_API_KEY=your_gemini_api_key
   ```

### Bước 4: Khởi chạy Bot
```bash
python bot.py
```

## 📝 Cách Sử Dụng

Bot sử dụng prefix `/` cho tất cả các lệnh. Dưới đây là một số lệnh chính:

### Lệnh Chung
| Lệnh | Mô tả | Ví dụ |
|------|-------|-------|
| `/ping` | Kiểm tra độ trễ của bot | `/ping` |
| `/helpme` | Hiển thị danh sách lệnh | `/helpme` hoặc `/helpme ping` |
| `/invite` | Lấy liên kết mời bot | `/invite` |
| `/botinfo` | Hiển thị thông tin về bot | `/botinfo` |

### Lệnh Điều Khiển Bot
| Lệnh | Mô tả | Ví dụ |
|------|-------|-------|
| `/stop` | Dừng phản hồi tin nhắn thông thường | `/stop` |
| `/continue` | Tiếp tục phản hồi tin nhắn | `/continue` |
| `/clearmemory` | Xóa bộ nhớ ngắn hạn | `/clearmemory` |
| `/clearall` | Xóa toàn bộ bộ nhớ | `/clearall` |

### Lệnh Giải Trí
| Lệnh | Mô tả | Ví dụ |
|------|-------|-------|
| `/fact` | Lấy sự thật ngẫu nhiên | `/fact` |
| `/quote` | Lấy trích dẫn ngẫu nhiên | `/quote` |
| `/randomimage` | Lấy hình ảnh ngẫu nhiên | `/randomimage` |
| `/coinflip` | Tung đồng xu | `/coinflip` |

### Lệnh Quản Trị (Chỉ dành cho Admin)
| Lệnh | Mô tả | Ví dụ |
|------|-------|-------|
| `/kick` | Kick thành viên | `/kick @user Lý do` |
| `/ban` | Ban thành viên | `/ban @user Lý do` |
| `/warning` | Cảnh cáo thành viên | `/warning @user Lý do` |
| `/say` | Bot nói điều gì đó | `/say Xin chào mọi người!` |

## 🛠️ Kiến Trúc và Thiết Kế

### Cấu trúc Dự Án
```
discord-bot/
│
├── bot.py                 # File chính chứa mã nguồn của bot
├── bot_memory.db          # Cơ sở dữ liệu SQLite cho bộ nhớ dài hạn
├── bot.log                # File log ghi lại hoạt động của bot
├── requirements.txt       # Danh sách các dependency
└── .env                   # File chứa các biến môi trường
```

### Các Thành Phần Chính

1. **Xử lý Sự Kiện Discord**
   Bot sử dụng thư viện `discord.py` để xử lý các sự kiện Discord. Ví dụ:

   ```python
   @bot.event
   async def on_message(message):
       if message.author == bot.user:
           return

       if message.content.startswith(bot.command_prefix):
           await bot.process_commands(message)
       elif gemini_responses_active:
           # Xử lý tin nhắn thông thường với AI
   ```

2. **Tích Hợp AI với Gemini API**
   Bot sử dụng Gemini API để tạo ra các phản hồi thông minh:

   ```python
   async def generate_gemini_response(prompt, context=""):
       # Cấu hình và gọi API Gemini
       # Xử lý phản hồi và trả về kết quả
   ```

3. **Quản Lý Bộ Nhớ**
   Bot sử dụng cả bộ nhớ ngắn hạn (RAM) và dài hạn (SQLite):

   ```python
   def update_memory(user_id, user_message, bot_response):
       # Cập nhật bộ nhớ ngắn hạn
       # Lưu vào cơ sở dữ liệu SQLite
   ```

4. **Xử Lý Lệnh**
   Sử dụng decorator `@bot.command()` để định nghĩa các lệnh:

   ```python
   @bot.command(name="ping")
   async def ping(ctx):
       latency = round(bot.latency * 1000)
       await ctx.send(f"Pong! Độ trễ: {latency}ms")
   ```

5. **Logging**
   Sử dụng module `logging` của Python để ghi log:

   ```python
   logging.basicConfig(
       level=logging.INFO,
       format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
       handlers=[
           logging.FileHandler("bot.log", encoding="utf-8"),
           logging.StreamHandler(sys.stdout)
       ]
   )
   ```

## 🔧 Mở Rộng Chức Năng

Để thêm tính năng mới cho bot, bạn có thể:

1. Tạo lệnh mới bằng cách sử dụng decorator `@bot.command()`.
2. Thêm xử lý sự kiện mới bằng cách sử dụng decorator `@bot.event`.
3. Tích hợp với các API bên ngoài khác để mở rộng khả năng của bot.

Ví dụ, để thêm một lệnh mới:

```python
@bot.command(name="hello")
async def hello(ctx):
    await ctx.send(f"Xin chào, {ctx.author.mention}!")
```

## 🐛 Xử Lý Sự Cố

1. **Bot không phản hồi**
   - Kiểm tra kết nối internet
   - Đảm bảo token Discord và API key Gemini hợp lệ
   - Kiểm tra log để xem có lỗi nào không

2. **Lỗi khi gọi API Gemini**
   - Kiểm tra giới hạn API
   - Đảm bảo định dạng yêu cầu chính xác

3. **Vấn đề về quyền hạn**
   - Kiểm tra cấu hình quyền của bot trong server Discord
   - Đảm bảo bot có đủ quyền để thực hiện các hành động cần thiết

## 📘 FAQ

1. **Q: Bot có thể hoạt động trên nhiều server cùng lúc không?**
   A: Có, bot có thể hoạt động trên nhiều server Discord cùng một lúc.

2. **Q: Làm thế nào để thêm bot vào server của tôi?**
   A: Sử dụng lệnh `/invite` để lấy liên kết mời bot, sau đó sử dụng liên kết đó để thêm bot vào server của bạn.

3. **Q: Bot có thể sử dụng ngôn ngữ khác ngoài tiếng Việt không?**
   A: Hiện tại, bot được cấu hình chủ yếu cho tiếng Việt, nhưng có thể dễ dàng mở rộng để hỗ trợ đa ngôn ngữ.

## 🤝 Đóng Góp

Chúng tôi rất hoan nghênh mọi đóng góp! Nếu bạn muốn cải thiện bot:

1. Fork repository
2. Tạo branch mới (`git checkout -b feature/AmazingFeature`)
3. Commit các thay đổi (`git commit -m 'Add some AmazingFeature'`)
4. Push lên branch (`git push origin feature/AmazingFeature`)
5. Mở Pull Request


## 📞 Liên Hệ

Nếu bạn có bất kỳ câu hỏi hoặc góp ý nào, vui lòng liên hệ:

- Email: tanbaycu@gmail.com
- Discord: [Tham gia server hỗ trợ của chúng tôi](https://discord.gg/GknzmQmX)
- GitHub Issues: [Tạo issue mới](https://github.com/tanbaycu/tanbaycuDiscordBotChat/issues)

---

⭐️ Nếu bạn thấy dự án này hữu ích, đừng ngần ngại tặng cho nó một ngôi sao trên GitHub!
