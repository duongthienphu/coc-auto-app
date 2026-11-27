"""
Module Auto Rally (Tổng Tấn Công) - Sự kiện Sa Hải Mê Thành (Gold Rush)
Kế thừa 100% thuật toán nhận diện từ src code gốc (auto_rally.py)
Thay thế chuột vật lý bằng ADB Tap ngầm (Không chiếm chuột).
"""

import time
import threading
from typing import Optional, Tuple, Dict, List, Callable

import cv2
import numpy as np
import mss

import config
import assets
from core.viewport import get_game_viewport, screen_to_android
from core.vision import safe_grab
from core.adb_manager import ADBManager

# Quản lý trạng thái nội bộ của Rally
_rally_templates = assets.get_rally_templates()
_timer_template = assets.get_rally_timer_template()
_full_tiles_cooldown: Dict[Tuple[int, int], float] = {}
_recently_joined_tiles: Dict[Tuple[int, int], float] = {}
_chat_failed_y_cooldown: Dict[int, float] = {}
_chat_full_cards_cooldown: List[Tuple[np.ndarray, float]] = []
_last_clicked_tile: Optional[Tuple[int, int]] = None
_effective_vp: Optional[Tuple[int, int, int, int]] = None
_last_raw_vp: Optional[Tuple[int, int, int, int]] = None
_last_pillarbox_check: float = 0.0
_consecutive_reward_claims: int = 0


def reset_rally_state() -> None:
    """Xóa sạch bộ nhớ tạm và cooldown khi bắt đầu phiên chạy mới."""
    global _full_tiles_cooldown, _recently_joined_tiles, _chat_failed_y_cooldown, _chat_full_cards_cooldown, _last_clicked_tile, _consecutive_reward_claims
    _full_tiles_cooldown.clear()
    _recently_joined_tiles.clear()
    _chat_failed_y_cooldown.clear()
    _chat_full_cards_cooldown.clear()
    _last_clicked_tile = None
    _consecutive_reward_claims = 0


def _sleep(seconds: float, stop_event: threading.Event, jitter: bool = True) -> bool:
    """Nghỉ có thể ngắt ngay lập tức khi stop_event được set, kèm độ lệch ngẫu nhiên nhẹ chống game quét."""
    import random
    extra = random.uniform(0.01, 0.035) if jitter else 0.0
    deadline = time.time() + seconds + extra
    while time.time() < deadline:
        if stop_event.is_set():
            return True
        time.sleep(0.02)
    return False


def _adb_tap(adb: ADBManager, vp: Tuple[int, int, int, int], win_x: int, win_y: int, desc: str = "", log_cb: Optional[Callable[[str], None]] = None):
    """Chuyển đổi tọa độ Windows -> Android và chạm ngầm qua ADB."""
    if not adb or not adb.active_serial:
        return
    screen_sz = adb.screen_size or (720, 1280)
    ax, ay = screen_to_android(win_x, win_y, vp, screen_sz)
    if desc and log_cb:
        log_cb(f"-> {desc} (Android: {ax}, {ay})")
    adb.tap(ax, ay)


def _adb_swipe(
    adb: ADBManager,
    vp: Tuple[int, int, int, int],
    win_x1: int,
    win_y1: int,
    win_x2: int,
    win_y2: int,
    duration_ms: int = 280,
    desc: str = "",
    log_cb: Optional[Callable[[str], None]] = None,
):
    """Chuyển đổi tọa độ Windows -> Android và vuốt ngầm qua ADB."""
    if not adb or not adb.active_serial:
        return
    screen_sz = adb.screen_size or (720, 1280)
    ax1, ay1 = screen_to_android(win_x1, win_y1, vp, screen_sz)
    ax2, ay2 = screen_to_android(win_x2, win_y2, vp, screen_sz)
    if desc and log_cb:
        log_cb(f"-> {desc} (Android vuốt: ({ax1}, {ay1}) -> ({ax2}, {ay2}))")
    adb.swipe(ax1, ay1, ax2, ay2, duration_ms)


def _detect_pillarbox(sample_bgr: np.ndarray) -> Tuple[int, int]:
    """Phát hiện viền đen hai bên của màn hình mobile trên PC."""
    gray = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2GRAY)
    col_means = np.mean(gray, axis=0)
    non_black = np.where(col_means > 10.0)[0]
    if len(non_black) == 0:
        return 0, sample_bgr.shape[1]
    left_bound = int(non_black[0])
    right_bound = int(non_black[-1])
    real_w = max(10, right_bound - left_bound + 1)
    return left_bound, real_w


def _get_effective_vp(sct: mss.MSS, raw_vp: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    global _effective_vp, _last_raw_vp, _last_pillarbox_check
    now = time.time()
    if _effective_vp is not None and raw_vp == _last_raw_vp and (now - _last_pillarbox_check < 10.0):
        return _effective_vp

    gw_l, gw_t, gw_w, gw_h = raw_vp
    _last_raw_vp = raw_vp
    _last_pillarbox_check = now

    sample_y = int(gw_t + gw_h * 0.35)
    sample_h = max(10, int(gw_h * 0.30))
    sample = safe_grab(sct, {"left": gw_l, "top": sample_y, "width": gw_w, "height": sample_h})
    if sample is None:
        _effective_vp = raw_vp
        return raw_vp

    offset_x, real_w = _detect_pillarbox(sample)
    if offset_x > 0 or real_w < gw_w:
        _effective_vp = (gw_l + offset_x, gw_t, real_w, gw_h)
    else:
        _effective_vp = raw_vp
    return _effective_vp


def _is_tile_in_dict(tile: Tuple[int, int], target_dict: Dict[Tuple[int, int], float], threshold: Optional[int] = None) -> bool:
    if threshold is None:
        threshold = getattr(config, "RALLY_FULL_TILE_RADIUS", 30)
    tx, ty = tile
    now = time.time()
    return any(abs(tx - cx) < threshold and abs(ty - cy) < threshold for (cx, cy), exp in target_dict.items() if exp > now)


def _check_and_claim_reward(sct: mss.MSS, vp: Tuple[int, int, int, int], adb: ADBManager, stop_event: threading.Event, log_cb: Optional[Callable[[str], None]] = None) -> bool:
    global _consecutive_reward_claims
    if stop_event.is_set():
        return False

    # Cơ chế Failsafe: Tránh loop bấm nhận quà liên tiếp do nhận diện nhầm chi tiết màn hình
    if _consecutive_reward_claims >= 2:
        if log_cb:
            log_cb("Đã bấm nhận quà 2 lần liên tiếp -> Tự động chuyển tiếp để chống kẹt")
        _consecutive_reward_claims = 0
        return False

    gw_l, gw_t, gw_w, gw_h = vp
    x1 = int(gw_l + gw_w * config.RALLY_REWARD_BTN_REL_X_MIN)
    x2 = int(gw_l + gw_w * config.RALLY_REWARD_BTN_REL_X_MAX)
    y1 = int(gw_t + gw_h * config.RALLY_REWARD_BTN_REL_Y_MIN)
    y2 = int(gw_t + gw_h * config.RALLY_REWARD_BTN_REL_Y_MAX)

    crop = safe_grab(sct, {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1})
    if crop is None:
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    lower_green = np.array(getattr(config, "HSV_RALLY_REWARD_GREEN_LOWER", [40, 110, 110]), dtype=np.uint8)
    upper_green = np.array(getattr(config, "HSV_RALLY_REWARD_GREEN_UPPER", [80, 255, 255]), dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_green, upper_green)

    px_count = int(np.count_nonzero(mask))
    total_px = max(1, crop.shape[0] * crop.shape[1])
    green_ratio = float(px_count) / float(total_px)
    ratio_threshold = float(getattr(config, "RALLY_REWARD_GREEN_RATIO", 0.22))
    if green_ratio >= ratio_threshold:
        cx = int(gw_l + gw_w * config.RALLY_CLAIM_REWARD_X)
        cy = int(gw_t + gw_h * config.RALLY_CLAIM_REWARD_Y)
        _adb_tap(adb, vp, cx, cy, "Nhận quà Rally", log_cb)
        _consecutive_reward_claims += 1
        _sleep(config.RALLY_DELAY_AFTER_CLAIM_REWARD, stop_event)
        return True

    _consecutive_reward_claims = 0
    return False


def _handle_rally_detail_popup(
    sct: mss.MSS,
    vp: Tuple[int, int, int, int],
    adb: ADBManager,
    stop_event: threading.Event,
    log_cb: Optional[Callable[[str], None]] = None,
    allow_type_d_close_x: bool = True,
) -> Tuple[bool, bool]:
    global _last_clicked_tile, _full_tiles_cooldown, _recently_joined_tiles
    if stop_event.is_set():
        return False, False

    gw_l, gw_t, gw_w, gw_h = vp
    screen_crop = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
    if screen_crop is None:
        return False, False

    # Chặn tuyệt đối: Khi khung Chat đang mở, không bao giờ xử lý như Popup ô đất/Map
    if _is_chat_open(screen_crop):
        return False, False

    # 0. Type Alert: Hộp thoại thông báo hệ thống dạng Modal ("Xác Nhận")
    # Ví dụ: "Tổng Tấn Công chưa hoàn thành. Không thể tấn công ô mục tiêu."
    # Đặc điểm: Tiêu đề tím / nền hộp thoại sáng và Nút lớn màu xanh lá "Xác Nhận" ở giữa màn hình.
    btn_modal_crop = screen_crop[int(gw_h * 0.55):int(gw_h * 0.72), int(gw_w * 0.20):int(gw_w * 0.80)]
    hsv_modal = cv2.cvtColor(btn_modal_crop, cv2.COLOR_BGR2HSV)
    green_mask_m = cv2.inRange(hsv_modal, np.array([35, 100, 100]), np.array([85, 255, 255]))
    contours_m, _ = cv2.findContours(green_mask_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    found_confirm_btn = None
    min_confirm_h = max(18, int(gw_h * 0.022))
    for c in contours_m:
        cx, cy, bw, bh = cv2.boundingRect(c)
        if bw >= int(gw_w * 0.20) and bh >= min_confirm_h and (1.5 <= bw / bh <= 6.0):
            confirm_x = int(gw_l + gw_w * 0.20 + cx + bw // 2)
            confirm_y = int(gw_t + gw_h * 0.55 + cy + bh // 2)
            found_confirm_btn = (confirm_x, confirm_y)
            break

    if found_confirm_btn is not None:
        header_crop = screen_crop[int(gw_h * 0.30):int(gw_h * 0.42), int(gw_w * 0.10):int(gw_w * 0.90)]
        hsv_h = cv2.cvtColor(header_crop, cv2.COLOR_BGR2HSV)
        purple_px = np.count_nonzero(cv2.inRange(hsv_h, np.array([115, 50, 50]), np.array([165, 255, 255])))
        tot_header = max(1, header_crop.shape[0] * header_crop.shape[1])
        purple_ratio = float(purple_px) / float(tot_header)
        body_crop = screen_crop[int(gw_h * 0.40):int(gw_h * 0.58), int(gw_w * 0.15):int(gw_w * 0.85)]

        if purple_ratio > 0.05 or np.mean(body_crop) > 150:
            confirm_x, confirm_y = found_confirm_btn
            if log_cb:
                log_cb("Phát hiện thông báo 'Không thể tấn công ô mục tiêu' -> Bấm Xác Nhận")
            _adb_tap(adb, vp, confirm_x, confirm_y, "Bấm nút Xác Nhận", log_cb)
            _sleep(0.5, stop_event)

            if _last_clicked_tile is not None:
                cooldown = getattr(config, "RALLY_FULL_TILE_COOLDOWN", 30.0)
                _full_tiles_cooldown[_last_clicked_tile] = time.time() + cooldown
                if log_cb:
                    log_cb(f"Ô ({_last_clicked_tile[0]}, {_last_clicked_tile[1]}) không thể tấn công -> Khóa ô {int(cooldown)}s")
                _last_clicked_tile = None

            return True, False

    # 1. Type A: Popup danh sách Rally (hỗ trợ cả bản thấp Y=0.15..0.22 và bản cao Dune Y=0.02..0.08)
    # Lưu ý badge '18+ Chơi quá 180 phút' có thể đè chữ trắng lên phần trái header thấp -> kiểm tra thêm phần phải X=0.25..0.42 + viền tím thân bảng.
    tab_low = screen_crop[int(gw_h * 0.15):int(gw_h * 0.22), int(gw_w * 0.03):int(gw_w * 0.40)]
    tab_low_right = screen_crop[int(gw_h * 0.15):int(gw_h * 0.22), int(gw_w * 0.25):int(gw_w * 0.42)]
    top_dim_low = screen_crop[int(gw_h * 0.09):int(gw_h * 0.14), int(gw_w * 0.20):int(gw_w * 0.80)]
    left_margin_low = screen_crop[int(gw_h * 0.25):int(gw_h * 0.85), int(gw_w * 0.005):int(gw_w * 0.035)]
    left_margin_purple_ratio = 0.0
    if left_margin_low.size > 0:
        hsv_lm = cv2.cvtColor(left_margin_low, cv2.COLOR_BGR2HSV)
        lm_mask = cv2.inRange(hsv_lm, np.array([115, 35, 60], dtype=np.uint8), np.array([160, 220, 255], dtype=np.uint8))
        left_margin_purple_ratio = float(np.count_nonzero(lm_mask)) / float(max(1, left_margin_low.shape[0] * left_margin_low.shape[1]))

    is_low_sheet = (
        tab_low.size > 0
        and top_dim_low.size > 0
        and float(np.mean(top_dim_low)) < 70.0
        and (
            float(np.mean(tab_low)) < 75.0
            or (tab_low_right.size > 0 and float(np.mean(tab_low_right)) < 70.0 and left_margin_purple_ratio >= 0.55)
        )
    )

    tab_high = screen_crop[int(gw_h * 0.02):int(gw_h * 0.08), int(gw_w * 0.03):int(gw_w * 0.38)]
    top_dim_high = screen_crop[int(gw_h * 0.01):int(gw_h * 0.07), int(gw_w * 0.45):int(gw_w * 0.90)]
    purple_band_high = screen_crop[int(gw_h * 0.09):int(gw_h * 0.115), int(gw_w * 0.05):int(gw_w * 0.95)]
    sheet_body_high = screen_crop[int(gw_h * 0.60):int(gw_h * 0.88), int(gw_w * 0.30):int(gw_w * 0.90)]
    top_purple_ratio = 0.0
    body_purple_ratio = 0.0
    body_lavender_ratio = 1.0
    if purple_band_high.size > 0 and sheet_body_high.size > 0:
        hsv_pb = cv2.cvtColor(purple_band_high, cv2.COLOR_BGR2HSV)
        pm_high = cv2.inRange(hsv_pb, np.array([115, 35, 60], dtype=np.uint8), np.array([160, 220, 255], dtype=np.uint8))
        top_purple_ratio = float(np.count_nonzero(pm_high)) / float(max(1, purple_band_high.shape[0] * purple_band_high.shape[1]))

        hsv_sb = cv2.cvtColor(sheet_body_high, cv2.COLOR_BGR2HSV)
        bm_purp = cv2.inRange(hsv_sb, np.array([115, 35, 60], dtype=np.uint8), np.array([160, 220, 255], dtype=np.uint8))
        bm_lav = cv2.inRange(hsv_sb, np.array([110, 10, 160], dtype=np.uint8), np.array([170, 75, 255], dtype=np.uint8))
        body_pixels = float(max(1, sheet_body_high.shape[0] * sheet_body_high.shape[1]))
        body_purple_ratio = float(np.count_nonzero(bm_purp)) / body_pixels
        body_lavender_ratio = float(np.count_nonzero(bm_lav)) / body_pixels

    is_high_sheet = (
        not is_low_sheet
        and tab_high.size > 0
        and top_dim_high.size > 0
        and np.mean(tab_high) < 155.0
        and np.mean(top_dim_high) < 95.0
        and top_purple_ratio >= 0.25
        and body_purple_ratio >= 0.55
        and body_lavender_ratio < 0.15
    )
    is_multi_sheet = is_low_sheet or is_high_sheet

    if is_multi_sheet:
        bx1, bx2 = int(gw_w * 0.55), int(gw_w * 0.95)
        by1, by2 = int(gw_h * 0.15), int(gw_h * 0.88)
        min_btn_w = int(gw_w * 0.16)
        max_btn_w = int(gw_w * 0.42)
        min_btn_h = max(12, int(gw_h * 0.012))
        max_btn_h = max(45, int(gw_h * 0.080))
        min_btn_aspect = 1.8

        def _get_green_btns(img_crop: np.ndarray) -> List[Tuple[int, int]]:
            card_crop = img_crop[by1:by2, bx1:bx2]
            if card_crop.size == 0:
                return []
            hsv_cards = cv2.cvtColor(card_crop, cv2.COLOR_BGR2HSV)
            green_mask = cv2.inRange(hsv_cards, np.array([35, 100, 100]), np.array([85, 255, 255]))
            contours_g, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            btns = []
            for c in contours_g:
                cx, cy, bw, bh = cv2.boundingRect(c)
                if min_btn_w <= bw <= max_btn_w and min_btn_h <= bh <= max_btn_h and (float(bw) / float(max(1, bh))) >= min_btn_aspect:
                    btns.append((bx1 + cx + bw // 2, by1 + cy + bh // 2))
            btns.sort(key=lambda b: b[1])
            return btns

        green_btns = _get_green_btns(screen_crop)

        # Xác thực xem có thực sự là danh sách Rally không (phải có nút xanh hoặc nút xám của các thẻ Rally)
        card_crop_chk = screen_crop[by1:by2, bx1:bx2]
        hsv_chk = cv2.cvtColor(card_crop_chk, cv2.COLOR_BGR2HSV)
        grey_mask_chk = cv2.inRange(hsv_chk, np.array([0, 0, 70]), np.array([180, 60, 225]))
        contours_grey_chk, _ = cv2.findContours(grey_mask_chk, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        has_any_card = (
            len(green_btns) > 0
            or any(
                min_btn_w <= cv2.boundingRect(c)[2] <= max_btn_w
                and min_btn_h <= cv2.boundingRect(c)[3] <= max_btn_h
                and (float(cv2.boundingRect(c)[2]) / float(max(1, cv2.boundingRect(c)[3]))) >= min_btn_aspect
                for c in contours_grey_chk
            )
        )

        if not has_any_card:
            # Không phát hiện thẻ Rally nào ở cột bên phải -> Không phải bảng danh sách Rally
            pass
        else:
            joined_any = False
            cooldown_time = getattr(config, "RALLY_JOINED_COOLDOWN", 30.0)

            # Nhịp 1: Quét và tham gia các Rally ở trang đầu (Rally 1 -> 4)
            if green_btns:
                for idx, (btn_x, btn_y) in enumerate(green_btns):
                    if stop_event.is_set():
                        break
                    _adb_tap(adb, vp, gw_l + btn_x, gw_t + btn_y, f"Tham gia Rally {idx+1}/{len(green_btns)}", log_cb)
                    joined_any = True
                    _sleep(0.35, stop_event)

            # Vuốt cuộn trang lên để hiển thị các Rally thứ 5, 6... bị tràn bên dưới
            swipe_x = int(gw_l + gw_w * 0.50)
            swipe_y1 = int(gw_t + gw_h * 0.72)
            swipe_y2 = int(gw_t + gw_h * 0.28)
            _adb_swipe(adb, vp, swipe_x, swipe_y1, swipe_x, swipe_y2, 280, "Cuộn xem thêm Rally phía dưới", log_cb)
            _sleep(0.40, stop_event)

            # Nhịp 2: Quét lại sau khi cuộn để bấm các Rally mới lộ ra
            screen_crop2 = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
            if screen_crop2 is not None:
                green_btns_p2 = _get_green_btns(screen_crop2)
                if green_btns_p2:
                    for idx, (btn_x, btn_y) in enumerate(green_btns_p2):
                        if stop_event.is_set():
                            break
                        _adb_tap(adb, vp, gw_l + btn_x, gw_t + btn_y, f"Tham gia Rally bổ sung {idx+1}/{len(green_btns_p2)}", log_cb)
                        joined_any = True
                        _sleep(0.35, stop_event)

            if joined_any:
                if _last_clicked_tile is not None:
                    _recently_joined_tiles[_last_clicked_tile] = time.time() + cooldown_time
            else:
                if _last_clicked_tile is not None:
                    _full_tiles_cooldown[_last_clicked_tile] = time.time() + getattr(config, "RALLY_FULL_TILE_COOLDOWN", 30.0)
                    if log_cb:
                        log_cb(f"Ô ({_last_clicked_tile[0]}, {_last_clicked_tile[1]}) đã đầy -> Bỏ qua {int(getattr(config, 'RALLY_FULL_TILE_COOLDOWN', 30.0))}s")

            # Đóng bảng danh sách Type A: nếu có nút [X] trắng ở dải đáy (như bảng 總攻 toàn màn hình) thì bấm chính tâm [X],
            # ngược lại bấm vùng mờ phía trên (0.70, 0.04) cho bảng cao hoặc (0.50, 0.12) cho bảng thấp.
            xb_y1, xb_y2 = int(gw_h * 0.915), int(gw_h * 0.985)
            xb_x1, xb_x2 = int(gw_w * 0.42), int(gw_w * 0.58)
            xb_crop = screen_crop[xb_y1:xb_y2, xb_x1:xb_x2]
            closed_via_x = False
            if xb_crop.size > 0:
                xb_mask = (xb_crop[:, :, 0] > 175) & (xb_crop[:, :, 1] > 175) & (xb_crop[:, :, 2] > 175)
                xb_ratio = float(np.count_nonzero(xb_mask)) / float(max(1, xb_crop.shape[0] * xb_crop.shape[1]))
                if xb_ratio >= 0.04:
                    ys_x, xs_x = np.where(xb_mask)
                    cx_rel = int(xb_x1 + float(np.mean(xs_x)))
                    cy_rel = int(xb_y1 + float(np.mean(ys_x)))
                    _adb_tap(adb, vp, gw_l + cx_rel, gw_t + cy_rel, "Đóng bảng danh sách Rally (Nút X)", log_cb)
                    closed_via_x = True

            if not closed_via_x:
                safe_close_x = int(gw_l + gw_w * (0.70 if is_high_sheet else 0.50))
                safe_close_y = int(gw_t + gw_h * (0.04 if is_high_sheet else 0.12))
                _adb_tap(adb, vp, safe_close_x, safe_close_y, "Đóng Popup danh sách", log_cb)
            _sleep(0.35, stop_event)
            _last_clicked_tile = None
            return True, joined_any

    # 2. Kiểm tra xem có bảng Popup Card (Lane/Ảo Ảnh/Đất) đang mở che nửa dưới màn hình hay không:
    # Vùng nền thẻ popup (Y: 0.70..0.88, X: 0.15..0.85) có màu tím nhạt/xanh nhạt đặc trưng (S < 75, V > 120)
    # Trên Mapview, nền là cát vàng sa mạc (S > 100) và 4 nút đáy -> card_ratio cực thấp (< 0.10)
    roi_card_bg = screen_crop[int(gw_h * 0.70):int(gw_h * 0.88), int(gw_w * 0.15):int(gw_w * 0.85)]
    hsv_bg = cv2.cvtColor(roi_card_bg, cv2.COLOR_BGR2HSV)
    card_bg_mask = (hsv_bg[:, :, 1] < 75) & (hsv_bg[:, :, 2] > 120)
    card_ratio = float(np.count_nonzero(card_bg_mask)) / float(roi_card_bg.shape[0] * roi_card_bg.shape[1])

    roi_title = screen_crop[int(gw_h * 0.50):int(gw_h * 0.60), int(gw_w * 0.03):int(gw_w * 0.45)]
    gray_title = cv2.cvtColor(roi_title, cv2.COLOR_BGR2GRAY)
    tot_title = max(1, roi_title.shape[0] * roi_title.shape[1])
    title_ratio = float(np.count_nonzero((gray_title > 25) & (gray_title < 70))) / float(tot_title)
    title_header_found = bool(title_ratio > 0.05)

    is_popup_card_open = bool((card_ratio >= 0.40) or (title_header_found and card_ratio >= 0.25))

    # NẾU KHÔNG CÓ THẺ POPUP NÀO ĐANG MỞ -> ĐANG Ở VIEWMAP TOÀN CẢNH:
    # TUYỆT ĐỐI KHÔNG BẤM NÚT [X] VÌ ĐÂY LÀ NÚT THOÁT EVENT GOLDRUSH!
    if not is_popup_card_open:
        return False, False

    # 3. Type B & C & Single Rally & "Ảo Ảnh": Có nút Back thực sự ở góc trái
    back_x = int(gw_l + gw_w * config.RALLY_POPUP_BACK_X)
    back_y = int(gw_t + gw_h * config.RALLY_POPUP_BACK_Y)
    crop_back = screen_crop[int(gw_h * 0.88):int(gw_h * 0.98), int(gw_w * 0.04):int(gw_w * 0.16)]
    hsv_back = cv2.cvtColor(crop_back, cv2.COLOR_BGR2HSV)
    purple_px = int(np.count_nonzero(cv2.inRange(hsv_back, (110, 40, 40), (160, 255, 255))))
    white_px = int(np.count_nonzero(cv2.inRange(hsv_back, (0, 0, 180), (180, 50, 255))))
    tot_back = max(1, crop_back.shape[0] * crop_back.shape[1])
    purple_ratio = float(purple_px) / float(tot_back)
    white_ratio = float(white_px) / float(tot_back)
    has_back_btn = (purple_ratio >= 0.20 and white_ratio >= 0.08)

    if has_back_btn:
        bx1, bx2 = int(gw_w * 0.20), int(gw_w * 0.95)
        by1, by2 = int(gw_h * 0.88), int(gw_h * 0.98)
        btn_crop = screen_crop[by1:by2, bx1:bx2]
        hsv_btn = cv2.cvtColor(btn_crop, cv2.COLOR_BGR2HSV)
        tot_btn = max(1, btn_crop.shape[0] * btn_crop.shape[1])

        yellow_px = int(np.count_nonzero(cv2.inRange(hsv_btn, (15, 100, 100), (35, 255, 255))))
        green_px = int(np.count_nonzero(cv2.inRange(hsv_btn, (35, 100, 100), (85, 255, 255))))
        grey_px = int(np.count_nonzero(cv2.inRange(hsv_btn, (0, 0, 80), (180, 40, 210))))

        yellow_ratio = float(yellow_px) / float(tot_btn)
        green_ratio = float(green_px) / float(tot_btn)
        grey_ratio = float(grey_px) / float(tot_btn)

        if yellow_ratio >= 0.08:
            if _last_clicked_tile is not None:
                cooldown = getattr(config, "RALLY_FULL_TILE_COOLDOWN", 30.0)
                _full_tiles_cooldown[_last_clicked_tile] = time.time() + cooldown
                if log_cb:
                    log_cb(f"Ô ({_last_clicked_tile[0]}, {_last_clicked_tile[1]}) là ô đất thường -> Bỏ qua {int(cooldown)}s")
            _adb_tap(adb, vp, back_x, back_y, "Đóng bảng tấn công đất", log_cb)
            _sleep(config.RALLY_DELAY_AFTER_BACK_CLICK, stop_event)
            _last_clicked_tile = None
            return True, False

        if green_ratio >= 0.05:
            join_btn_x = int(gw_l + gw_w * 0.72)
            join_btn_y = int(gw_t + gw_h * 0.93)
            _adb_tap(adb, vp, join_btn_x, join_btn_y, "Tham gia Rally lẻ", log_cb)
            if _last_clicked_tile is not None:
                _recently_joined_tiles[_last_clicked_tile] = time.time() + getattr(config, "RALLY_JOINED_COOLDOWN", 30.0)
            _sleep(0.4, stop_event)
            _adb_tap(adb, vp, back_x, back_y, "Bấm Back về Map", log_cb)
            _sleep(config.RALLY_DELAY_AFTER_BACK_CLICK, stop_event)
            _last_clicked_tile = None
            return True, True

        if grey_ratio >= 0.04:
            if _last_clicked_tile is not None:
                cooldown = getattr(config, "RALLY_FULL_TILE_COOLDOWN", 30.0)
                _full_tiles_cooldown[_last_clicked_tile] = time.time() + cooldown
                if log_cb:
                    log_cb(f"Rally tại ({_last_clicked_tile[0]}, {_last_clicked_tile[1]}) đang chờ chấp thuận / đã đầy -> Bấm Back về Map")
            _adb_tap(adb, vp, back_x, back_y, "Bấm Back về Map", log_cb)
            _sleep(config.RALLY_DELAY_AFTER_BACK_CLICK, stop_event)
            _last_clicked_tile = None
            return True, False

        # Không có nút hành động nào khác -> Đây là bảng "Ảo Ảnh" / Bảng xếp hạng cứ điểm (có nút Back)
        if _last_clicked_tile is not None:
            cooldown = getattr(config, "RALLY_FULL_TILE_COOLDOWN", 30.0)
            _full_tiles_cooldown[_last_clicked_tile] = time.time() + cooldown
            if log_cb:
                log_cb(f"Ô ({_last_clicked_tile[0]}, {_last_clicked_tile[1]}) không có Rally -> Bỏ qua {int(cooldown)}s")
        _adb_tap(adb, vp, back_x, back_y, "Đóng bảng Ảo Ảnh/Cứ điểm về Map", log_cb)
        _sleep(config.RALLY_DELAY_AFTER_BACK_CLICK, stop_event)
        _last_clicked_tile = None
        return True, False

    # 4. Type D: Bảng mỏ vàng phe ta / ô đất đồng minh / Đồng Bằng (có nút [X] ở đáy, KHÔNG có nút Back tím)
    crop_close_x = screen_crop[int(gw_h * 0.925):int(gw_h * 0.980), int(gw_w * 0.44):int(gw_w * 0.56)]
    w_x_mask = (crop_close_x[:, :, 0] > 180) & (crop_close_x[:, :, 1] > 180) & (crop_close_x[:, :, 2] > 180)
    tot_x = max(1, crop_close_x.shape[0] * crop_close_x.shape[1])
    x_ratio = float(np.count_nonzero(w_x_mask)) / float(tot_x)

    # Ở chế độ Dune (allow_type_d_close_x=False), chỉ được đóng [X] khi KHỚP CHẶT cả 4 dấu hiệu bảng ô đất
    # che nút Chat: nền thẻ sáng S<45,V>180 >= 0.35 + thanh tiêu đề tối >= 0.35 + dải đáy hai bên [X] tối < 115 + nút [X] trắng đậm >= 0.22.
    can_close_strict_territory = False
    if not allow_type_d_close_x and x_ratio >= 0.22:
        lav180_ratio = float(np.count_nonzero((hsv_bg[:, :, 1] < 45) & (hsv_bg[:, :, 2] > 180))) / float(
            max(1, roi_card_bg.shape[0] * roi_card_bg.shape[1])
        )
        tb_low = cv2.cvtColor(screen_crop[int(gw_h * 0.64):int(gw_h * 0.72), int(gw_w * 0.05):int(gw_w * 0.35)], cv2.COLOR_BGR2GRAY)
        tb_high = cv2.cvtColor(screen_crop[int(gw_h * 0.50):int(gw_h * 0.60), int(gw_w * 0.05):int(gw_w * 0.35)], cv2.COLOR_BGR2GRAY)
        tb_dark_low = float(np.count_nonzero(tb_low < 80)) / float(max(1, tb_low.size))
        tb_dark_high = float(np.count_nonzero(tb_high < 80)) / float(max(1, tb_high.size))
        foot_l = screen_crop[int(gw_h * 0.925):int(gw_h * 0.980), int(gw_w * 0.10):int(gw_w * 0.38)]
        foot_r = screen_crop[int(gw_h * 0.925):int(gw_h * 0.980), int(gw_w * 0.62):int(gw_w * 0.90)]
        has_dark_x_footer = (
            foot_l.size > 0 and foot_r.size > 0
            and float(np.mean(foot_l)) < 115.0
            and float(np.mean(foot_r)) < 115.0
        )
        can_close_strict_territory = (lav180_ratio >= 0.35 and max(tb_dark_low, tb_dark_high) >= 0.35 and has_dark_x_footer)

    if (allow_type_d_close_x and x_ratio >= 0.04) or can_close_strict_territory:
        close_x = int(gw_l + gw_w * 0.50)
        close_y = int(gw_t + gw_h * 0.955)
        _adb_tap(adb, vp, close_x, close_y, "Đóng bảng ô đất / tài nguyên (Nút X)", log_cb)
        _sleep(config.RALLY_DELAY_AFTER_BACK_CLICK, stop_event)
        if _last_clicked_tile is not None:
            cooldown = getattr(config, "RALLY_FULL_TILE_COOLDOWN", 30.0)
            _full_tiles_cooldown[_last_clicked_tile] = time.time() + cooldown
            if log_cb:
                log_cb(f"Ô ({_last_clicked_tile[0]}, {_last_clicked_tile[1]}) là ô đất/tài nguyên -> Bỏ qua {int(cooldown)}s")
        _last_clicked_tile = None
        return True, False

    return False, False


def scan_and_join_map_rallies(
    sct: mss.MSS,
    vp: Tuple[int, int, int, int],
    adb: ADBManager,
    stop_event: threading.Event,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    global _last_clicked_tile, _full_tiles_cooldown, _recently_joined_tiles
    if stop_event.is_set():
        return None

    gw_l, gw_t, gw_w, gw_h = vp
    now = time.time()
    _full_tiles_cooldown = {p: exp for p, exp in _full_tiles_cooldown.items() if exp > now}
    _recently_joined_tiles = {p: exp for p, exp in _recently_joined_tiles.items() if exp > now}

    my1 = int(gw_t + gw_h * 0.12)
    my2 = int(gw_t + gw_h * 0.82)
    map_crop = safe_grab(sct, {"left": gw_l, "top": my1, "width": gw_w, "height": my2 - my1})
    if map_crop is None:
        return None

    map_gray = cv2.cvtColor(map_crop, cv2.COLOR_BGR2GRAY)
    candidates: List[Tuple[int, int, Tuple[int, int], str, float]] = []

    # Dynamic Adaptive Scaling: Tự động tính tỉ lệ scale tối ưu theo chiều cao cửa sổ game thật của người dùng
    ref_h = getattr(config, "RALLY_BASE_REFERENCE_HEIGHT", 1530.0)
    base_scale = gw_h / float(ref_h) if ref_h > 0 else 1.0
    configured_scales = getattr(config, "RALLY_SCALE_FACTORS", [1.00, 1.04, 0.96, 1.08, 0.92, 0.88, 0.84, 0.80])
    
    # Kết hợp dải scale thích ứng tự động và danh sách cấu hình tĩnh
    dynamic_scales = [base_scale * 1.00, base_scale * 1.04, base_scale * 0.96, base_scale * 1.08, base_scale * 0.92, base_scale * 0.85]
    scale_factors = sorted(list({round(s, 2) for s in (configured_scales + dynamic_scales) if 0.25 <= s <= 1.80}), reverse=True)
    cluster_radius = max(16, int(35 * (gw_h / ref_h)))

    # 1. ENGINE 1: Universal Timer Pill (Đa ngôn ngữ 100%: Bắt các số mm:ss trên nền đen viền vàng)
    timer_tpl = _timer_template if _timer_template is not None else assets.get_rally_timer_template()
    if timer_tpl is not None:
        t_th, t_tw = timer_tpl.shape[:2]
        timer_thresh = getattr(config, "RALLY_TIMER_MATCH_THRESHOLD", 0.52)
        avatar_offset_ratio = getattr(config, "RALLY_TIMER_AVATAR_OFFSET_Y", 0.85)

        for cur_sc in scale_factors:
            cur_tw = max(15, int(t_tw * cur_sc))
            cur_th = max(10, int(t_th * cur_sc))
            if cur_tw >= map_crop.shape[1] or cur_th >= map_crop.shape[0]:
                continue

            scaled_timer = cv2.resize(
                timer_tpl,
                (cur_tw, cur_th),
                interpolation=cv2.INTER_AREA if cur_sc < 1.0 else cv2.INTER_LINEAR,
            )
            res_timer = cv2.matchTemplate(map_crop, scaled_timer, cv2.TM_CCOEFF_NORMED)
            locs_timer = np.where(res_timer >= timer_thresh)
            for pt in zip(*locs_timer[::-1]):
                tx, ty = int(pt[0]), int(pt[1])
                score = float(res_timer[ty, tx])

                # Click rơi thẳng vào TÂM AVATAR (dịch ngược lên trên thanh timer)
                click_x = int(gw_l + tx + cur_tw // 2)
                click_y = int(my1 + ty - int(cur_th * avatar_offset_ratio))
                tile = (click_x, click_y)

                # Peak-Finding NMS: Luôn cập nhật điểm có score cực đại và tọa độ tâm chuẩn nhất trong bán kính cluster_radius
                matched_idx = -1
                for idx, c in enumerate(candidates):
                    if abs(c[0] - click_x) < cluster_radius and abs(c[1] - click_y) < cluster_radius:
                        matched_idx = idx
                        break
                if matched_idx == -1:
                    candidates.append((click_x, click_y, tile, f"TimerPill_{cur_sc:.2f}", score))
                elif score > candidates[matched_idx][4]:
                    candidates[matched_idx] = (click_x, click_y, tile, f"TimerPill_{cur_sc:.2f}", score)

    # 2. ENGINE 2: Banner Text Templates (Dự phòng bổ trợ cho Tiếng Việt)
    match_thresh = getattr(config, "RALLY_MATCH_THRESHOLD", 0.58)
    for tname, tpl in _rally_templates:
        is_clean = ("clean" in tname)
        tpl_th, tpl_tw = tpl.shape[:2]
        tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY) if is_clean else None

        for cur_sc in scale_factors:
            cur_tw = max(10, int(tpl_tw * cur_sc))
            cur_th = max(10, int(tpl_th * cur_sc))
            if cur_tw >= map_crop.shape[1] or cur_th >= map_crop.shape[0]:
                continue

            scaled_temp = cv2.resize(
                tpl_gray if is_clean else tpl,
                (cur_tw, cur_th),
                interpolation=cv2.INTER_AREA if cur_sc < 1.0 else cv2.INTER_LINEAR,
            )
            res = cv2.matchTemplate(map_gray if is_clean else map_crop, scaled_temp, cv2.TM_CCOEFF_NORMED)
            locs = np.where(res >= match_thresh)
            for pt in zip(*locs[::-1]):
                x, y = int(pt[0]), int(pt[1])
                score = float(res[y, x])
                click_x = int(gw_l + x + cur_tw // 2)
                click_y = int(my1 + y + int(cur_th * 1.85))
                tile = (click_x, click_y)

                # Peak-Finding NMS: Cập nhật nếu tìm thấy điểm khớp banner tốt hơn trong bán kính cluster_radius
                matched_idx = -1
                for idx, c in enumerate(candidates):
                    if abs(c[0] - click_x) < cluster_radius and abs(c[1] - click_y) < cluster_radius:
                        matched_idx = idx
                        break
                if matched_idx == -1:
                    candidates.append((click_x, click_y, tile, tname, score))
                elif score > candidates[matched_idx][4]:
                    candidates[matched_idx] = (click_x, click_y, tile, tname, score)

    # Sắp xếp ưu tiên độ tin cậy score giảm dần
    candidates.sort(key=lambda c: c[4], reverse=True)

    for click_x, click_y, tile, faction, score in candidates:
        if stop_event.is_set():
            return None

        if _is_tile_in_dict(tile, _recently_joined_tiles) or _is_tile_in_dict(tile, _full_tiles_cooldown):
            continue

        _last_clicked_tile = tile
        if log_cb:
            log_cb(f"Phát hiện Rally ({faction}) độ khớp {score:.2f} -> Bấm mở Avatar tại ({click_x}, {click_y})")

        _adb_tap(adb, vp, click_x, click_y, f"Mở Rally tại Avatar ({click_x}, {click_y})", log_cb)
        if _sleep(config.RALLY_DELAY_AFTER_MAP_CLICK, stop_event):
            return None

        is_pop, is_join = _handle_rally_detail_popup(sct, vp, adb, stop_event, log_cb)
        if not is_pop:
            # Thử kiểm tra lại lần 2 sau 0.35s phòng trường hợp giả lập lag mở popup chậm
            if not _sleep(0.35, stop_event):
                is_pop, is_join = _handle_rally_detail_popup(sct, vp, adb, stop_event, log_cb)

        if is_pop:
            return "JOINED" if is_join else "FULL"

        # Nếu đã bấm mở nhưng không có bất kỳ popup nào xuất hiện (ô không tương tác / lag / đã kết thúc / vô tình chọn ô đất):
        # BƯỚC TỰ GIẢI THOÁT: Chạm vùng bản đồ trống phía trên (50%, 20%) để chắc chắn hủy chọn ô đất và đóng mọi panel tồn đọng
        _adb_tap(adb, vp, int(gw_l + gw_w * 0.50), int(gw_t + gw_h * 0.20), "Bỏ chọn ô đất (Tự giải thoát)", log_cb)
        _sleep(0.3, stop_event)
        ensure_map_overview(sct, vp, adb, stop_event, None)

        cooldown = getattr(config, "RALLY_NON_INTERACTIVE_COOLDOWN", 20.0)
        _full_tiles_cooldown[tile] = time.time() + cooldown
        if log_cb:
            log_cb(f"Ô ({tile[0]}, {tile[1]}) không mở Popup -> Đã tự giải thoát & tạm bỏ qua {int(cooldown)}s")
        _last_clicked_tile = None
        return "CLICKED"

    return None


def ensure_map_overview(
    sct: mss.MSS,
    vp: Tuple[int, int, int, int],
    adb: ADBManager,
    stop_event: threading.Event,
    log_cb: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Đảm bảo bản đồ Sa Hải Mê Thành luôn ở chế độ toàn cảnh rộng nhất.
    Tự động chạm vào nút Kính Lúp dấu trừ ở góc dưới trái (Rel X: 0.084, Rel Y: 0.770)
    để mở toàn cảnh 4 phe nếu người dùng quên chưa bấm.
    """
    if stop_event.is_set():
        return False

    gw_l, gw_t, gw_w, gw_h = vp
    click_x = int(gw_l + gw_w * getattr(config, "RALLY_ZOOM_BTN_REL_X", 0.084))
    click_y = int(gw_t + gw_h * getattr(config, "RALLY_ZOOM_BTN_REL_Y", 0.770))

    zoom_tpl = assets.get_zoom_btn_template()
    has_zoom_minus = False
    if zoom_tpl is not None:
        roi_y1 = int(gw_t + gw_h * 0.68)
        roi_y2 = int(gw_t + gw_h * 0.85)
        roi_x1 = int(gw_l + gw_w * 0.01)
        roi_x2 = int(gw_l + gw_w * 0.25)
        roi_crop = safe_grab(sct, {"left": roi_x1, "top": roi_y1, "width": roi_x2 - roi_x1, "height": roi_y2 - roi_y1})
        if roi_crop is not None:
            best_val = 0.0
            best_pt = None
            for sc in [0.75, 0.85, 0.95, 1.0, 1.1, 1.25]:
                cur_w = int(zoom_tpl.shape[1] * sc)
                cur_h = int(zoom_tpl.shape[0] * sc)
                if cur_w >= roi_crop.shape[1] or cur_h >= roi_crop.shape[0]:
                    continue
                scaled = cv2.resize(zoom_tpl, (cur_w, cur_h))
                res = cv2.matchTemplate(roi_crop, scaled, cv2.TM_CCOEFF_NORMED)
                _, max_v, _, max_l = cv2.minMaxLoc(res)
                if max_v > best_val:
                    best_val = max_v
                    best_pt = (roi_x1 + max_l[0] + cur_w // 2, roi_y1 + max_l[1] + cur_h // 2)

            if best_val >= 0.55 and best_pt is not None:
                click_x, click_y = best_pt
                has_zoom_minus = True

    if has_zoom_minus:
        if log_cb:
            log_cb("Tự động kích hoạt toàn cảnh bản đồ (Kính lúp dấu trừ)...")
        _adb_tap(adb, vp, click_x, click_y, "Kính lúp toàn cảnh", log_cb)
        _sleep(0.5, stop_event)
        return True

    return False


def _has_chat_unread_badge(screen_crop: np.ndarray) -> bool:
    """Kiểm tra chấm/số thông báo đỏ trên icon Chat ở góc dưới phải Mapview."""
    if screen_crop is None or screen_crop.size == 0:
        return False
    gh, gw = screen_crop.shape[:2]
    x1 = max(0, min(gw - 1, int(gw * getattr(config, "RALLY_CHAT_BADGE_REL_X_MIN", 0.840))))
    x2 = max(x1 + 1, min(gw, int(gw * getattr(config, "RALLY_CHAT_BADGE_REL_X_MAX", 0.970))))
    y1 = max(0, min(gh - 1, int(gh * getattr(config, "RALLY_CHAT_BADGE_REL_Y_MIN", 0.710))))
    y2 = max(y1 + 1, min(gh, int(gh * getattr(config, "RALLY_CHAT_BADGE_REL_Y_MAX", 0.800))))

    roi = screen_crop[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower1 = np.array(getattr(config, "HSV_RED_LOWER1", [0, 90, 90]), dtype=np.uint8)
    upper1 = np.array(getattr(config, "HSV_RED_UPPER1", [12, 255, 255]), dtype=np.uint8)
    lower2 = np.array(getattr(config, "HSV_RED_LOWER2", [168, 90, 90]), dtype=np.uint8)
    upper2 = np.array(getattr(config, "HSV_RED_UPPER2", [180, 255, 255]), dtype=np.uint8)
    red_mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))
    red_ratio = float(np.count_nonzero(red_mask)) / float(max(1, roi.shape[0] * roi.shape[1]))
    min_ratio = float(getattr(config, "RALLY_CHAT_BADGE_MIN_RATIO", 0.008))
    return red_ratio >= min_ratio


def _is_chat_open(screen_crop: np.ndarray) -> bool:
    """
    Xác nhận giao diện Chat đang mở:
    1. Đáy màn hình (vùng nút hành động Popup) KHÔNG có nút xanh lớn (loại nhầm Popup Đơn Vị Tiêu Chuẩn).
    2. Góc phải thanh nhập liệu có nút Gửi màu xanh lá.
    3. Vùng thân Chat có nền sáng trắng/xám đặc trưng.
    """
    if screen_crop is None or screen_crop.size == 0:
        return False
    gh, gw = screen_crop.shape[:2]

    # 1. Loại trừ trường hợp đang mở Popup Chi Tiết Rally (có nút lớn ở Y: 0.90..0.97)
    by1 = max(0, min(gh - 1, int(gh * getattr(config, "RALLY_MAIN_BTN_REL_Y_MIN", 0.900))))
    by2 = max(by1 + 1, min(gh, int(gh * getattr(config, "RALLY_MAIN_BTN_REL_Y_MAX", 0.970))))
    bx1 = max(0, min(gw - 1, int(gw * getattr(config, "RALLY_MAIN_BTN_REL_X_MIN", 0.200))))
    bx2 = max(bx1 + 1, min(gw, int(gw * getattr(config, "RALLY_MAIN_BTN_REL_X_MAX", 0.950))))
    bottom_roi = screen_crop[by1:by2, bx1:bx2]
    if bottom_roi.size > 0:
        hsv_bot = cv2.cvtColor(bottom_roi, cv2.COLOR_BGR2HSV)
        lower_g = np.array(getattr(config, "HSV_RALLY_GREEN_LOWER", [35, 70, 70]), dtype=np.uint8)
        upper_g = np.array(getattr(config, "HSV_RALLY_GREEN_UPPER", [85, 255, 255]), dtype=np.uint8)
        bot_green_ratio = float(np.count_nonzero(cv2.inRange(hsv_bot, lower_g, upper_g))) / float(
            max(1, bottom_roi.shape[0] * bottom_roi.shape[1])
        )
        if bot_green_ratio >= 0.10:
            return False

    # 2. Kiểm tra nút Gửi tin nhắn màu xanh lá ở góc dưới phải khung Chat
    sx1 = max(0, min(gw - 1, int(gw * getattr(config, "RALLY_CHAT_SEND_REL_X_MIN", 0.720))))
    sx2 = max(sx1 + 1, min(gw, int(gw * getattr(config, "RALLY_CHAT_SEND_REL_X_MAX", 0.960))))
    sy1 = max(0, min(gh - 1, int(gh * getattr(config, "RALLY_CHAT_SEND_REL_Y_MIN", 0.820))))
    sy2 = max(sy1 + 1, min(gh, int(gh * getattr(config, "RALLY_CHAT_SEND_REL_Y_MAX", 0.920))))
    send_roi = screen_crop[sy1:sy2, sx1:sx2]
    if send_roi.size == 0:
        return False
    hsv_send = cv2.cvtColor(send_roi, cv2.COLOR_BGR2HSV)
    lower_g = np.array(getattr(config, "HSV_RALLY_GREEN_LOWER", [35, 70, 70]), dtype=np.uint8)
    upper_g = np.array(getattr(config, "HSV_RALLY_GREEN_UPPER", [85, 255, 255]), dtype=np.uint8)
    send_green_ratio = float(np.count_nonzero(cv2.inRange(hsv_send, lower_g, upper_g))) / float(
        max(1, send_roi.shape[0] * send_roi.shape[1])
    )
    if send_green_ratio < float(getattr(config, "RALLY_CHAT_SEND_GREEN_RATIO", 0.18)):
        return False

    # 3. Kiểm tra nền sáng đặc trưng của khung tin nhắn Chat
    cx1 = max(0, min(gw - 1, int(gw * getattr(config, "RALLY_CHAT_BODY_REL_X_MIN", 0.220))))
    cx2 = max(cx1 + 1, min(gw, int(gw * getattr(config, "RALLY_CHAT_BODY_REL_X_MAX", 0.900))))
    cy1 = max(0, min(gh - 1, int(gh * getattr(config, "RALLY_CHAT_BODY_REL_Y_MIN", 0.150))))
    cy2 = max(cy1 + 1, min(gh, int(gh * getattr(config, "RALLY_CHAT_BODY_REL_Y_MAX", 0.800))))
    body_roi = screen_crop[cy1:cy2, cx1:cx2]
    if body_roi.size == 0:
        return False
    hsv_body = cv2.cvtColor(body_roi, cv2.COLOR_BGR2HSV)
    light_mask = (hsv_body[:, :, 1] < 45) & (hsv_body[:, :, 2] > 190)
    light_ratio = float(np.count_nonzero(light_mask)) / float(max(1, body_roi.shape[0] * body_roi.shape[1]))
    return light_ratio >= float(getattr(config, "RALLY_CHAT_BODY_LIGHT_RATIO", 0.42))


def _detect_lien_minh_tab_target_y(screen_crop: np.ndarray) -> Optional[Tuple[float, float, float]]:
    """
    Xác định chính xác vị trí tab 'Liên Minh' bên trái khung Chat bằng nhận diện icon khiên vàng
    trên toàn sidebar (Y: 0.06..0.85, bao gồm cả slot 1..6 khi bị Thế Giới / tradecard / người lạ đẩy xuống).
    Trả về None nếu không khớp chắc chắn icon khiên vàng — TUYỆT ĐỐI không đoán mù slot 1/2.
    """
    if screen_crop is None or screen_crop.size == 0:
        return None

    shield_tpl = assets.get_lien_minh_tab_template()
    if shield_tpl is None or shield_tpl.size == 0:
        return None

    gh, gw = screen_crop.shape[:2]
    sb_y1 = max(0, int(gh * 0.06))
    sb_y2 = max(sb_y1 + 10, int(gh * float(getattr(config, "RALLY_CHAT_TAB_SCAN_Y_MAX", 0.850))))
    sb_x2 = max(10, int(gw * 0.21))
    sidebar = screen_crop[sb_y1:sb_y2, 0:sb_x2]
    if sidebar.size == 0:
        return None

    ref_h = float(getattr(config, "RALLY_CHAT_TAB_REF_HEIGHT", 715.0))
    base_sc = float(gh) / ref_h if ref_h > 0 else 1.0
    match_thresh = float(getattr(config, "RALLY_CHAT_TAB_MATCH_THRESHOLD", 0.68))
    gray_thresh = float(getattr(config, "RALLY_CHAT_TAB_GRAY_MATCH_THRESHOLD", 0.78))
    gold_min_ratio = float(getattr(config, "RALLY_CHAT_TAB_GOLD_MIN_RATIO", 0.15))
    lower_gold = np.array(getattr(config, "HSV_CHAT_CARD_GOLD_LOWER", [12, 80, 100]), dtype=np.uint8)
    upper_gold = np.array(getattr(config, "HSV_CHAT_CARD_GOLD_UPPER", [34, 255, 255]), dtype=np.uint8)

    sidebar_gray = cv2.cvtColor(sidebar, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(shield_tpl, cv2.COLOR_BGR2GRAY) if len(shield_tpl.shape) == 3 else shield_tpl

    best_score = 0.0
    best_cy_px = 0
    best_gray_score = 0.0
    best_gray_cy_px = 0
    tpl_h, tpl_w = shield_tpl.shape[:2]
    for mult in (0.85, 0.95, 1.00, 1.05, 1.15, 1.30):
        cur_sc = base_sc * mult
        cur_tw = max(8, int(tpl_w * cur_sc))
        cur_th = max(8, int(tpl_h * cur_sc))
        if cur_tw >= sidebar.shape[1] or cur_th >= sidebar.shape[0]:
            continue
        interp = cv2.INTER_AREA if cur_sc < 1.0 else cv2.INTER_LINEAR
        scaled = cv2.resize(shield_tpl, (cur_tw, cur_th), interpolation=interp)
        res = cv2.matchTemplate(sidebar, scaled, cv2.TM_CCOEFF_NORMED)
        _, max_v, _, max_l = cv2.minMaxLoc(res)
        if max_v > best_score:
            best_score = float(max_v)
            best_cy_px = int(sb_y1 + max_l[1] + cur_th // 2)

        scaled_gray = cv2.resize(tpl_gray, (cur_tw, cur_th), interpolation=interp)
        res_gray = cv2.matchTemplate(sidebar_gray, scaled_gray, cv2.TM_CCOEFF_NORMED)
        _, max_gv, _, max_gl = cv2.minMaxLoc(res_gray)
        if max_gv >= gray_thresh and float(max_gv) > best_gray_score:
            gx, gy = int(max_gl[0]), int(max_gl[1])
            patch = sidebar[gy:gy + cur_th, gx:gx + cur_tw]
            if patch.size > 0:
                hsv_p = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
                gold_ratio = float(np.count_nonzero(cv2.inRange(hsv_p, lower_gold, upper_gold))) / float(
                    max(1, patch.shape[0] * patch.shape[1])
                )
                if gold_ratio >= gold_min_ratio:
                    best_gray_score = float(max_gv)
                    best_gray_cy_px = int(sb_y1 + gy + cur_th // 2)

    if best_score >= match_thresh and best_cy_px > 0:
        cy_rel = float(best_cy_px) / float(max(1, gh))
        return max(0.05, cy_rel - 0.055), min(0.86, cy_rel + 0.055), cy_rel
    if best_gray_score >= gray_thresh and best_gray_cy_px > 0:
        cy_rel = float(best_gray_cy_px) / float(max(1, gh))
        return max(0.05, cy_rel - 0.055), min(0.86, cy_rel + 0.055), cy_rel
    return None


def _is_chat_tab_roi_purple(screen_crop: np.ndarray, y1_rel: float, y2_rel: float) -> bool:
    """Kiểm tra vùng tab trong [y1_rel..y2_rel] trên sidebar trái có đang sáng nền tím không."""
    if screen_crop is None or screen_crop.size == 0:
        return False
    gh, gw = screen_crop.shape[:2]
    x1 = max(0, min(gw - 1, int(gw * getattr(config, "RALLY_CHAT_TAB_REL_X_MIN", 0.030))))
    x2 = max(x1 + 1, min(gw, int(gw * getattr(config, "RALLY_CHAT_TAB_REL_X_MAX", 0.180))))
    y1 = max(0, min(gh - 1, int(gh * y1_rel)))
    y2 = max(y1 + 1, min(gh, int(gh * y2_rel)))
    tab_roi = screen_crop[y1:y2, x1:x2]
    if tab_roi.size == 0:
        return False
    hsv_tab = cv2.cvtColor(tab_roi, cv2.COLOR_BGR2HSV)
    purple_mask = cv2.inRange(hsv_tab, np.array([120, 80, 120], dtype=np.uint8), np.array([155, 255, 255], dtype=np.uint8))
    purple_ratio = float(np.count_nonzero(purple_mask)) / float(max(1, tab_roi.shape[0] * tab_roi.shape[1]))
    return purple_ratio >= float(getattr(config, "RALLY_CHAT_TAB_PURPLE_RATIO", 0.28))


def _is_lien_minh_tab_active(screen_crop: np.ndarray) -> bool:
    """Kiểm tra tab 'Liên Minh' (khớp icon khiên vàng thật) có đang được chọn (nền tím) không."""
    bounds = _detect_lien_minh_tab_target_y(screen_crop)
    if bounds is None:
        return False
    return _is_chat_tab_roi_purple(screen_crop, bounds[0], bounds[1])


def _has_purple_rally_card_above(screen_crop: np.ndarray, btn_y: int) -> bool:
    """
    Xác nhận phía trên nút xanh có phần thẻ Rally:
    - Tím ('Đơn Vị Tiêu Chuẩn'),
    - Hồng/đỏ san hô ('Tù Và Sa Mạc'),
    - Hoặc vàng/cam đất ('Cồn Cát' / 'Đồng Bằng' / 'Mỏ Vàng').
    Loại bỏ 100% bong bóng tin nhắn màu xanh lá do người dùng/đồng đội tự chat.
    """
    if screen_crop is None or screen_crop.size == 0:
        return False
    gh, gw = screen_crop.shape[:2]
    py1 = max(0, min(gh - 1, int(btn_y - gh * 0.11)))
    py2 = max(py1 + 1, min(gh, int(btn_y - gh * 0.02)))
    px1 = max(0, min(gw - 1, int(gw * 0.30)))
    px2 = max(px1 + 1, min(gw, int(gw * 0.58)))
    roi = screen_crop[py1:py2, px1:px2]
    if roi.size == 0:
        return False
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    purple_mask = cv2.inRange(hsv_roi, np.array([120, 60, 80], dtype=np.uint8), np.array([155, 255, 255], dtype=np.uint8))
    pink_red_high = cv2.inRange(hsv_roi, np.array([162, 70, 80], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
    pink_red_low = cv2.inRange(hsv_roi, np.array([0, 70, 80], dtype=np.uint8), np.array([10, 255, 255], dtype=np.uint8))
    lower_gold = np.array(getattr(config, "HSV_CHAT_CARD_GOLD_LOWER", [12, 80, 100]), dtype=np.uint8)
    upper_gold = np.array(getattr(config, "HSV_CHAT_CARD_GOLD_UPPER", [34, 255, 255]), dtype=np.uint8)
    gold_mask = cv2.inRange(hsv_roi, lower_gold, upper_gold)
    card_mask = purple_mask | pink_red_high | pink_red_low | gold_mask
    card_ratio = float(np.count_nonzero(card_mask)) / float(max(1, roi.shape[0] * roi.shape[1]))
    return card_ratio >= float(getattr(config, "RALLY_CHAT_CARD_PURPLE_MIN_RATIO", 0.12))


def _find_chat_join_buttons(screen_crop: np.ndarray) -> List[Tuple[int, int]]:
    """
    Tìm toàn bộ nút 'Tham gia' màu xanh lá nằm ngang trong vùng tin nhắn Chat.
    Lọc Hue >= 39 và bắt buộc có phần thẻ Rally tím phía trên để loại bỏ bong bóng chat xanh của người dùng.
    Sắp xếp từ DƯỚI lên TRÊN để ưu tiên Rally mới nhất trước.
    """
    if screen_crop is None or screen_crop.size == 0:
        return []
    gh, gw = screen_crop.shape[:2]
    x1 = max(0, min(gw - 1, int(gw * getattr(config, "CHAT_MESSAGES_REL_X_MIN", 0.280))))
    x2 = max(x1 + 1, min(gw, int(gw * getattr(config, "CHAT_MESSAGES_REL_X_MAX", 0.900))))
    y1 = max(0, min(gh - 1, int(gh * getattr(config, "CHAT_MESSAGES_REL_Y_MIN", 0.140))))
    y2 = max(y1 + 1, min(gh, int(gh * getattr(config, "CHAT_MESSAGES_REL_Y_MAX", 0.820))))

    msg_crop = screen_crop[y1:y2, x1:x2]
    if msg_crop.size == 0:
        return []

    hsv = cv2.cvtColor(msg_crop, cv2.COLOR_BGR2HSV)
    lower_g = np.array(getattr(config, "HSV_CHAT_JOIN_GREEN_LOWER", [39, 70, 70]), dtype=np.uint8)
    upper_g = np.array(getattr(config, "HSV_CHAT_JOIN_GREEN_UPPER", [85, 255, 255]), dtype=np.uint8)
    green_mask = cv2.inRange(hsv, lower_g, upper_g)
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_w = max(40, int(gw * getattr(config, "RALLY_CHAT_BTN_MIN_W_RATIO", 0.250)))
    min_h = max(12, int(gh * getattr(config, "RALLY_CHAT_BTN_MIN_H_RATIO", 0.015)))
    max_h = max(35, int(gh * getattr(config, "RALLY_CHAT_BTN_MAX_H_RATIO", 0.065)))
    min_aspect = float(getattr(config, "RALLY_CHAT_BTN_MIN_ASPECT", 2.5))

    buttons: List[Tuple[int, int]] = []
    for c in contours:
        cx, cy, bw, bh = cv2.boundingRect(c)
        if bw >= min_w and min_h <= bh <= max_h and (float(bw) / float(max(1, bh))) >= min_aspect:
            btn_cx = int(x1 + cx + bw // 2)
            btn_cy = int(y1 + cy + bh // 2)
            if _has_purple_rally_card_above(screen_crop, btn_cy):
                buttons.append((btn_cx, btn_cy))

    # Ưu tiên bấm Rally mới nhất ở dưới cùng trước
    buttons.sort(key=lambda pt: pt[1], reverse=True)
    return buttons


def _close_chat_if_open(
    sct: mss.MSS,
    vp: Tuple[int, int, int, int],
    adb: ADBManager,
    stop_event: threading.Event,
    log_cb: Optional[Callable[[str], None]] = None,
) -> bool:
    """Chỉ bấm khoảng trống phía trên đỉnh khung Chat (Y=0.030) để đóng Chat khi xác nhận Chat đang mở (tránh xa nút [X] ở đáy)."""
    if stop_event.is_set():
        return False
    gw_l, gw_t, gw_w, gw_h = vp
    frame = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
    if frame is None or not _is_chat_open(frame):
        return False
    close_x = int(gw_l + gw_w * getattr(config, "RALLY_CHAT_CLOSE_X", 0.500))
    close_y = int(gw_t + gw_h * getattr(config, "RALLY_CHAT_CLOSE_Y", 0.030))
    _adb_tap(adb, vp, close_x, close_y, "Đóng khung Chat (vùng trên đỉnh)", log_cb)
    _sleep(getattr(config, "RALLY_DELAY_AFTER_CHAT_CLOSE", 0.40), stop_event)
    return True


def _extract_chat_card_signature(screen_crop: np.ndarray, btn_y: int) -> Optional[np.ndarray]:
    """Trích xuất chữ ký ảnh xám 16x8 của phần nội dung thẻ Rally ngay phía trên nút Tham gia."""
    if screen_crop is None or screen_crop.size == 0:
        return None
    gh, gw = screen_crop.shape[:2]
    y2 = max(0, min(gh, int(btn_y - gh * 0.015)))
    y1 = max(0, y2 - max(12, int(gh * 0.075)))
    x1 = max(0, min(gw - 1, int(gw * getattr(config, "CHAT_MESSAGES_REL_X_MIN", 0.280))))
    x2 = max(x1 + 1, min(gw, int(gw * getattr(config, "CHAT_MESSAGES_REL_X_MAX", 0.900))))
    if (y2 - y1) < 10 or (x2 - x1) < 30:
        return None
    patch = screen_crop[y1:y2, x1:x2]
    if patch.size == 0:
        return None
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (16, 8), interpolation=cv2.INTER_AREA)


def _is_card_signature_cooled_down(card_sig: Optional[np.ndarray]) -> bool:
    """Kiểm tra thẻ Rally này vừa bị đánh dấu đã đầy/lỗi trong thời gian cooldown hay chưa."""
    global _chat_full_cards_cooldown
    now = time.time()
    _chat_full_cards_cooldown = [(sig, exp) for (sig, exp) in _chat_full_cards_cooldown if exp > now]
    if card_sig is None or card_sig.size == 0:
        return False
    max_diff = float(getattr(config, "RALLY_DUNE_CARD_DIFF_THRESHOLD", 12.0))
    sig_i16 = card_sig.astype(np.int16)
    for saved_sig, _ in _chat_full_cards_cooldown:
        diff = float(np.mean(np.abs(sig_i16 - saved_sig.astype(np.int16))))
        if diff < max_diff:
            return True
    return False


def _filter_chat_buttons_by_cooldown(
    buttons: List[Tuple[int, int]],
    screen_crop: np.ndarray,
    gw_h: int,
) -> List[Tuple[int, int]]:
    """
    Loại bỏ các thẻ Rally đã đầy (lag state 4/4 vẫn hiện nút xanh) theo chữ ký thẻ 45s
    và fallback khóa vị trí Y trong 8s để tránh bấm lặp liên tục.
    """
    global _chat_failed_y_cooldown
    now = time.time()
    _chat_failed_y_cooldown = {b: exp for b, exp in _chat_failed_y_cooldown.items() if exp > now}
    bucket_px = max(20, int(gw_h * 0.04))

    filtered: List[Tuple[int, int]] = []
    for bx, by in buttons:
        card_sig = _extract_chat_card_signature(screen_crop, by)
        if _is_card_signature_cooled_down(card_sig):
            continue
        if (by // bucket_px) in _chat_failed_y_cooldown:
            continue
        filtered.append((bx, by))
    return filtered


def _tap_chat_join_and_handle_popup(
    sct: mss.MSS,
    vp: Tuple[int, int, int, int],
    adb: ADBManager,
    btn_rel_xy: Tuple[int, int],
    stop_event: threading.Event,
    log_cb: Optional[Callable[[str], None]] = None,
    card_sig: Optional[np.ndarray] = None,
) -> str:
    """Bấm nút xanh 'Tham gia' trong Chat rồi xử lý bảng Rally Map hiện lên."""
    global _chat_failed_y_cooldown, _chat_full_cards_cooldown
    gw_l, gw_t, gw_w, gw_h = vp
    btn_x, btn_y = btn_rel_xy
    bucket_px = max(20, int(gw_h * 0.04))
    y_bucket = btn_y // bucket_px

    _adb_tap(adb, vp, gw_l + btn_x, gw_t + btn_y, "Bấm Tham gia Rally trong Chat", log_cb)
    if _sleep(getattr(config, "RALLY_DELAY_AFTER_CHAT_CLICK", 1.10), stop_event):
        return "STOPPED"

    is_pop, is_join = _handle_rally_detail_popup(sct, vp, adb, stop_event, log_cb, allow_type_d_close_x=False)
    if not is_pop and not _sleep(0.50, stop_event):
        is_pop, is_join = _handle_rally_detail_popup(sct, vp, adb, stop_event, log_cb, allow_type_d_close_x=False)

    if is_pop:
        if is_join:
            _chat_failed_y_cooldown.clear()
            return "JOINED"
        full_cd = float(getattr(config, "RALLY_DUNE_FULL_CARD_COOLDOWN", 45.0))
        if card_sig is not None and card_sig.size > 0:
            _chat_full_cards_cooldown.append((card_sig, time.time() + full_cd))
            if log_cb:
                log_cb(f"Dune Chat: Rally đã đầy/không thể vào -> Khóa thẻ này {int(full_cd)}s")
        else:
            _chat_failed_y_cooldown[y_bucket] = time.time() + float(getattr(config, "RALLY_DUNE_TAP_COOLDOWN", 8.0))
        return "POPUP_HANDLED"

    # Nếu không bật popup (rally vừa hết hạn hoặc lag) -> chỉ thoát popup nếu thật sự xuất hiện muộn;
    # KHÔNG tap mù vào (0.50, 0.20) trên Map để tránh tự bấm trúng ô đất sinh ra popup Đồng Bằng!
    after_frame = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
    if after_frame is not None and not _is_chat_open(after_frame):
        is_pop_late, is_join_late = _handle_rally_detail_popup(sct, vp, adb, stop_event, log_cb, allow_type_d_close_x=False)
        if is_pop_late:
            return "JOINED" if is_join_late else "POPUP_HANDLED"
    else:
        _chat_failed_y_cooldown[y_bucket] = time.time() + float(getattr(config, "RALLY_DUNE_TAP_COOLDOWN", 8.0))
    return "NO_POPUP"


def scan_and_join_chat_rallies(
    sct: mss.MSS,
    vp: Tuple[int, int, int, int],
    adb: ADBManager,
    stop_event: threading.Event,
    log_cb: Optional[Callable[[str], None]] = None,
    allow_scroll: bool = True,
) -> str:
    """
    Quét Rally trong tab 'Liên Minh' khi đang camp trong khung Chat:
    1. Kiểm tra đáy Chat (tin mới nhất).
    2. Nếu allow_scroll=True và chưa thấy nút xanh -> Vuốt lên xem tin cũ để bắt Rally bị trôi,
       nếu không thấy thì vuốt xuống lại đáy Chat.
    """
    if stop_event.is_set():
        return "STOPPED"

    gw_l, gw_t, gw_w, gw_h = vp
    frame = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
    if frame is None or not _is_chat_open(frame):
        return "NOT_CHAT"

    # Chỉ chuyển tab sang 'Liên Minh' khi nhận diện CHẮC CHẮN icon chiếc khiên vàng (tuyệt đối không bấm mù slot 1/2)
    tab_bounds = _detect_lien_minh_tab_target_y(frame)
    if tab_bounds is not None:
        y1_rel, y2_rel, target_tab_y = tab_bounds
        if not _is_chat_tab_roi_purple(frame, y1_rel, y2_rel):
            tab_x = int(gw_l + gw_w * getattr(config, "RALLY_CHAT_LIEN_MINH_TAB_X", 0.110))
            tab_y = int(gw_t + gw_h * target_tab_y)
            _adb_tap(adb, vp, tab_x, tab_y, "Chuyển sang tab Liên Minh", log_cb)
            if _sleep(float(getattr(config, "RALLY_DELAY_AFTER_TAB_CLICK", 0.75)), stop_event):
                return "STOPPED"
            frame = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
            if frame is None:
                return "NONE"

    # Nhịp 1: Quét đáy Chat (tin nhắn mới nhất)
    btns = _filter_chat_buttons_by_cooldown(_find_chat_join_buttons(frame), frame, gw_h)
    if btns:
        if log_cb:
            log_cb(f"Dune Chat: Phát hiện {len(btns)} nút Tham gia ở đáy -> Chọn Rally mới nhất")
        sig = _extract_chat_card_signature(frame, btns[0][1])
        return _tap_chat_join_and_handle_popup(sct, vp, adb, btns[0], stop_event, log_cb, card_sig=sig)

    if not allow_scroll:
        return "NONE"

    # Nhịp 2: Vuốt lên (kéo ngón tay từ trên xuống) để soi các Rally vừa bị trôi lên trên
    scroll_steps = int(getattr(config, "RALLY_CHAT_SCROLL_UP_STEPS", 2))
    swipe_x = int(gw_l + gw_w * getattr(config, "RALLY_CHAT_SWIPE_X", 0.560))
    top_y = int(gw_t + gw_h * getattr(config, "RALLY_CHAT_SWIPE_TOP_Y", 0.280))
    bot_y = int(gw_t + gw_h * getattr(config, "RALLY_CHAT_SWIPE_BOTTOM_Y", 0.720))
    swipe_ms = int(getattr(config, "RALLY_CHAT_SWIPE_DURATION_MS", 280))
    scroll_delay = float(getattr(config, "RALLY_DELAY_AFTER_CHAT_SCROLL", 0.45))

    swiped_up = 0
    for step in range(scroll_steps):
        if stop_event.is_set():
            return "STOPPED"
        _adb_swipe(adb, vp, swipe_x, top_y, swipe_x, bot_y, swipe_ms, f"Vuốt lên tìm Rally bị trôi ({step + 1}/{scroll_steps})", log_cb)
        swiped_up += 1
        if _sleep(scroll_delay, stop_event):
            return "STOPPED"

        up_frame = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
        if up_frame is None or not _is_chat_open(up_frame):
            break
        up_btns = _filter_chat_buttons_by_cooldown(_find_chat_join_buttons(up_frame), up_frame, gw_h)
        if up_btns:
            if log_cb:
                log_cb("Dune Chat: Tìm thấy Rally bị trôi -> Bấm Tham gia")
            up_sig = _extract_chat_card_signature(up_frame, up_btns[0][1])
            return _tap_chat_join_and_handle_popup(sct, vp, adb, up_btns[0], stop_event, log_cb, card_sig=up_sig)

    # Nhịp 3: Vuốt xuống lại đáy Chat (kéo ngón tay từ dưới lên) để luôn chốt lại ở tin mới nhất
    for step in range(swiped_up):
        if stop_event.is_set():
            return "STOPPED"
        _adb_swipe(adb, vp, swipe_x, bot_y, swipe_x, top_y, swipe_ms, f"Vuốt xuống lại đáy Chat ({step + 1}/{swiped_up})", log_cb)
        if _sleep(scroll_delay, stop_event):
            return "STOPPED"

    return "NONE"


def _run_dune_chat_loop(
    sct: mss.MSS,
    adb: ADBManager,
    get_vp_func: Callable[[], Optional[Tuple[int, int, int, int]]],
    stop_event: threading.Event,
    log_cb: Callable[[str], None],
) -> None:
    """
    Vòng lặp chuyên dụng cho Sa Hải Dune (Camp cố định 100% trong Chat Liên Minh):
    - Tuyệt đối KHÔNG gọi Type D (Nút X) và KHÔNG tự đóng Chat -> Không bao giờ bấm nhầm nút [X] thoát Mapview.
    - Quét đáy tức thì mỗi ~0.4s; định kỳ 8s vuốt lên/xuống bắt Rally bị trôi.
    - Khi thấy nút xanh -> Bấm Tham gia -> Xử lý Popup Rally trên Map -> Quay về Mapview check quà
      rồi lập tức mở lại Chat để camp tiếp.
    """
    drift_interval = float(getattr(config, "RALLY_DUNE_DRIFT_SCROLL_INTERVAL", 8.0))
    last_drift_scroll = time.time()

    while not stop_event.is_set():
        raw_vp = get_vp_func()
        if not raw_vp:
            log_cb("Chờ phát hiện cửa sổ game...")
            _sleep(1.0, stop_event)
            continue

        vp = _get_effective_vp(sct, raw_vp)
        gw_l, gw_t, gw_w, gw_h = vp

        screen_crop = safe_grab(sct, {"left": gw_l, "top": gw_t, "width": gw_w, "height": gw_h})
        if screen_crop is None:
            _sleep(0.4, stop_event)
            continue

        chat_open = _is_chat_open(screen_crop)

        if not chat_open:
            # 1. Chỉ xử lý Popup Rally / Alert hoặc nhận quà khi KHÔNG đứng trong Chat (tắt hẳn nút X Type D)
            is_pop, is_join = _handle_rally_detail_popup(
                sct, vp, adb, stop_event, log_cb, allow_type_d_close_x=False
            )
            if is_pop:
                if is_join:
                    log_cb("Dune: Đã xử lý popup & tham gia Rally -> Vào lại Chat camp tiếp")
                _sleep(0.45, stop_event)
                continue

            if _check_and_claim_reward(sct, vp, adb, stop_event, log_cb):
                continue

            # 2. Mở lại khung Chat Liên Minh để đứng camp cố định
            chat_x = int(gw_l + gw_w * getattr(config, "RALLY_CHAT_ICON_X", 0.927))
            chat_y = int(gw_t + gw_h * getattr(config, "RALLY_CHAT_ICON_Y", 0.770))
            _adb_tap(adb, vp, chat_x, chat_y, "Mở khung Chat Liên Minh để camp", log_cb)
            if _sleep(getattr(config, "RALLY_DELAY_AFTER_CHAT_OPEN", 0.95), stop_event):
                break
            last_drift_scroll = time.time()

        # 3. Quét nhanh đáy Chat; định kỳ mỗi drift_interval mới vuốt lên/xuống bắt Rally bị trôi
        now = time.time()
        do_scroll = (now - last_drift_scroll >= drift_interval)
        chat_res = scan_and_join_chat_rallies(sct, vp, adb, stop_event, log_cb, allow_scroll=do_scroll)
        if do_scroll:
            last_drift_scroll = time.time()

        if chat_res == "JOINED":
            log_cb("Dune: Đã tham gia Rally thành công! Quay lại Chat camp Rally tiếp theo...")
            last_drift_scroll = time.time()
            _sleep(0.5, stop_event)
            continue

        if chat_res in ("POPUP_HANDLED", "NO_POPUP"):
            _sleep(0.5, stop_event)
            continue

        _sleep(getattr(config, "RALLY_SCAN_INTERVAL", config.RALLY_DELAY_IDLE_SLEEP), stop_event)


def run_rally_loop(
    adb: ADBManager,
    get_vp_func: Callable[[], Optional[Tuple[int, int, int, int]]],
    stop_event: threading.Event,
    log_cb: Callable[[str], None],
    rally_mode: str = "map",
):
    """Vòng lặp chạy chính của Auto Rally (hỗ trợ 'map' Gold Rush thường và 'dune' Chat Liên Minh)."""
    reset_rally_state()
    sct = mss.mss()

    if rally_mode == "dune":
        log_cb("Khởi động Auto Rally - Sa Hải Dune (Quét Chat Liên Minh)...")
        _run_dune_chat_loop(sct, adb, get_vp_func, stop_event, log_cb)
        log_cb("Đã dừng Auto Rally (Dune).")
        return

    log_cb("Khởi động Auto Rally (Tổng Tấn Công - Map Thường)...")
    is_first_cycle = True
    last_zoom_check = 0.0

    while not stop_event.is_set():
        raw_vp = get_vp_func()
        if not raw_vp:
            log_cb("Chờ phát hiện cửa sổ game...")
            _sleep(1.0, stop_event)
            continue

        vp = _get_effective_vp(sct, raw_vp)

        # Tự động kích hoạt toàn cảnh bản đồ 4 phe khi bắt đầu hoặc định kỳ 60s
        now = time.time()
        if is_first_cycle or (now - last_zoom_check > 60.0):
            ensure_map_overview(sct, vp, adb, stop_event, log_cb if is_first_cycle else None)
            is_first_cycle = False
            last_zoom_check = now

        # 1. Kiểm tra nhận quà nếu trận trước vừa xong
        if _check_and_claim_reward(sct, vp, adb, stop_event, log_cb):
            # Sau khi nhận quà quay lại map, đảm bảo góc nhìn vẫn là toàn cảnh
            ensure_map_overview(sct, vp, adb, stop_event, None)
            continue

        # 2. Quét và bấm Rally trên Mapview
        result = scan_and_join_map_rallies(sct, vp, adb, stop_event, log_cb)
        if result == "JOINED":
            log_cb("Đã tham gia Rally thành công! Đang chờ lượt quét tiếp theo...")
            _sleep(1.5, stop_event)
            continue

        # 3. Kiểm tra popup tồn đọng (tránh kẹt nếu popup bị mở sẵn)
        is_pop, is_join = _handle_rally_detail_popup(sct, vp, adb, stop_event, log_cb)
        if is_pop:
            if is_join:
                log_cb("Đã xử lý popup tồn đọng & tham gia Rally!")
            # Sau khi đóng popup ô đất / cứ điểm, lập tức khôi phục toàn cảnh bản đồ nếu bị zoom
            ensure_map_overview(sct, vp, adb, stop_event, None)
            _sleep(0.5, stop_event)
            continue

        _sleep(getattr(config, "RALLY_SCAN_INTERVAL", config.RALLY_DELAY_IDLE_SLEEP), stop_event)

    log_cb("Đã dừng Auto Rally.")
