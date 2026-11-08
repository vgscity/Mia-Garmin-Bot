# Mia — bot Telegram đọc giấc ngủ và vận động từ đồng hồ Garmin, cho cả nhà

Mia là bot Telegram chạy trên Vercel (Python, không máy chủ riêng). Mỗi sáng Mia gửi tin giấc ngủ
đêm qua, mỗi tối gửi tổng kết ngày, kèm vài dòng nhận xét của AI và một gợi ý. Mỗi người trong nhà
tự chọn cách Mia gọi mình (ba, mẹ, ông, bà, anh, chị…), giờ nhận tin, và bật thêm tin tức buổi sáng,
thực đơn 10h theo hồ sơ của mình, theo dõi cân nặng. Cài đặt qua Mini App ngay trong Telegram.

Trang giới thiệu: https://alexvgs.tech/mia · Bot đang chạy: [@miamyworld_bot](https://t.me/miamyworld_bot)
(ai có Garmin cũng dùng được; muốn bản riêng thì tự dựng theo hướng dẫn dưới).

> Mia dùng dữ liệu từ đồng hồ Garmin qua tài khoản Garmin Connect của bạn, thông qua thư viện
> không chính thức [python-garminconnect](https://github.com/cyberjunky/python-garminconnect).
> Đây không phải sản phẩm của Garmin. Nhận xét của Mia là để tham khảo, không thay cho tư vấn y tế.

## Mia gửi gì

- **Sáng (giờ tự chọn 5h–10h):** điểm ngủ, tổng giờ ngủ, sâu / nông / REM, nhịp tim nghỉ, HRV, SpO2,
  nhịp thở, Body Battery hồi, nhiệt độ da; 3–5 dòng AI so với 7 đêm trước và một gợi ý cho hôm nay.
  Bật thêm thì kèm **tin thời sự** (RSS báo Việt), **tin xã hội · văn hoá · thể thao** (RSS) và/hoặc **tin công nghệ** (nguồn JSON tự cấu hình).
- **10h:** **thực đơn** theo hồ sơ tự khai (giới tính, chiều cao, cân mục tiêu, có ăn sáng không,
  món thích / kiêng), món Việt nấu ở nhà, có định lượng và calo, không lặp món 7 ngày; calo tự chỉnh
  theo tốc độ giảm cân thật.
- **Tối (18h–23h):** bước chân so với mục tiêu, calo, phút gắng sức, nhịp tim nghỉ / thấp / cao và giờ
  đạt đỉnh, Body Battery, stress, các buổi tập; AI nhận xét và gợi ý cho tối nay.
- **Hỏi gì đáp nấy:** nhắn tự do ("tuần này mình ngủ đủ không?", "hôm qua chạy bộ tim lên bao nhiêu?"), Mia tự
  đọc số Garmin, sổ cân, bữa ăn của chính người hỏi rồi trả lời (Claude + tool use). Tối đa `HOI_MOI_NGAY` câu/ngày.
- **Ảnh bữa ăn:** gửi ảnh, Mia đoán món, lượng, calo, đạm, cộng vào ngày và đưa vào tổng kết tối. Tối đa `ANH_MOI_NGAY` ảnh/ngày.
- **Tin sáng có thêm** (nếu đồng hồ / cân có dữ liệu): chỉ số tập luyện (sẵn sàng tập, VO2max, trạng thái), cân tự động từ
  cân Garmin Index, nhắc nhẹ khi số lệch nhiều ngày (ngủ dưới 6 tiếng, nhịp tim nghỉ tăng, HRV tụt), một dòng thời tiết
  (Open-Meteo) nếu bật. **Chủ nhật** kèm tổng kết tuần (`/tuan` để xem bất cứ lúc nào).
- **Nhắc vận động 17h** nếu bật và chưa được nửa mục tiêu bước.
- **Người nhà trông nhau:** người cho xem tạo mã trong Mini App, người xem nhập mã; mỗi sáng người xem nhận một dòng tóm tắt
  (ngủ ổn không, đồng hồ có đồng bộ không). Một bên bỏ là thôi.
- **Lệnh:** `/ngu` (`/ngu hqua`), `/tongket`, `/tuan`, `/thoisu`, `/xahoi`, `/tin`, `/thucdon`, `/can 60.5` (`/can`,
  `/can xoa`), `/caidat` (mở Mini App).

Riêng tư: mỗi người chỉ thấy số liệu của mình. Mật khẩu Garmin chỉ dùng một lần để lấy token đọc,
không lưu. Ai nhắn `/start` cũng dùng được ngay; chủ bot nhận một dòng báo kèm nút Chặn. Muốn duyệt
từng người thì đặt `DUYET_TAY=1`.

## Cấu trúc

```
api/webhook.py   webhook Telegram: lệnh, duyệt người nhà (callback_query)
api/cron.py      Vercel Cron mỗi giờ: ai đặt giờ sáng/tối trùng giờ VN hiện tại thì nhận; ?loai=trua = thực đơn 10h
api/mia.py       API cho Mini App (xác thực initData của Telegram bằng BOT_TOKEN)
api/app.py       trang Mini App (mini/mia.html)
api/man_phu.py   cổng JSON chỉ đọc cho dashboard riêng (tuỳ chọn, cần MAN_PHU_KEY)
bot/ngu.py       giấc ngủ        bot/tong_ket.py  tổng kết ngày     bot/ai.py       Claude API
bot/tin.py       bản tin sáng    bot/thuc_don.py  thực đơn          bot/can_nang.py sổ cân
bot/nguoi.py     người dùng (bảng mia_nguoi)       bot/kho.py       kho key-value (Turso)
bot/dau_truong.py  phần riêng của VGS (báo cáo game), tắt khi không đặt BAO_CAO_SECRET
```

Dữ liệu cất ở Turso (libSQL) qua HTTP: bảng `garmin_kv` (token Garmin, sổ cân, thực đơn gần đây,
bản tin đệm) và `mia_nguoi` (người dùng + hồ sơ). Chạy ở máy không có Turso thì token ghi ra
`.garmin_tokens.json`.

## Tự dựng

1. Tạo bot ở [@BotFather](https://t.me/BotFather), lấy `BOT_TOKEN`; lấy Telegram id của bạn làm `OWNER_ID`.
2. Tạo database Turso, lấy `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`. Lấy `ANTHROPIC_API_KEY` ở platform.claude.com (AI của Mia là Claude; model đổi bằng `CLAUDE_MODEL`).
3. Sao `.env.example` thành `.env`, điền biến. Hồ sơ của chủ bot (cách xưng hô, mục tiêu cân, món ăn…)
   nằm hết trong biến `CHU_*`, không có trong code.
4. Deploy lên Vercel: `vercel --prod` (cần `"framework": null` trong `vercel.json`, đã có). Đặt các biến
   môi trường trên Vercel giống `.env`.
5. Đặt webhook và nút Menu:
   ```bash
   curl "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" -d url=https://<project>.vercel.app/api/webhook \
     -d secret_token=$TELEGRAM_WEBHOOK_SECRET -d 'allowed_updates=["message","callback_query"]'
   curl "https://api.telegram.org/bot$BOT_TOKEN/setChatMenuButton" -H 'Content-Type: application/json' \
     -d '{"menu_button":{"type":"web_app","text":"Mia","web_app":{"url":"https://<project>.vercel.app/api/app"}}}'
   ```
6. Mở bot, nhắn `/start`, bấm "Mở Mia" để chọn xưng hô, giờ, bật các mục và đăng nhập Garmin
   (Garmin đòi mã xác minh thì nhập ngay trong Mini App).

Thử cron không gửi: `GET /api/cron?dry=1&gio=7`, `?dry=1&loai=trua` hoặc `?dry=1&tin=xa-hoi` với header
`Authorization: Bearer <CRON_SECRET>`.

## Lưu ý

- Garmin đôi khi đổi cách đăng nhập làm thư viện không chính thức hỏng; khi đó cron nhắn lỗi cho
  người dùng chứ không im lặng. Đăng nhập nhiều lần bị 429, đợi khoảng 1 tiếng.
- Request đăng nhập Garmin giữ kết nối tới 4 phút để chờ mã MFA (`maxDuration` 300 trong `vercel.json`).
- Bản tin soạn xong được đệm trong ngày theo cách xưng hô, nên nhiều người cùng gọi "anh" không tốn
  Claude soạn lại.

Giấy phép MIT. Tác giả: Alex Nguyen ([alexvgs.tech](https://alexvgs.tech)).
