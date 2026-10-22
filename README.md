# Chạy database PostgreSQL

1. Đảm bảo dịch vụ PostgreSQL đang chạy. Tạo database `ai_news_aggregator` bằng pgAdmin, hoặc chạy trong PowerShell/Git Bash:

   ```sh
   psql -U postgres -h localhost -p 5432 -c "CREATE DATABASE ai_news_aggregator;"
   ```

   Nếu database đã tồn tại, bỏ qua bước này. `create_all()` chỉ tạo bảng, không tạo database.

2. Kiểm tra các biến PostgreSQL trong `app/.env` khớp với PostgreSQL trên máy:

   ```env
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=<mật khẩu PostgreSQL>
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=ai_news_aggregator
   ```

3. Từ thư mục `practice`, chạy:

   ```sh
   uv run python -m app.database.create_tables
   ```

   Lệnh kết nối vào database rồi tạo các bảng được khai báo trong `app/database/models.py`. Nếu thành công, terminal báo `Tables created successfully`.

# Chạy Gemini digest và curator

Đặt `GEMINI_API_KEY` trong `app/.env`. Để chạy bước curator riêng trên các digest gần đây:

```sh
uv run python -m app.services.process_curator
```

Để chạy pipeline hằng ngày:

```sh
uv run python main.py
```

Pipeline dùng Gemini để tạo digest, xếp hạng bài viết và viết lời giới thiệu email. `EmailAgent` OpenAI cũ vẫn được giữ lại nhưng pipeline không dùng nó. Việc gửi email vẫn cần `MY_EMAIL` và `APP_PASSWORD` trong `app/.env`.