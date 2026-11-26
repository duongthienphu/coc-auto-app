"""
Cấu hình toạ độ và thông số nhận diện cho Auto Câu Cá Đa Giả Lập.
Đo đạc chính xác theo tỉ lệ chuẩn màn hình dọc (Portrait 9:16) trên BlueStacks, LDPlayer, Nox, MuMu.
- Nút câu cá: Rel X = 0.406, Rel Y = 0.814 (Tâm nút câu)
- Nút Nhận Ngay: Rel X = 0.465, Rel Y = 0.870 (Nút nhận thưởng an toàn, tránh nút X)
- Thanh trượt minigame: X [0.200 -> 0.710], Y [0.660 -> 0.710]
"""

# ==============================================================================
# 1. TOẠ ĐỘ TỈ LỆ (THEO CHIỀU RỘNG & CAO CỦA CỬA SỔ GIẢ LẬP)
# ==============================================================================
# Tâm nút câu cá (Trên bờ / Dưới nước / Khi cá cắn) - Tọa độ mặc định / Fallback
BUTTON_REL_X: float = 0.500
BUTTON_REL_Y: float = 0.824

# Vùng quét tìm nút câu cá thích ứng (Smart Adaptive Button cho BlueStacks, LDPlayer, Nox, MuMu)
BUTTON_SCAN_REL_X_MIN: float = 0.350
BUTTON_SCAN_REL_X_MAX: float = 0.650
BUTTON_SCAN_REL_Y_MIN: float = 0.740
BUTTON_SCAN_REL_Y_MAX: float = 0.900

# Vùng thanh trượt mini-game kéo cá (Bao trọn 100% thanh trượt, đường ray và phao câu)
SLIDER_REL_X_MIN: float = 0.165
SLIDER_REL_X_MAX: float = 0.835
SLIDER_REL_Y_MIN: float = 0.605
SLIDER_REL_Y_MAX: float = 0.730

# Vị trí nút "Nhận Ngay" & vùng an toàn đóng popup
# (Nằm ngoài popup kỷ lục, trúng nút nhận thưởng cá thường, tuyệt đối không chạm nút X)
CLAIM_REL_X: float = 0.500
CLAIM_REL_Y: float = 0.870

# Vị trí tâm thẻ bài (Đóng popup "Kỷ Lục Đội Mới", "Cá Mới", "Kỷ Lục Cá Nhân")
CARD_REL_X: float = 0.500
CARD_REL_Y: float = 0.480

# Vị trí nút xác nhận giữa màn hình (Nút "Tiếp tục" / "Chia sẻ" / xác nhận thẻ bài đặc biệt)
CARD_CONFIRM_REL_Y: float = 0.720

# ==============================================================================
# 2. BÙ SAI SỐ VIỀN CỬA SỔ THEO TỪNG GIẢ LẬP
# ==============================================================================
# Thông số bù trừ viền: (title_bar_px, sidebar_left_px, sidebar_right_px)
# Tất cả các giả lập Android phổ biến trên Windows đều đặt thanh công cụ ở bên PHẢI (bên trái = 0px).
EMULATOR_VIEWPORT_OFFSETS: dict = {
    "bluestacks": (32, 0, 50),   # BlueStacks 5: thanh công cụ nằm bên phải ~50px
    "app player": (32, 0, 50),   # BlueStacks App Player
    "hd-player":  (32, 0, 50),   # BlueStacks 5 process
    "coc":        (32, 0, 50),   # Clash of Critters / coc multi-instance
    "critters":   (32, 0, 50),   # Clash of Critters
    "ldplayer":   (34, 0, 44),   # LDPlayer 9: thanh công cụ nằm bên phải ~44px
    "dnplayer":   (34, 0, 44),   # LDPlayer process
    "nox":        (32, 0, 46),   # NoxPlayer: thanh công cụ nằm bên phải ~46px
    "mumu":       (32, 0,  0),   # MuMu Player: không có sidebar cố định, thanh tab ~32px
    "nemu":       (32, 0,  0),   # MuMu Player process (NemuPlayer)
    "memu":       (32, 0, 44),   # MEmu: thanh công cụ nằm bên phải ~44px
}

# ==============================================================================
# 3. DẢI MÀU HSV & NGƯỠNG NHẬN DIỆN
# ==============================================================================
# Trạng thái 1: Nút xanh lá sẵn sàng thả cần (Trên bờ)
HSV_READY_GREEN_LOWER = [35, 70, 70]
HSV_READY_GREEN_UPPER = [85, 255, 255]
GREEN_PX_THRESHOLD: int = 400

# Trạng thái 2: Nút xám dưới nước (Cần đã thả, đang chờ cá đớp)
# Màu xám có độ bão hòa rất thấp (S < 50) và độ sáng vừa phải (80 <= V <= 220)
GREY_SATURATION_MAX: int = 50
GREY_VALUE_MIN: int = 80
GREY_VALUE_MAX: int = 220
GREY_PX_THRESHOLD: int = 600

# Trạng thái 3: Nút tím rực khi cá cắn câu thật sự & trong trận kéo cá
HSV_BITE_PURPLE_LOWER = [125, 70, 90]
HSV_BITE_PURPLE_UPPER = [175, 255, 255]
PURPLE_PX_THRESHOLD: int = 700

# Trạng thái 4: Ô vàng mục tiêu trên thanh trượt
HSV_YELLOW_LOWER = [15, 70, 90]
HSV_YELLOW_UPPER = [38, 255, 255]
YELLOW_MAX_WIDTH: int = 130  # Nếu rộng hơn 130px là chữ 'Hoàn hảo!' lóe sáng

# Phao đỏ di chuyển trên thanh trượt (quét 2 dải đỏ của HSV)
HSV_RED_LOWER1 = [0, 90, 90]
HSV_RED_UPPER1 = [12, 255, 255]
HSV_RED_LOWER2 = [168, 90, 90]
HSV_RED_UPPER2 = [180, 255, 255]

# ==============================================================================
# 4. GIỚI HẠN THỜI GIAN AN TOÀN
# ==============================================================================
# Timeout tối đa cho 1 ván kéo cá (MINIGAME_SLIDER).
# Nếu vượt quá giới hạn này mà vẫn chưa kết thúc -> tự động thu cần và nhận thưởng.
# Giá trị 45s là phao cứu sinh an toàn đủ cho cả cá kỷ lục kéo dài 30s trong game.
MINIGAME_MAX_DURATION: int = 45

# ==============================================================================
# 5. TOẠ ĐỘ & CẤU HÌNH CHO AUTO RALLY (SA HẢI MÊ THÀNH - GOLDRUSH)
# ==============================================================================
# A. Toạ độ tỉ lệ trong Popup Chi Tiết Rally ("Đơn Vị Tiêu Chuẩn / Xung Kích")
# Tâm nút lớn "Tham gia" ở đáy màn hình
RALLY_POPUP_JOIN_X: float = 0.580
RALLY_POPUP_JOIN_Y: float = 0.940

# Tâm nút Back nhỏ kế bên nút tham gia (góc dưới bên trái) để đóng popup về Mapview (tránh xa nút X ở giữa)
RALLY_POPUP_BACK_X: float = 0.085
RALLY_POPUP_BACK_Y: float = 0.940

# Vùng kiểm tra nút lớn ở đáy popup: (Rel X: 0.20 -> 0.95, Rel Y: 0.90 -> 0.97)
RALLY_MAIN_BTN_REL_X_MIN: float = 0.200
RALLY_MAIN_BTN_REL_X_MAX: float = 0.950
RALLY_MAIN_BTN_REL_Y_MIN: float = 0.900
RALLY_MAIN_BTN_REL_Y_MAX: float = 0.970

# B. Toạ độ tỉ lệ Popup Nhận Quà ("Tổng Tấn Công đã hoàn tất!")
# Tâm nút "Xác Nhận" màu xanh lá
RALLY_CLAIM_REWARD_X: float = 0.500
RALLY_CLAIM_REWARD_Y: float = 0.838

# Nút Kính Lúp dấu trừ (Thu nhỏ về bản đồ toàn cảnh Sa Hải Mê Thành)
RALLY_ZOOM_BTN_REL_X: float = 0.084
RALLY_ZOOM_BTN_REL_Y: float = 0.770

# Vùng kiểm tra nút "Xác Nhận" nhận quà
RALLY_REWARD_BTN_REL_X_MIN: float = 0.350
RALLY_REWARD_BTN_REL_X_MAX: float = 0.650
RALLY_REWARD_BTN_REL_Y_MIN: float = 0.800
RALLY_REWARD_BTN_REL_Y_MAX: float = 0.880

# Ngưỡng pixel & dải màu cho nút "Xác Nhận" nhận quà (Chống nhận diện nhầm viền thẻ/thanh máu)
HSV_RALLY_REWARD_GREEN_LOWER = [40, 110, 110]
HSV_RALLY_REWARD_GREEN_UPPER = [80, 255, 255]
RALLY_REWARD_PX_THRESHOLD: int = 2000
RALLY_REWARD_GREEN_RATIO: float = 0.22

# C. Toạ độ tỉ lệ Màn hình Chat & Chế độ Sa Hải Dune (Chat Liên Minh)
# Nút bong bóng Chat trên Mapview (góc dưới bên phải) và vùng kiểm tra badge đỏ
RALLY_CHAT_ICON_X: float = 0.927
RALLY_CHAT_ICON_Y: float = 0.770
RALLY_CHAT_BADGE_REL_X_MIN: float = 0.880
RALLY_CHAT_BADGE_REL_X_MAX: float = 0.990
RALLY_CHAT_BADGE_REL_Y_MIN: float = 0.710
RALLY_CHAT_BADGE_REL_Y_MAX: float = 0.800
RALLY_CHAT_BADGE_MIN_RATIO: float = 0.008

# Tab "Liên Minh" bên trái khung Chat (hỗ trợ cả trường hợp có tab Thế Giới ở trên cùng đẩy Liên Minh xuống slot 2)
RALLY_CHAT_LIEN_MINH_TAB_X: float = 0.110
RALLY_CHAT_LIEN_MINH_TAB_Y: float = 0.119
RALLY_CHAT_LIEN_MINH_TAB_Y_SLOT2: float = 0.245
RALLY_CHAT_TAB_REL_X_MIN: float = 0.030
RALLY_CHAT_TAB_REL_X_MAX: float = 0.180
RALLY_CHAT_TAB_REL_Y_MIN: float = 0.070
RALLY_CHAT_TAB_REL_Y_MAX: float = 0.180
RALLY_CHAT_TAB2_REL_Y_MIN: float = 0.190
RALLY_CHAT_TAB2_REL_Y_MAX: float = 0.300
RALLY_CHAT_TAB_PURPLE_RATIO: float = 0.28
RALLY_CHAT_WORLD_CYAN_RATIO: float = 0.05
RALLY_CHAT_WORLD_MAX_GOLD_RATIO: float = 0.03

# Tọa độ khoảng trống phía trên đỉnh khung Chat để đóng Chat an toàn (tránh xa nút [X] ở đáy Y=0.955)
RALLY_CHAT_CLOSE_X: float = 0.500
RALLY_CHAT_CLOSE_Y: float = 0.030

# Nhận diện khung Chat đang mở (Send button xanh + nền trắng tin nhắn + đáy tối)
RALLY_CHAT_SEND_REL_X_MIN: float = 0.720
RALLY_CHAT_SEND_REL_X_MAX: float = 0.960
RALLY_CHAT_SEND_REL_Y_MIN: float = 0.820
RALLY_CHAT_SEND_REL_Y_MAX: float = 0.920
RALLY_CHAT_SEND_GREEN_RATIO: float = 0.18

RALLY_CHAT_BODY_REL_X_MIN: float = 0.220
RALLY_CHAT_BODY_REL_X_MAX: float = 0.900
RALLY_CHAT_BODY_REL_Y_MIN: float = 0.150
RALLY_CHAT_BODY_REL_Y_MAX: float = 0.800
RALLY_CHAT_BODY_LIGHT_RATIO: float = 0.42

# Vùng quét các nút "Tham gia" màu xanh lá trong khung chat
CHAT_MESSAGES_REL_X_MIN: float = 0.280
CHAT_MESSAGES_REL_X_MAX: float = 0.900
CHAT_MESSAGES_REL_Y_MIN: float = 0.140
CHAT_MESSAGES_REL_Y_MAX: float = 0.820

# Lọc hình học nút "Tham gia" nằm ngang trong Chat (loại nút Gửi hình tròn & icon nhỏ)
RALLY_CHAT_BTN_MIN_W_RATIO: float = 0.250
RALLY_CHAT_BTN_MIN_H_RATIO: float = 0.015
RALLY_CHAT_BTN_MAX_H_RATIO: float = 0.085
RALLY_CHAT_BTN_MIN_ASPECT: float = 2.5

# Thông số vuốt chống trôi tin nhắn trong Chat (Vuốt lên xem tin cũ -> Vuốt xuống về đáy)
RALLY_CHAT_SWIPE_X: float = 0.560
RALLY_CHAT_SWIPE_TOP_Y: float = 0.280
RALLY_CHAT_SWIPE_BOTTOM_Y: float = 0.720
RALLY_CHAT_SWIPE_DURATION_MS: int = 280
RALLY_CHAT_SCROLL_UP_STEPS: int = 2

# Nút mũi tên tím cuộn xuống tin nhắn mới nhất trong Chat (góc dưới phải)
CHAT_SCROLL_BOTTOM_X: float = 0.915
CHAT_SCROLL_BOTTOM_Y: float = 0.772

# Chu kỳ & độ trễ riêng cho chế độ Dune (Camp cố định trong Chat Liên Minh)
RALLY_DELAY_AFTER_CHAT_OPEN: float = 0.95
RALLY_DELAY_AFTER_TAB_CLICK: float = 0.75
RALLY_DELAY_AFTER_CHAT_SCROLL: float = 0.75
RALLY_DELAY_AFTER_CHAT_CLOSE: float = 0.45
RALLY_DUNE_DRIFT_SCROLL_INTERVAL: float = 8.0
RALLY_DUNE_TAP_COOLDOWN: float = 8.0
RALLY_DUNE_FULL_CARD_COOLDOWN: float = 45.0
RALLY_DUNE_CARD_DIFF_THRESHOLD: float = 12.0

# D. Dải màu & ngưỡng nhận diện cho Rally
# Nút "Tham gia" màu xanh lá (Nút thật có > 12.000 px, ngưỡng 2500 loại bỏ 100% icon Mapview)
HSV_RALLY_GREEN_LOWER = [35, 70, 70]
HSV_RALLY_GREEN_UPPER = [85, 255, 255]
RALLY_GREEN_PX_THRESHOLD: int = 2500

# Nút xám "Chờ chấp thuận" / "Đã tham gia" / "Đã đầy" (Nút thật có > 11.000 px, ngưỡng 2500 loại bỏ 100% bóng mờ Mapview)
RALLY_GREY_SAT_MAX: int = 50
RALLY_GREY_VAL_MIN: int = 70
RALLY_GREY_VAL_MAX: int = 210
RALLY_GREY_PX_THRESHOLD: int = 2500

# Dòng chữ xanh lá "Đã tham gia" trên avatar ở Map
HSV_RALLY_JOINED_GREEN_LOWER = [35, 110, 110]
HSV_RALLY_JOINED_GREEN_UPPER = [85, 255, 255]
RALLY_JOINED_PX_THRESHOLD: int = 300

# Ngưỡng nhận diện Template Matching tiêu đề 'Tổng Tấn Công!' trên Mapview
# Ngưỡng nhận diện cờ Tổng Tấn Công (Rally thật: 0.70 - 0.89. Nhiễu địa hình/khói bụi: <= 0.54. Ngưỡng 0.58 lọc sạch 100% nhiễu)
RALLY_MATCH_THRESHOLD: float = 0.58
# Chiều cao chuẩn của viewport làm mốc tính tỉ lệ co dãn tự động (Adaptive Scale)
RALLY_BASE_REFERENCE_HEIGHT: float = 1530.0
# Dải tỷ lệ quét chuẩn quanh tỷ lệ 1.0 và mở rộng cho màn hình co nhỏ (720p, 1080p thu nhỏ trên multi-monitor)
RALLY_SCALE_FACTORS = [1.00, 1.04, 0.96, 1.08, 0.92, 0.88, 0.84, 0.80, 1.15]
# Bán kính kiểm tra trùng lặp ô đất (pixel) - Giảm xuống 30px để không khóa nhầm ô lân cận
RALLY_FULL_TILE_RADIUS: int = 30

# Cấu hình nhận diện Universal Timer Pill (Đa ngôn ngữ: mm:ss trên nền đen viền vàng, ngưỡng 0.55 lọc sạch nhiễu)
RALLY_TIMER_MATCH_THRESHOLD: float = 0.55
RALLY_TIMER_AVATAR_OFFSET_Y: float = 0.85  # Tỉ lệ dịch ngược từ đỉnh Timer lên tâm Avatar: click_y = timer_y - int(th * 0.85)

# Ngưỡng nhận diện bảng Tấn Công ô đất (Hình 2 - Không phải Rally, cần tự đóng về Mapview)
RALLY_TILE_ATTACK_YELLOW_PX: int = 1500  # Nút vàng "Tấn Công" góc dưới bên phải
RALLY_TILE_ATTACK_RED_PX: int = 1500     # Thanh máu phòng thủ đỏ "Quân phòng thủ"

# E. Cấu hình nhận diện Dải đen (Pillarbox Detection khi cửa sổ bị kéo dãn ngang)
PILLARBOX_BLACK_THRESHOLD: float = 12.0  # Ngưỡng độ sáng xác định dải đen hai bên sườn
PILLARBOX_MIN_MARGIN: int = 15           # Độ rộng lề tối thiểu (px) để kích hoạt loại trừ dải đen (tránh viền 1px)

# F. Cấu hình thời gian chờ (Delays - Đơn vị: Giây)
# Thời gian giữ phím chuột (chạm cảm ứng Android an toàn)
RALLY_DELAY_TAP_HOLD: float = 0.08

# Thời gian chờ sau khi bấm nút "Tham gia" trong popup (đợi server phản hồi đổi màu nút)
RALLY_DELAY_AFTER_JOIN_CLICK: float = 0.80

# Thời gian chờ sau khi bấm nút Back nhỏ để đóng popup (đợi hoạt ảnh hạ popup)
RALLY_DELAY_AFTER_BACK_CLICK: float = 0.80

# Thời gian chờ sau khi bấm "Xác Nhận" nhận quà (chờ hoạt ảnh "Phần Thưởng!" 2s kết thúc và Mapview hiện lại)
RALLY_DELAY_AFTER_CLAIM_REWARD: float = 2.20

# Thời gian chờ sau khi bấm "Tham gia" trong Chat (đợi game tải bản đồ và mở popup)
RALLY_DELAY_AFTER_CHAT_CLICK: float = 1.20

# Thời gian chờ sau khi click Avatar trên Map (đợi tải dữ liệu ô trên map)
RALLY_DELAY_AFTER_MAP_CLICK: float = 0.90

# Thời gian chờ sau khi bấm nút cuộn tin mới trong Chat
RALLY_DELAY_AFTER_SCROLL_CLICK: float = 0.40

# Thời gian nghỉ giữa các lần quét khi ở trạng thái chờ
RALLY_DELAY_IDLE_SLEEP: float = 0.40
RALLY_SCAN_INTERVAL: float = 0.40

# Thời gian khóa bỏ qua ô đã đầy trên Mapview (Cân bằng chuẩn 20s theo yêu cầu)
RALLY_FULL_TILE_COOLDOWN: float = 20.0
# Thời gian khóa bỏ qua ô không mở popup / ô đất trống (20s)
RALLY_NON_INTERACTIVE_COOLDOWN: float = 20.0

# Thời gian chờ kiểm tra lại ô đất vừa tham gia (20s)
RALLY_JOINED_COOLDOWN: float = 20.0

# Chế độ hoạt động: False = Focus 100% Tổng Mapview (Khuyên dùng); True = Quét cả Chat
RALLY_ENABLE_CHAT_SCAN: bool = False

# ==============================================================================
# 6. CẤU HÌNH CHO AUTO PHIÊU LƯU CỔ VẬT (RELIC ADVENTURE)
# ==============================================================================
# Toạ độ tỉ lệ chuẩn (Game Viewport 9:16)
# Nút "Bắt Đầu Phiêu Lưu!" tại sảnh chính (Hình 6)
PHIEULUU_START_REL_X: float = 0.570
PHIEULUU_START_REL_Y: float = 0.855

# Nút "Tiến Lên" trong mê cung (Hình 3, 4)
PHIEULUU_ADVANCE_REL_X: float = 0.505
PHIEULUU_ADVANCE_REL_Y: float = 0.820

# Nút "Chiến Đấu" khi gặp quái vật (Hình 2 - luôn chọn chiến đấu)
PHIEULUU_FIGHT_REL_X: float = 0.700
PHIEULUU_FIGHT_REL_Y: float = 0.795

# Nút "Chấp Nhận" khi kết toán / thất bại (Hình 7)
PHIEULUU_SETTLE_REL_X: float = 0.500
PHIEULUU_SETTLE_REL_Y: float = 0.925

# Nút "Mở Tất Cả" khi mở nhộng quà mốc (Hình 22 - nút vàng bên phải)
PHIEULUU_UNBOX_REL_X: float = 0.735
PHIEULUU_UNBOX_REL_Y: float = 0.880

# Nút "OK" khi nhận thưởng quà mốc hoàn tất (Hình 23 - nút xanh lá ở giữa)
PHIEULUU_OK_REL_X: float = 0.500
PHIEULUU_OK_REL_Y: float = 0.895

# Vị trí an toàn đóng popup bảo vật & giải phóng giao diện
# Lưu ý: Tuyệt đối KHÔNG chạm tại Y >= 0.88 ở giữa màn hình (X=0.50) vì đó là vị trí nút 'X' thoát trận của mê cung!
# Đặt lệch sang lề trái trên (X=0.15, Y=0.35) đảm bảo đóng popup an toàn 100% mà không bao giờ bấm trúng nút 'X'.
PHIEULUU_DISMISS_REL_X: float = 0.150
PHIEULUU_DISMISS_REL_Y: float = 0.350

# Vị trí an toàn lề trên màn hình (Dùng cho Watchdog giải phóng kẹt)
PHIEULUU_CENTER_REL_X: float = 0.150
PHIEULUU_CENTER_REL_Y: float = 0.350

# Thời gian chờ (Delays - giây)
# Chờ hoạt ảnh bước đi khi bấm Tiến Lên (~2s theo yêu cầu)
PHIEULUU_DELAY_AFTER_ADVANCE: float = 2.00

# Chờ 1s timing trước khi chạm đóng popup bảo vật (yêu cầu: "timing 1s để nó bảo là chạm vào màn hình để tiếp tục")
PHIEULUU_DELAY_POPUP_TIMING: float = 1.05

# Chờ sau khi đóng popup bảo vật
PHIEULUU_DELAY_AFTER_DISMISS: float = 0.60

# Chờ hoạt ảnh chiến đấu kết thúc
PHIEULUU_DELAY_AFTER_FIGHT: float = 1.80

# Chờ sau khi bấm Bắt Đầu Phiêu Lưu vào màn
PHIEULUU_DELAY_AFTER_START: float = 2.00

# Chờ sau khi bấm Chấp Nhận kết toán thoát ra ngoài để lặp lại từ đầu (~2s theo yêu cầu)
PHIEULUU_DELAY_AFTER_RESET: float = 2.00

# Chờ hoạt ảnh mở nhộng quà mốc (~3.5s theo yêu cầu người dùng)
PHIEULUU_DELAY_AFTER_UNBOX: float = 3.60

# Chờ sau khi bấm OK đóng bảng quà mốc
PHIEULUU_DELAY_AFTER_OK: float = 1.30

# Cơ chế Chống Treo (Watchdog / Anti-stuck)
PHIEULUU_WATCHDOG_UNKNOWN_TIMEOUT: float = 3.50    # Chạm an toàn nếu không rõ trạng thái sau 3.5s
PHIEULUU_WATCHDOG_ACTIVATE_TIMEOUT: float = 8.00   # Kích hoạt lại cửa sổ nếu kẹt sau 8s
PHIEULUU_SAME_STATE_MAX_RETRIES: int = 4           # Số lần bấm lại tối đa nếu trạng thái không đổi


