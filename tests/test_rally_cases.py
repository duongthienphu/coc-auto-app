"""
Comprehensive Test Suite for All Known Rally & Popup Cases in COC AutoMaster.
Tests:
1. Modal Alert ("Không thể tấn công ô mục tiêu" -> Bấm nút Xác Nhận -> Cooldown 30s).
2. Type A Popup (Danh sách nhiều Rally -> Nhịp 1 bấm tham gia -> Vuốt cuộn trang -> Nhịp 2 bấm tham gia -> Đóng popup ở đỉnh).
3. Type B Single Rally - Nút xanh ("Tham gia" -> Bấm tham gia -> Bấm Back tím về map -> Cooldown joined).
4. Type B Single Rally - Nút xám ("Chờ chấp thuận" / "Đã đầy" -> Bấm Back tím -> KHÔNG bấm nút xám -> Cooldown 30s).
5. Type B Single Rally - Nút vàng (Bảng tấn công ô đất thường -> Bấm Back tím -> Cooldown 30s).
6. Type B "Ảo Ảnh" / Bảng xếp hạng không có nút hành động -> Bấm Back tím -> Cooldown 30s.
7. Type D Popup (Ô đất / Cồn cát / Mỏ tài nguyên có thanh máu & nút [X] ở đáy giữa -> Bấm nút [X] -> Cooldown 30s).
8. Miss-click Self-Escape (Bấm mở avatar nhưng không hiện popup -> Tap vùng trống 50%, 20% -> Bấm kính lúp -> Cooldown 20s).
9. Peak-Finding NMS (Nhiều điểm match lân cận -> Gom nhóm bán kính 35px, lấy điểm score cao nhất).
10. Claim Reward & Failsafe (Nhận diện nút xanh lá -> Tap nhận quà; Failsafe ngắt nhận quà khi bấm liên tiếp 2 lần).
11. Pillarbox Detection (Viền đen 2 bên màn hình mobile -> Tính đúng left_bound và real_w).
12. Ensure Map Overview (Icon kính lúp dấu trừ -> Kích hoạt toàn cảnh).
13. User 6 Screens Verification (Xác minh 100% chính xác trên 6 ảnh thực tế: Viewmap KHÔNG bấm X, các popup đóng đúng nút).
"""

import os
import sys
import glob
import threading
import unittest
from unittest.mock import patch
import cv2
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import assets
from modules import rally


class MockADB:
    """Mock ADBManager để ghi nhận toàn bộ tap và swipe trong quá trình kiểm thử."""
    def __init__(self, screen_size=(720, 1280)):
        self.active_serial = "emulator-5554"
        self.screen_size = screen_size
        self.taps = []
        self.swipes = []

    def tap(self, x: int, y: int):
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 280):
        self.swipes.append((x1, y1, x2, y2, duration_ms))

    def clear(self):
        self.taps.clear()
        self.swipes.clear()


def make_mock_grab(full_frame: np.ndarray):
    """Mô phỏng chính xác hành vi của mss.grab / safe_grab khi cắt theo ROI monitor."""
    def _grab(sct, mon):
        if mon is None:
            return full_frame.copy()
        l = max(0, mon.get("left", 0))
        t = max(0, mon.get("top", 0))
        w = mon.get("width", full_frame.shape[1] - l)
        h = mon.get("height", full_frame.shape[0] - t)
        crop = full_frame[t:t+h, l:l+w]
        return crop.copy() if crop.size > 0 else None
    return _grab


class TestRallyCases(unittest.TestCase):

    def setUp(self):
        rally.reset_rally_state()
        self.gw_w = 720
        self.gw_h = 1280
        self.vp = (0, 0, self.gw_w, self.gw_h)
        self.mock_adb = MockADB(screen_size=(self.gw_w, self.gw_h))
        self.stop_event = threading.Event()
        self.sleep_patcher = patch("modules.rally._sleep", return_value=False)
        self.sleep_patcher.start()

    def tearDown(self):
        self.sleep_patcher.stop()

    def _create_blank_frame(self, bg_bgr=(50, 150, 200)):
        """Mặc định nền vàng cát sa mạc (Mapview)."""
        frame = np.zeros((self.gw_h, self.gw_w, 3), dtype=np.uint8)
        frame[:] = bg_bgr
        return frame

    def _draw_popup_card(self, frame):
        """Vẽ thẻ popup màu tím nhạt/lavender che nửa dưới màn hình (Y: 0.52 -> 0.98)."""
        py1, py2 = int(self.gw_h * 0.52), int(self.gw_h * 0.98)
        frame[py1:py2, :] = (225, 215, 230)
        # Tiêu đề slate đen ở Y: 0.52 -> 0.58
        ty1, ty2 = int(self.gw_h * 0.53), int(self.gw_h * 0.57)
        tx1, tx2 = int(self.gw_w * 0.05), int(self.gw_w * 0.40)
        frame[ty1:ty2, tx1:tx2] = (50, 40, 45)

    def _draw_purple_back_btn(self, frame):
        """Vẽ nút Back tím ở góc dưới trái (Rel X: ~0.08, Rel Y: ~0.935)."""
        y1, y2 = int(self.gw_h * 0.90), int(self.gw_h * 0.96)
        x1, x2 = int(self.gw_w * 0.05), int(self.gw_w * 0.15)
        # Nền tím (HSV: H=135, S=200, V=140)
        frame[y1:y2, x1:x2] = (140, 20, 140)
        # Mũi tên trắng bên trong
        frame[y1+8:y2-8, x1+10:x2-10] = (255, 255, 255)

    # -------------------------------------------------------------
    # CASE 1: Modal Alert ("Không thể tấn công ô mục tiêu")
    # -------------------------------------------------------------
    def test_case_01_modal_alert_confirm(self):
        """Hộp thoại Alert: Header tím/sáng + Nút Xác Nhận xanh ở giữa -> Bấm nút & set cooldown 30s."""
        frame = self._create_blank_frame(bg_bgr=(30, 30, 30))
        hy1, hy2 = int(self.gw_h * 0.30), int(self.gw_h * 0.42)
        hx1, hx2 = int(self.gw_w * 0.10), int(self.gw_w * 0.90)
        frame[hy1:hy2, hx1:hx2] = (160, 40, 140)

        by1, by2 = int(self.gw_h * 0.40), int(self.gw_h * 0.58)
        bx1, bx2 = int(self.gw_w * 0.15), int(self.gw_w * 0.85)
        frame[by1:by2, bx1:bx2] = (220, 220, 220)

        ny1, ny2 = int(self.gw_h * 0.60), int(self.gw_h * 0.67)
        nx1, nx2 = int(self.gw_w * 0.35), int(self.gw_w * 0.65)
        frame[ny1:ny2, nx1:nx2] = (30, 200, 30)

        rally._last_clicked_tile = (250, 400)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event
            )

        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertGreaterEqual(len(self.mock_adb.taps), 1)

        tap_x, tap_y = self.mock_adb.taps[0]
        self.assertTrue(nx1 <= tap_x <= nx2)
        self.assertTrue(ny1 <= tap_y <= ny2)
        self.assertTrue(rally._is_tile_in_dict((250, 400), rally._full_tiles_cooldown))

    # -------------------------------------------------------------
    # CASE 2: Type A Popup (Danh sách nhiều Rally)
    # -------------------------------------------------------------
    def test_case_02_type_a_multi_rally_list_with_swipe(self):
        """Danh sách nhiều Rally: bấm nút xanh nhịp 1, vuốt cuộn trang, bấm nhịp 2, bấm đóng trên đỉnh."""
        frame1 = self._create_blank_frame(bg_bgr=(20, 20, 20))
        frame1[int(self.gw_h * 0.15):int(self.gw_h * 0.22), int(self.gw_w * 0.03):int(self.gw_w * 0.40)] = (50, 50, 50)
        frame1[int(self.gw_h * 0.09):int(self.gw_h * 0.14), int(self.gw_w * 0.20):int(self.gw_w * 0.80)] = (40, 40, 40)

        btn_w, btn_h = 130, 35
        frame1[400:400+btn_h, 450:450+btn_w] = (30, 200, 30)
        frame1[550:550+btn_h, 450:450+btn_w] = (30, 200, 30)

        frame2 = frame1.copy()
        frame2[700:700+btn_h, 450:450+btn_w] = (30, 200, 30)

        frames = [frame1, frame2]
        rally._last_clicked_tile = (100, 200)

        def mock_grab_sequence(sct, mon):
            curr_frame = frames[0] if len(self.mock_adb.swipes) == 0 else frames[1]
            return make_mock_grab(curr_frame)(sct, mon)

        with patch("modules.rally.safe_grab", side_effect=mock_grab_sequence):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event
            )

        self.assertTrue(is_pop)
        self.assertTrue(is_join)
        self.assertGreaterEqual(len(self.mock_adb.swipes), 1)
        self.assertGreaterEqual(len(self.mock_adb.taps), 4)

        last_tap = self.mock_adb.taps[-1]
        self.assertAlmostEqual(last_tap[0] / self.gw_w, 0.50, delta=0.05)
        self.assertAlmostEqual(last_tap[1] / self.gw_h, 0.12, delta=0.05)
        self.assertTrue(rally._is_tile_in_dict((100, 200), rally._recently_joined_tiles))

    # -------------------------------------------------------------
    # CASE 3: Type B Single Rally - Nút xanh (Tham gia)
    # -------------------------------------------------------------
    def test_case_03_type_b_single_rally_green(self):
        """Single Rally nút xanh: Bấm tham gia lẻ -> Sau đó bấm nút Back tím về Map."""
        frame = self._create_blank_frame()
        self._draw_popup_card(frame)
        self._draw_purple_back_btn(frame)

        frame[int(self.gw_h * 0.90):int(self.gw_h * 0.96), int(self.gw_w * 0.60):int(self.gw_w * 0.85)] = (30, 200, 30)

        rally._last_clicked_tile = (300, 500)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event
            )

        self.assertTrue(is_pop)
        self.assertTrue(is_join)
        self.assertEqual(len(self.mock_adb.taps), 2)

        tap1 = self.mock_adb.taps[0]
        self.assertAlmostEqual(tap1[0] / self.gw_w, 0.72, delta=0.08)
        self.assertAlmostEqual(tap1[1] / self.gw_h, 0.93, delta=0.08)

        tap2 = self.mock_adb.taps[1]
        self.assertAlmostEqual(tap2[0] / self.gw_w, config.RALLY_POPUP_BACK_X, delta=0.05)
        self.assertAlmostEqual(tap2[1] / self.gw_h, config.RALLY_POPUP_BACK_Y, delta=0.05)

        self.assertTrue(rally._is_tile_in_dict((300, 500), rally._recently_joined_tiles))

    # -------------------------------------------------------------
    # CASE 4: Type B Single Rally - Nút xám "Chờ chấp thuận" / "Đã đầy"
    # -------------------------------------------------------------
    def test_case_04_type_b_single_rally_grey_waiting_approval(self):
        """CRITICAL: Nút xám 'Chờ chấp thuận' / 'Đã đầy' -> Bấm Back tím về Map, KHÔNG bấm nút xám, cooldown 30s."""
        frame = self._create_blank_frame()
        self._draw_popup_card(frame)
        self._draw_purple_back_btn(frame)

        frame[int(self.gw_h * 0.90):int(self.gw_h * 0.96), int(self.gw_w * 0.60):int(self.gw_w * 0.85)] = (130, 130, 130)

        rally._last_clicked_tile = (400, 600)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event
            )

        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)

        tap = self.mock_adb.taps[0]
        self.assertAlmostEqual(tap[0] / self.gw_w, config.RALLY_POPUP_BACK_X, delta=0.05)
        self.assertAlmostEqual(tap[1] / self.gw_h, config.RALLY_POPUP_BACK_Y, delta=0.05)
        self.assertTrue(rally._is_tile_in_dict((400, 600), rally._full_tiles_cooldown))

    # -------------------------------------------------------------
    # CASE 5: Type B Single Rally - Nút vàng (Tấn công ô đất thường)
    # -------------------------------------------------------------
    def test_case_05_type_b_yellow_button_attack_tile(self):
        """Nút vàng tấn công đất -> Bấm Back tím, cooldown 30s."""
        frame = self._create_blank_frame()
        self._draw_popup_card(frame)
        self._draw_purple_back_btn(frame)

        frame[int(self.gw_h * 0.90):int(self.gw_h * 0.96), int(self.gw_w * 0.60):int(self.gw_w * 0.85)] = (0, 200, 220)

        rally._last_clicked_tile = (123, 456)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event
            )

        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.gw_w, config.RALLY_POPUP_BACK_X, delta=0.05)
        self.assertTrue(rally._is_tile_in_dict((123, 456), rally._full_tiles_cooldown))

    # -------------------------------------------------------------
    # CASE 6: Type B "Ảo Ảnh" / Bảng xếp hạng cứ điểm (Không có nút hành động)
    # -------------------------------------------------------------
    def test_case_06_type_b_ao_anh_ranking_board(self):
        """Bảng xếp hạng / Ảo ảnh cứ điểm: có nút Back nhưng không có nút hành động -> Bấm Back về Map."""
        frame = self._create_blank_frame()
        self._draw_popup_card(frame)
        self._draw_purple_back_btn(frame)

        rally._last_clicked_tile = (555, 666)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event
            )

        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.gw_w, config.RALLY_POPUP_BACK_X, delta=0.05)
        self.assertTrue(rally._is_tile_in_dict((555, 666), rally._full_tiles_cooldown))

    # -------------------------------------------------------------
    # CASE 7: Type D Popup (Bảng ô đất / mỏ tài nguyên có nút [X] ở đáy giữa)
    # -------------------------------------------------------------
    def test_case_07_type_d_territory_sheet(self):
        """Bảng ô đất / mỏ tài nguyên: Có thẻ popup mở + nút [X] ở đáy giữa -> Bấm nút [X], cooldown 30s."""
        frame = self._create_blank_frame()
        self._draw_popup_card(frame)
        # KHÔNG vẽ nút Back tím để phân biệt với Type B

        # Nút [X] màu trắng ở đáy giữa (Y: 0.925 -> 0.980, X: 0.44 -> 0.56)
        frame[int(self.gw_h * 0.94):int(self.gw_h * 0.97), int(self.gw_w * 0.48):int(self.gw_w * 0.52)] = (255, 255, 255)

        rally._last_clicked_tile = (777, 888)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event
            )

        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        tap = self.mock_adb.taps[0]
        self.assertAlmostEqual(tap[0] / self.gw_w, 0.50, delta=0.05)
        self.assertAlmostEqual(tap[1] / self.gw_h, 0.955, delta=0.05)
        self.assertTrue(rally._is_tile_in_dict((777, 888), rally._full_tiles_cooldown))

    # -------------------------------------------------------------
    # CASE 8: Miss-Click Self-Escape (Bấm ô không mở popup)
    # -------------------------------------------------------------
    def test_case_08_miss_click_self_escape_and_overview(self):
        """Khi bấm vào avatar mà không có popup nào mở: Tự bấm vùng trống (50%, 20%) & gọi kính lúp & cooldown 20s."""
        timer_tpl = assets.get_rally_timer_template()
        th, tw = timer_tpl.shape[:2]

        map_frame = self._create_blank_frame(bg_bgr=(50, 50, 50))
        target_y = int(self.gw_h * 0.35)
        target_x = int(self.gw_w * 0.45)
        map_frame[target_y:target_y+th, target_x:target_x+tw] = timer_tpl

        blank_popup = self._create_blank_frame(bg_bgr=(100, 100, 100))

        call_count = [0]
        def mock_grab_for_scan(sct, mon):
            call_count[0] += 1
            if call_count[0] == 1:
                return make_mock_grab(map_frame)(sct, mon)
            return make_mock_grab(blank_popup)(sct, mon)

        with patch("modules.rally.safe_grab", side_effect=mock_grab_for_scan):
            with patch("modules.rally.ensure_map_overview") as mock_ensure_overview:
                result = rally.scan_and_join_map_rallies(
                    None, self.vp, self.mock_adb, self.stop_event
                )

        self.assertEqual(result, "CLICKED")
        self.assertGreaterEqual(len(self.mock_adb.taps), 2)

        tap_avatar = self.mock_adb.taps[0]
        self.assertTrue(tap_avatar[1] < target_y + th // 2)

        tap_escape = self.mock_adb.taps[1]
        self.assertAlmostEqual(tap_escape[0] / self.gw_w, 0.50, delta=0.05)
        self.assertAlmostEqual(tap_escape[1] / self.gw_h, 0.20, delta=0.05)

        mock_ensure_overview.assert_called_once()

    # -------------------------------------------------------------
    # CASE 9: Peak-Finding NMS (Chống trùng lặp điểm match)
    # -------------------------------------------------------------
    def test_case_09_peak_finding_nms(self):
        """Khi có nhiều điểm match lân cận trong bán kính 35px, NMS chỉ giữ lại 1 điểm có score cao nhất."""
        timer_tpl = assets.get_rally_timer_template()
        th, tw = timer_tpl.shape[:2]

        map_frame = self._create_blank_frame(bg_bgr=(40, 40, 40))
        map_frame[400:400+th, 300:300+tw] = timer_tpl
        map_frame[415:415+th, 315:315+tw] = cv2.addWeighted(timer_tpl, 0.5, np.zeros_like(timer_tpl), 0.5, 0)

        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(map_frame)):
            with patch("modules.rally._handle_rally_detail_popup", return_value=(True, True)):
                result = rally.scan_and_join_map_rallies(
                    None, self.vp, self.mock_adb, self.stop_event
                )

        self.assertEqual(result, "JOINED")
        self.assertEqual(len(self.mock_adb.taps), 1)

    # -------------------------------------------------------------
    # CASE 10: Claim Reward & Anti-loop Failsafe
    # -------------------------------------------------------------
    def test_case_10_claim_reward_and_failsafe(self):
        """Nhận thưởng: bấm nút xanh lá nhận quà; ngắt Failsafe sau 2 lần liên tiếp."""
        frame = self._create_blank_frame()
        ry1 = int(self.gw_h * config.RALLY_REWARD_BTN_REL_Y_MIN)
        ry2 = int(self.gw_h * config.RALLY_REWARD_BTN_REL_Y_MAX)
        rx1 = int(self.gw_w * config.RALLY_REWARD_BTN_REL_X_MIN)
        rx2 = int(self.gw_w * config.RALLY_REWARD_BTN_REL_X_MAX)
        frame[ry1:ry2, rx1:rx2] = (30, 200, 30)

        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            claimed_1 = rally._check_and_claim_reward(None, self.vp, self.mock_adb, self.stop_event)
            self.assertTrue(claimed_1)
            self.assertEqual(rally._consecutive_reward_claims, 1)

            claimed_2 = rally._check_and_claim_reward(None, self.vp, self.mock_adb, self.stop_event)
            self.assertTrue(claimed_2)
            self.assertEqual(rally._consecutive_reward_claims, 2)

            claimed_3 = rally._check_and_claim_reward(None, self.vp, self.mock_adb, self.stop_event)
            self.assertFalse(claimed_3)
            self.assertEqual(rally._consecutive_reward_claims, 0)

    # -------------------------------------------------------------
    # CASE 11: Pillarbox Detection (Viền đen 2 bên màn hình)
    # -------------------------------------------------------------
    def test_case_11_pillarbox_detection(self):
        """Tự động phát hiện viền đen trái và phải của giả lập mobile trên PC."""
        sample = np.zeros((400, 1000, 3), dtype=np.uint8)
        sample[:, 151:851] = (150, 150, 150)

        left_bound, real_w = rally._detect_pillarbox(sample)
        self.assertAlmostEqual(left_bound, 151, delta=2)
        self.assertAlmostEqual(real_w, 700, delta=4)

    # -------------------------------------------------------------
    # CASE 12: Ensure Map Overview (Kính lúp dấu trừ)
    # -------------------------------------------------------------
    def test_case_12_ensure_map_overview(self):
        """Khôi phục toàn cảnh bản đồ bằng template icon kính lúp."""
        zoom_tpl = assets.get_zoom_btn_template()
        if zoom_tpl is not None:
            zh, zw = zoom_tpl.shape[:2]
            frame = self._create_blank_frame()
            zy = int(self.gw_h * 0.75)
            zx = int(self.gw_w * 0.08)
            frame[zy:zy+zh, zx:zx+zw] = zoom_tpl

            with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
                restored = rally.ensure_map_overview(None, self.vp, self.mock_adb, self.stop_event)

            self.assertTrue(restored)
            self.assertGreaterEqual(len(self.mock_adb.taps), 1)
            tap = self.mock_adb.taps[0]
            self.assertAlmostEqual(tap[0] / self.gw_w, 0.08, delta=0.08)
            self.assertAlmostEqual(tap[1] / self.gw_h, 0.77, delta=0.08)

    # -------------------------------------------------------------
    # CASE 13: User Uploaded 6 Real Screens Verification
    # -------------------------------------------------------------
    def test_case_13_user_real_screens_classification(self):
        """Kiểm thử trực tiếp trên 6 ảnh chụp thực tế do người dùng cung cấp."""
        user_files = sorted(glob.glob(r"C:\Users\ADMIN\.gemini\antigravity\brain\93b2c7c8-abdd-44b8-bc5f-e53ca99e9bbe\.user_uploaded\*.jpg"))
        if len(user_files) < 6:
            self.skipTest("Chưa có đủ 6 ảnh user upload để test")

        # Hình 1: Mapview -> Tuyệt đối không nhận diện là popup, KHÔNG bấm nút [X] ở đáy!
        img1 = cv2.imread(user_files[0])
        h1, w1 = img1.shape[:2]
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", return_value=img1):
            is_pop, is_join = rally._handle_rally_detail_popup(None, (0, 0, w1, h1), self.mock_adb, self.stop_event)
        self.assertFalse(is_pop, "Hình 1 (Mapview) tuyệt đối KHÔNG được nhận là popup")
        self.assertEqual(len(self.mock_adb.taps), 0, "Hình 1 (Mapview) tuyệt đối KHÔNG được bấm nút [X] ở đáy!")

        # Hình 2: Lane có thể tấn công (có nút Back tím + Tổng Tấn Công + Tấn Công) -> Bấm Back
        img2 = cv2.imread(user_files[1])
        h2, w2 = img2.shape[:2]
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", return_value=img2):
            is_pop, is_join = rally._handle_rally_detail_popup(None, (0, 0, w2, h2), self.mock_adb, self.stop_event)
        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.mock_adb.screen_size[0], config.RALLY_POPUP_BACK_X, delta=0.08)

        # Hình 3: Đất đồng minh (có nút [X] ở đáy giữa, KHÔNG có nút Back) -> Bấm nút [X]
        img3 = cv2.imread(user_files[2])
        h3, w3 = img3.shape[:2]
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", return_value=img3):
            is_pop, is_join = rally._handle_rally_detail_popup(None, (0, 0, w3, h3), self.mock_adb, self.stop_event)
        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.mock_adb.screen_size[0], 0.50, delta=0.08)
        self.assertAlmostEqual(self.mock_adb.taps[0][1] / self.mock_adb.screen_size[1], 0.955, delta=0.08)

        # Hình 4: Ảo ảnh không có đường đánh (có nút Back tím) -> Bấm Back
        img4 = cv2.imread(user_files[3])
        h4, w4 = img4.shape[:2]
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", return_value=img4):
            is_pop, is_join = rally._handle_rally_detail_popup(None, (0, 0, w4, h4), self.mock_adb, self.stop_event)
        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.mock_adb.screen_size[0], config.RALLY_POPUP_BACK_X, delta=0.08)

        # Hình 5: Lane địch không có đường đánh (có nút [X] ở đáy giữa, KHÔNG có nút Back) -> Bấm nút [X]
        img5 = cv2.imread(user_files[4])
        h5, w5 = img5.shape[:2]
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", return_value=img5):
            is_pop, is_join = rally._handle_rally_detail_popup(None, (0, 0, w5, h5), self.mock_adb, self.stop_event)
        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.mock_adb.screen_size[0], 0.50, delta=0.08)
        self.assertAlmostEqual(self.mock_adb.taps[0][1] / self.mock_adb.screen_size[1], 0.955, delta=0.08)

        # Hình 6: Ảo ảnh có đường đánh (có nút Back tím) -> Bấm Back
        img6 = cv2.imread(user_files[5])
        h6, w6 = img6.shape[:2]
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", return_value=img6):
            is_pop, is_join = rally._handle_rally_detail_popup(None, (0, 0, w6, h6), self.mock_adb, self.stop_event)
        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.mock_adb.screen_size[0], config.RALLY_POPUP_BACK_X, delta=0.08)

    def test_case_14_scaled_windows(self):
        """
        Kiểm thử giả lập bị thu nhỏ trên các màn hình laptop nhỏ hoặc cửa sổ co giãn:
        Scale từ 0.35x (cửa sổ siêu nhỏ ~200x340px) đến 2.0x (màn hình độ nét cao 2K/4K).
        Đảm bảo 100% độ chính xác:
        - Viewmap (Hình 1): Tuyệt đối KHÔNG bao giờ bấm [X].
        - Các popup (Hình 2..6): Đóng chuẩn xác bằng Back hoặc [X] tương ứng.
        """
        user_dir = r"C:/Users/ADMIN/.gemini/antigravity/brain/93b2c7c8-abdd-44b8-bc5f-e53ca99e9bbe/.user_uploaded"
        user_files = sorted(glob.glob(os.path.join(user_dir, "*.jpg")))
        if len(user_files) < 6:
            self.skipTest("Không tìm thấy đủ 6 ảnh người dùng")

        test_scales = [0.35, 0.50, 0.70, 1.50]
        for sc in test_scales:
            # 1. Hình 1 (Viewmap)
            img1 = cv2.imread(user_files[0])
            h1, w1 = img1.shape[:2]
            scaled1 = cv2.resize(img1, (int(w1 * sc), int(h1 * sc)))
            sh1, sw1 = scaled1.shape[:2]
            self.mock_adb.clear()
            self.mock_adb.screen_size = (sw1, sh1)
            with patch("modules.rally.safe_grab", return_value=scaled1):
                is_pop, _ = rally._handle_rally_detail_popup(None, (0, 0, sw1, sh1), self.mock_adb, self.stop_event)
            self.assertFalse(is_pop, f"Scale {sc}: Viewmap không được nhận là popup")
            self.assertEqual(len(self.mock_adb.taps), 0, f"Scale {sc}: Viewmap không được bấm nút X!")

            # 2. Hình 2 (Lane có đường đánh -> Back)
            img2 = cv2.imread(user_files[1])
            h2, w2 = img2.shape[:2]
            scaled2 = cv2.resize(img2, (int(w2 * sc), int(h2 * sc)))
            sh2, sw2 = scaled2.shape[:2]
            self.mock_adb.clear()
            self.mock_adb.screen_size = (sw2, sh2)
            with patch("modules.rally.safe_grab", return_value=scaled2):
                is_pop, _ = rally._handle_rally_detail_popup(None, (0, 0, sw2, sh2), self.mock_adb, self.stop_event)
            self.assertTrue(is_pop, f"Scale {sc}: Hình 2 phải được nhận là popup")
            self.assertEqual(len(self.mock_adb.taps), 1, f"Scale {sc}: Hình 2 phải tap đúng 1 lần")
            self.assertAlmostEqual(self.mock_adb.taps[0][0] / sw2, config.RALLY_POPUP_BACK_X, delta=0.08)

            # 3. Hình 3 (Đất đồng minh -> Nút X)
            img3 = cv2.imread(user_files[2])
            h3, w3 = img3.shape[:2]
            scaled3 = cv2.resize(img3, (int(w3 * sc), int(h3 * sc)))
            sh3, sw3 = scaled3.shape[:2]
            self.mock_adb.clear()
            self.mock_adb.screen_size = (sw3, sh3)
            with patch("modules.rally.safe_grab", return_value=scaled3):
                is_pop, _ = rally._handle_rally_detail_popup(None, (0, 0, sw3, sh3), self.mock_adb, self.stop_event)
            self.assertTrue(is_pop, f"Scale {sc}: Hình 3 phải được nhận là popup")
            self.assertEqual(len(self.mock_adb.taps), 1)
            self.assertAlmostEqual(self.mock_adb.taps[0][0] / sw3, 0.50, delta=0.08)
            self.assertAlmostEqual(self.mock_adb.taps[0][1] / sh3, 0.955, delta=0.08)

            # 4. Hình 4 (Ảo ảnh không có đường đánh -> Back)
            img4 = cv2.imread(user_files[3])
            h4, w4 = img4.shape[:2]
            scaled4 = cv2.resize(img4, (int(w4 * sc), int(h4 * sc)))
            sh4, sw4 = scaled4.shape[:2]
            self.mock_adb.clear()
            self.mock_adb.screen_size = (sw4, sh4)
            with patch("modules.rally.safe_grab", return_value=scaled4):
                is_pop, _ = rally._handle_rally_detail_popup(None, (0, 0, sw4, sh4), self.mock_adb, self.stop_event)
            self.assertTrue(is_pop, f"Scale {sc}: Hình 4 phải được nhận là popup")
            self.assertEqual(len(self.mock_adb.taps), 1)
            self.assertAlmostEqual(self.mock_adb.taps[0][0] / sw4, config.RALLY_POPUP_BACK_X, delta=0.08)

            # 5. Hình 5 (Lane địch không có đường đánh -> Nút X)
            img5 = cv2.imread(user_files[4])
            h5, w5 = img5.shape[:2]
            scaled5 = cv2.resize(img5, (int(w5 * sc), int(h5 * sc)))
            sh5, sw5 = scaled5.shape[:2]
            self.mock_adb.clear()
            self.mock_adb.screen_size = (sw5, sh5)
            with patch("modules.rally.safe_grab", return_value=scaled5):
                is_pop, _ = rally._handle_rally_detail_popup(None, (0, 0, sw5, sh5), self.mock_adb, self.stop_event)
            self.assertTrue(is_pop, f"Scale {sc}: Hình 5 phải được nhận là popup")
            self.assertEqual(len(self.mock_adb.taps), 1)
            self.assertAlmostEqual(self.mock_adb.taps[0][0] / sw5, 0.50, delta=0.08)
            self.assertAlmostEqual(self.mock_adb.taps[0][1] / sh5, 0.955, delta=0.08)

            # 6. Hình 6 (Ảo ảnh có đường đánh -> Back)
            img6 = cv2.imread(user_files[5])
            h6, w6 = img6.shape[:2]
            scaled6 = cv2.resize(img6, (int(w6 * sc), int(h6 * sc)))
            sh6, sw6 = scaled6.shape[:2]
            self.mock_adb.clear()
            self.mock_adb.screen_size = (sw6, sh6)
            with patch("modules.rally.safe_grab", return_value=scaled6):
                is_pop, _ = rally._handle_rally_detail_popup(None, (0, 0, sw6, sh6), self.mock_adb, self.stop_event)
            self.assertTrue(is_pop, f"Scale {sc}: Hình 6 phải được nhận là popup")
            self.assertEqual(len(self.mock_adb.taps), 1)
            self.assertAlmostEqual(self.mock_adb.taps[0][0] / sw6, config.RALLY_POPUP_BACK_X, delta=0.08)

    # -------------------------------------------------------------
    # CASE 15: Dune Chat Detection, Anti-Drift Scroll & Join Flow
    # -------------------------------------------------------------
    def _create_chat_frame(self, include_green_btn: bool = False, lien_minh_active: bool = True) -> np.ndarray:
        """Tạo khung giả lập giao diện Chat Liên Minh chuẩn tỉ lệ."""
        frame = self._create_blank_frame(bg_bgr=(25, 25, 30))
        # Vùng thân Chat nền trắng/xám sáng
        frame[int(self.gw_h * 0.14):int(self.gw_h * 0.83), int(self.gw_w * 0.19):int(self.gw_w * 0.93)] = (238, 236, 240)
        # Thanh nhập liệu trắng + Nút Gửi xanh lá ở góc dưới phải
        frame[int(self.gw_h * 0.84):int(self.gw_h * 0.90), int(self.gw_w * 0.20):int(self.gw_w * 0.65)] = (230, 230, 230)
        frame[int(self.gw_h * 0.835):int(self.gw_h * 0.905), int(self.gw_w * 0.76):int(self.gw_w * 0.91)] = (35, 195, 50)
        # Tab Liên Minh bên trái (nền tím + icon khiên vàng chuẩn)
        if lien_minh_active:
            frame[int(self.gw_h * 0.08):int(self.gw_h * 0.18), int(self.gw_w * 0.04):int(self.gw_w * 0.17)] = (220, 60, 140)
            shield_tpl = assets.get_lien_minh_tab_template()
            if shield_tpl is not None:
                sc = self.gw_h / float(getattr(config, "RALLY_CHAT_TAB_REF_HEIGHT", 715.0))
                tw, th = max(8, int(shield_tpl.shape[1] * sc)), max(8, int(shield_tpl.shape[0] * sc))
                scaled_tpl = cv2.resize(shield_tpl, (tw, th))
                sy = int(self.gw_h * 0.125) - th // 2
                sx = int(self.gw_w * 0.105) - tw // 2
                frame[sy:sy + th, sx:sx + tw] = scaled_tpl
        # Nút Tham gia màu xanh lá dạng thanh ngang dài trong thẻ Rally + ô tím đặc trưng phía trên
        if include_green_btn:
            frame[int(self.gw_h * 0.61):int(self.gw_h * 0.68), int(self.gw_w * 0.30):int(self.gw_w * 0.52)] = (200, 80, 160)
            by1, by2 = int(self.gw_h * 0.69), int(self.gw_h * 0.735)
            bx1, bx2 = int(self.gw_w * 0.34), int(self.gw_w * 0.84)
            frame[by1:by2, bx1:bx2] = (35, 200, 50)
        return frame

    def test_case_15_dune_chat_detection_and_bottom_join(self):
        """Dune Chat: Phân biệt đúng Chat vs Mapview/Popup, tìm nút Tham gia ngang & bỏ qua nút Gửi."""
        map_frame = self._create_blank_frame(bg_bgr=(50, 150, 200))
        self.assertFalse(rally._is_chat_open(map_frame))

        chat_empty = self._create_chat_frame(include_green_btn=False, lien_minh_active=True)
        self.assertTrue(rally._is_chat_open(chat_empty))
        self.assertTrue(rally._is_lien_minh_tab_active(chat_empty))
        self.assertEqual(rally._find_chat_join_buttons(chat_empty), [])

        chat_with_rally = self._create_chat_frame(include_green_btn=True, lien_minh_active=True)
        btns = rally._find_chat_join_buttons(chat_with_rally)
        self.assertEqual(len(btns), 1, "Chỉ được bắt đúng 1 nút Tham gia ngang, không bắt nút Gửi")
        self.assertAlmostEqual(btns[0][0] / self.gw_w, 0.59, delta=0.05)
        self.assertAlmostEqual(btns[0][1] / self.gw_h, 0.712, delta=0.04)

    def test_case_16_dune_chat_anti_drift_scroll_and_popup_join(self):
        """Dune Chat chống trôi: Đáy không có nút -> Vuốt lên thấy Rally -> Bấm vào Popup Type B -> Join & Back."""
        chat_empty = self._create_chat_frame(include_green_btn=False, lien_minh_active=True)
        chat_drifted = self._create_chat_frame(include_green_btn=True, lien_minh_active=True)

        # Popup Type B mở lên sau khi bấm nút xanh trong Chat
        popup_frame = self._create_blank_frame()
        self._draw_popup_card(popup_frame)
        self._draw_purple_back_btn(popup_frame)
        popup_frame[int(self.gw_h * 0.90):int(self.gw_h * 0.96), int(self.gw_w * 0.60):int(self.gw_w * 0.85)] = (30, 200, 30)

        def mock_grab(sct, mon):
            if len(self.mock_adb.swipes) == 0:
                return make_mock_grab(chat_empty)(sct, mon)
            if len(self.mock_adb.taps) == 0:
                return make_mock_grab(chat_drifted)(sct, mon)
            return make_mock_grab(popup_frame)(sct, mon)

        with patch("modules.rally.safe_grab", side_effect=mock_grab):
            res = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event)

        self.assertEqual(res, "JOINED")
        self.assertEqual(len(self.mock_adb.swipes), 1, "Phải vuốt lên 1 nhịp để tìm Rally bị trôi")
        # Tap 1: Tham gia trong Chat; Tap 2: Tham gia trong Popup; Tap 3: Back tím về Map
        self.assertEqual(len(self.mock_adb.taps), 3)
        self.assertAlmostEqual(self.mock_adb.taps[2][0] / self.gw_w, config.RALLY_POPUP_BACK_X, delta=0.05)

    def test_case_17_dune_chat_no_rally_scroll_back_and_safe_close(self):
        """Dune Chat: allow_scroll=False không vuốt; allow_scroll=True vuốt lên 2 nhịp rồi vuốt xuống lại đáy 2 nhịp."""
        chat_empty = self._create_chat_frame(include_green_btn=False, lien_minh_active=True)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_empty)):
            res_fast = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(res_fast, "NONE")
        self.assertEqual(len(self.mock_adb.swipes), 0, "Chế độ camp nhanh không được vuốt liên tục")

        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_empty)):
            res = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=True)

        self.assertEqual(res, "NONE")
        self.assertEqual(len(self.mock_adb.swipes), 4, "Phải vuốt lên 2 nhịp rồi vuốt xuống lại đáy 2 nhịp")

        # Cooldown chống bấm lặp khi nút xanh bấm vào không mở popup
        self.mock_adb.clear()
        chat_stale = self._create_chat_frame(include_green_btn=True, lien_minh_active=True)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_stale)):
            res_nopop = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(res_nopop, "NO_POPUP")
        self.assertEqual(len(self.mock_adb.taps), 1)

        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_stale)):
            res_cooldown = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(res_cooldown, "NONE")
        self.assertEqual(len(self.mock_adb.taps), 0, "Vị trí Y vừa lỗi phải bị khóa cooldown 8s")

        # Đóng Chat an toàn bằng khoảng trống phía trên đỉnh (Y ~ 0.030, tránh xa nút X đáy 0.955)
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_empty)):
            closed = rally._close_chat_if_open(None, self.vp, self.mock_adb, self.stop_event)
        self.assertTrue(closed)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][1] / self.gw_h, 0.030, delta=0.02)

        # Trên Mapview tuyệt đối không bấm [X]
        self.mock_adb.clear()
        map_frame = self._create_blank_frame(bg_bgr=(50, 150, 200))
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(map_frame)):
            closed_map = rally._close_chat_if_open(None, self.vp, self.mock_adb, self.stop_event)
        self.assertFalse(closed_map)
        self.assertEqual(len(self.mock_adb.taps), 0)

    def test_case_18_dune_chat_full_card_lag_state_fingerprint(self):
        """Lag state 4/4 vẫn hiện nút xanh: Vào Popup 'Đã đầy' -> Back -> Khóa thẻ 45s kể cả khi thẻ trôi Y."""
        # Tạo thẻ A (4/4 bị lag nút xanh ở Y=0.71) với họa tiết riêng
        chat_lag_a = self._create_chat_frame(include_green_btn=True, lien_minh_active=True)
        chat_lag_a[int(self.gw_h * 0.61):int(self.gw_h * 0.67), int(self.gw_w * 0.35):int(self.gw_w * 0.60)] = (180, 70, 140)

        # Popup 'Đã đầy' (nút Back tím + nút xám)
        full_popup = self._create_blank_frame()
        self._draw_popup_card(full_popup)
        self._draw_purple_back_btn(full_popup)
        full_popup[int(self.gw_h * 0.90):int(self.gw_h * 0.96), int(self.gw_w * 0.30):int(self.gw_w * 0.85)] = (150, 150, 150)

        def mock_grab_full(sct, mon):
            if len(self.mock_adb.taps) == 0:
                return make_mock_grab(chat_lag_a)(sct, mon)
            return make_mock_grab(full_popup)(sct, mon)

        with patch("modules.rally.safe_grab", side_effect=mock_grab_full):
            res1 = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(res1, "POPUP_HANDLED")
        self.assertEqual(len(self.mock_adb.taps), 2)  # Tap 1: Chat, Tap 2: Back tím (không bấm nút xám)

        # Thẻ A bị trôi lên trên ~200px (khác hẳn y_bucket!) -> Vẫn phải bị khóa cooldown 45s nhờ chữ ký thẻ
        chat_lag_a_shifted = self._create_chat_frame(include_green_btn=False, lien_minh_active=True)
        by1, by2 = int(self.gw_h * 0.50), int(self.gw_h * 0.545)
        bx1, bx2 = int(self.gw_w * 0.34), int(self.gw_w * 0.84)
        chat_lag_a_shifted[by1:by2, bx1:bx2] = (35, 200, 50)
        chat_lag_a_shifted[int(self.gw_h * 0.42):int(self.gw_h * 0.48), int(self.gw_w * 0.35):int(self.gw_w * 0.60)] = (180, 70, 140)

        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_lag_a_shifted)):
            res2 = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(res2, "NONE")
        self.assertEqual(len(self.mock_adb.taps), 0, "Thẻ 4/4 bị trôi vị trí vẫn phải bị chặn không bấm lại")

        # Thẻ B hoàn toàn mới xuất hiện ở đúng vị trí Y cũ -> Phải bấm ngay không bị chặn oan
        chat_new_b = self._create_chat_frame(include_green_btn=True, lien_minh_active=True)
        chat_new_b[int(self.gw_h * 0.61):int(self.gw_h * 0.67), int(self.gw_w * 0.35):int(self.gw_w * 0.80)] = (40, 190, 210)
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_new_b)):
            res3 = rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(res3, "NO_POPUP")
        self.assertGreaterEqual(len(self.mock_adb.taps), 1, "Thẻ mới khác nội dung ở vị trí Y cũ phải bấm được ngay")

    def test_case_19_high_multi_rally_sheet(self):
        """Bảng danh sách nhiều Rally cùng 1 ô dạng cao (Dune Y=0.02..0.08): Bấm nút xanh, cuộn và đóng đúng vùng mờ phía trên."""
        frame = self._create_blank_frame(bg_bgr=(118, 65, 75))
        # Thanh tiêu đề tối trên cùng Y: 0.02..0.08 và vùng mờ góc phải Y: 0.01..0.07
        frame[int(self.gw_h * 0.01):int(self.gw_h * 0.085), :] = (40, 30, 35)
        # Thẻ 1 có nút xanh (Y: 0.25..0.305 -> bh ~ 0.055) + icon vuông xanh nhỏ cạnh bên
        frame[int(self.gw_h * 0.25):int(self.gw_h * 0.305), int(self.gw_w * 0.64):int(self.gw_w * 0.91)] = (35, 200, 50)
        frame[int(self.gw_h * 0.42):int(self.gw_h * 0.48), int(self.gw_w * 0.80):int(self.gw_w * 0.90)] = (35, 200, 50)  # icon lực chiến vuông
        # Thẻ 2 nút xám
        frame[int(self.gw_h * 0.51):int(self.gw_h * 0.565), int(self.gw_w * 0.64):int(self.gw_w * 0.91)] = (140, 140, 140)

        frame_after_scroll = frame.copy()
        frame_after_scroll[int(self.gw_h * 0.25):int(self.gw_h * 0.305), int(self.gw_w * 0.64):int(self.gw_w * 0.91)] = (140, 140, 140)

        def mock_grab(sct, mon):
            cur = frame if len(self.mock_adb.swipes) == 0 else frame_after_scroll
            return make_mock_grab(cur)(sct, mon)

        with patch("modules.rally.safe_grab", side_effect=mock_grab):
            is_pop, is_join = rally._handle_rally_detail_popup(None, self.vp, self.mock_adb, self.stop_event)

        self.assertTrue(is_pop)
        self.assertTrue(is_join)
        self.assertEqual(len(self.mock_adb.swipes), 1)
        # Tap 1: Tham gia thẻ 1; Tap 2: Đóng ở vùng mờ phía trên (0.70, 0.04)
        self.assertEqual(len(self.mock_adb.taps), 2)
        self.assertAlmostEqual(self.mock_adb.taps[0][1] / self.gw_h, 0.277, delta=0.04)
        self.assertAlmostEqual(self.mock_adb.taps[1][0] / self.gw_w, 0.70, delta=0.05)
        self.assertAlmostEqual(self.mock_adb.taps[1][1] / self.gw_h, 0.04, delta=0.03)

    def test_case_20_dune_zero_x_protection_and_world_tab_offset(self):
        """Chống bấm nhầm nút X trên Chat / allow_type_d_close_x=False & tự nhận tab Liên Minh ở slot 2 dưới tab Thế Giới."""
        # 1. Chat đang mở có điểm trắng sáng ở đáy (Y: 0.925..0.980) -> _handle_rally_detail_popup PHẢI trả (False, False)
        chat_bright_x = self._create_chat_frame(include_green_btn=False, lien_minh_active=True)
        chat_bright_x[int(self.gw_h * 0.94):int(self.gw_h * 0.97), int(self.gw_w * 0.47):int(self.gw_w * 0.53)] = (255, 255, 255)
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_bright_x)):
            is_pop, is_join = rally._handle_rally_detail_popup(None, self.vp, self.mock_adb, self.stop_event)
        self.assertFalse(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 0, "Tuyệt đối không được bấm Nút X khi đang mở khung Chat!")

        # 2. Type D frame khi allow_type_d_close_x=False (chế độ Dune) -> KHÔNG được bấm Nút X
        type_d_frame = self._create_blank_frame()
        self._draw_popup_card(type_d_frame)
        type_d_frame[int(self.gw_h * 0.94):int(self.gw_h * 0.97), int(self.gw_w * 0.48):int(self.gw_w * 0.52)] = (255, 255, 255)
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(type_d_frame)):
            is_pop_d, _ = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event, allow_type_d_close_x=False
            )
        self.assertFalse(is_pop_d)
        self.assertEqual(len(self.mock_adb.taps), 0, "Chế độ Dune tuyệt đối không bao giờ bấm Nút X Type D!")

        # 3. Chat có tab Thế Giới (xanh cyan) ở slot 1 (Y=0.07..0.18), Liên Minh ở slot 2 (Y=0.19..0.30) có icon khiên vàng
        shield_tpl = assets.get_lien_minh_tab_template()
        self.assertIsNotNone(shield_tpl)
        sc = self.gw_h / float(getattr(config, "RALLY_CHAT_TAB_REF_HEIGHT", 715.0))
        scaled_shield = cv2.resize(shield_tpl, (max(8, int(shield_tpl.shape[1] * sc)), max(8, int(shield_tpl.shape[0] * sc))))
        sh_s, sw_s = scaled_shield.shape[:2]

        chat_world_tab = self._create_chat_frame(include_green_btn=False, lien_minh_active=False)
        # Vẽ quả địa cầu cyan ở slot 1
        chat_world_tab[int(self.gw_h * 0.09):int(self.gw_h * 0.16), int(self.gw_w * 0.06):int(self.gw_w * 0.14)] = (220, 180, 30)
        # Vẽ slot 2 màu tím đang active + icon khiên vàng Liên Minh
        chat_world_tab[int(self.gw_h * 0.20):int(self.gw_h * 0.29), int(self.gw_w * 0.04):int(self.gw_w * 0.17)] = (220, 60, 140)
        sy2 = int(self.gw_h * config.RALLY_CHAT_LIEN_MINH_TAB_Y_SLOT2) - sh_s // 2
        sx2 = int(self.gw_w * 0.105) - sw_s // 2
        chat_world_tab[sy2:sy2 + sh_s, sx2:sx2 + sw_s] = scaled_shield
        self.assertTrue(rally._is_lien_minh_tab_active(chat_world_tab))
        bounds = rally._detect_lien_minh_tab_target_y(chat_world_tab)
        self.assertIsNotNone(bounds)
        self.assertAlmostEqual(bounds[2], config.RALLY_CHAT_LIEN_MINH_TAB_Y_SLOT2, delta=0.02)

        # Nếu slot 2 chưa tím -> scan_and_join_chat_rallies phải bấm đúng vào slot 2 (khiên vàng), không bấm nhầm Thế Giới
        chat_world_inactive = chat_world_tab.copy()
        chat_world_inactive[int(self.gw_h * 0.20):int(self.gw_h * 0.29), int(self.gw_w * 0.04):int(self.gw_w * 0.17)] = (25, 25, 30)
        chat_world_inactive[sy2:sy2 + sh_s, sx2:sx2 + sw_s] = scaled_shield
        self.assertFalse(rally._is_lien_minh_tab_active(chat_world_inactive))
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_world_inactive)):
            rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][1] / self.gw_h, config.RALLY_CHAT_LIEN_MINH_TAB_Y_SLOT2, delta=0.02)

        # 4. Tuyệt đối KHÔNG bấm mù slot 1/2 nếu không thấy icon khiên vàng (VD: quá nhiều tin nhắn lạ đẩy tuột Liên Minh)
        chat_no_shield = self._create_chat_frame(include_green_btn=False, lien_minh_active=False)
        chat_no_shield[int(self.gw_h * 0.08):int(self.gw_h * 0.17), int(self.gw_w * 0.05):int(self.gw_w * 0.15)] = (200, 180, 120)
        self.assertIsNone(rally._detect_lien_minh_tab_target_y(chat_no_shield))
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_no_shield)):
            rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(len(self.mock_adb.taps), 0, "Không khớp khiên vàng thì tuyệt đối KHÔNG được bấm mù vào slot người lạ!")

    def test_case_21_ignore_user_green_chat_bubbles(self):
        """Bong bóng chat màu xanh nõn chuối của người dùng (dài hoặc ngắn) không bao giờ bị nhầm là nút Tham gia."""
        # 1. Bong bóng chat dài đúng màu xanh nõn chuối thực tế BGR (22, 232, 195)
        chat_user_msg = self._create_chat_frame(include_green_btn=False, lien_minh_active=True)
        chat_user_msg[int(self.gw_h * 0.62):int(self.gw_h * 0.665), int(self.gw_w * 0.34):int(self.gw_w * 0.86)] = (22, 232, 195)
        self.assertEqual(rally._find_chat_join_buttons(chat_user_msg), [])

        # 2. Kể cả bong bóng cùng màu xanh ngọc (35, 200, 50) nhưng KHÔNG có thẻ Rally tím phía trên -> vẫn phải bỏ qua
        chat_plain_green = self._create_chat_frame(include_green_btn=False, lien_minh_active=True)
        chat_plain_green[int(self.gw_h * 0.62):int(self.gw_h * 0.665), int(self.gw_w * 0.34):int(self.gw_w * 0.86)] = (35, 200, 50)
        self.assertEqual(rally._find_chat_join_buttons(chat_plain_green), [])

        # 3. Nếu bên dưới có thẻ Rally thật (có ô tím phía trên) thì vẫn bắt đúng thẻ Rally, bỏ qua bong bóng chat ở trên
        chat_mixed = chat_user_msg.copy()
        chat_mixed[int(self.gw_h * 0.68):int(self.gw_h * 0.75), int(self.gw_w * 0.30):int(self.gw_w * 0.52)] = (200, 80, 160)
        chat_mixed[int(self.gw_h * 0.76):int(self.gw_h * 0.805), int(self.gw_w * 0.34):int(self.gw_w * 0.84)] = (35, 200, 50)
        btns = rally._find_chat_join_buttons(chat_mixed)
        self.assertEqual(len(btns), 1)
        self.assertAlmostEqual(btns[0][1] / self.gw_h, 0.782, delta=0.03)

    def test_case_22_lien_minh_tab_below_tradecard_stranger_dm(self):
        """Khi tradecard / tin nhắn người lạ nhảy lên slot 1-2 đẩy Liên Minh xuống slot 3 -> KHÔNG bấm nhầm tradecard!"""
        shield_tpl = assets.get_lien_minh_tab_template()
        self.assertIsNotNone(shield_tpl)
        scale = self.gw_h / float(getattr(config, "RALLY_CHAT_TAB_REF_HEIGHT", 715.0))
        scaled_shield = cv2.resize(shield_tpl, (max(8, int(shield_tpl.shape[1] * scale)), max(8, int(shield_tpl.shape[0] * scale))))
        sh, sw = scaled_shield.shape[:2]

        # Tạo khung Chat: slot 1 là tradecard, slot 2 là tin nhắn người lạ, slot 3 (Y ~ 0.36) là Liên Minh đang tím sẵn
        chat_tradecard_top = self._create_chat_frame(include_green_btn=False, lien_minh_active=False)
        # Vẽ avatar giả ở slot 1 và slot 2
        chat_tradecard_top[int(self.gw_h * 0.08):int(self.gw_h * 0.17), int(self.gw_w * 0.05):int(self.gw_w * 0.15)] = (200, 180, 120)
        chat_tradecard_top[int(self.gw_h * 0.20):int(self.gw_h * 0.29), int(self.gw_w * 0.05):int(self.gw_w * 0.15)] = (120, 160, 220)
        # Vẽ nền tím active ở slot 3 + dán đúng icon khiên vàng Liên Minh
        chat_tradecard_top[int(self.gw_h * 0.31):int(self.gw_h * 0.42), int(self.gw_w * 0.04):int(self.gw_w * 0.17)] = (220, 60, 140)
        sy = int(self.gw_h * 0.365) - sh // 2
        sx = int(self.gw_w * 0.105) - sw // 2
        chat_tradecard_top[sy:sy+sh, sx:sx+sw] = scaled_shield

        # Đã đứng sẵn ở Liên Minh (slot 3 tím) -> _is_lien_minh_tab_active PHẢI là True (không được swap lên tradecard!)
        self.assertTrue(rally._is_lien_minh_tab_active(chat_tradecard_top))
        _, _, target_y = rally._detect_lien_minh_tab_target_y(chat_tradecard_top)
        self.assertAlmostEqual(target_y, 0.365, delta=0.03)

        # Nếu đang đứng nhầm ở tradecard (slot 1 tím, slot 3 không tím) -> phải bấm chuyển đúng xuống slot 3 (Liên Minh)
        chat_on_tradecard = chat_tradecard_top.copy()
        chat_on_tradecard[int(self.gw_h * 0.31):int(self.gw_h * 0.42), int(self.gw_w * 0.04):int(self.gw_w * 0.17)] = (25, 25, 30)
        chat_on_tradecard[sy:sy+sh, sx:sx+sw] = scaled_shield
        chat_on_tradecard[int(self.gw_h * 0.08):int(self.gw_h * 0.17), int(self.gw_w * 0.04):int(self.gw_w * 0.17)] = (220, 60, 140)
        self.assertFalse(rally._is_lien_minh_tab_active(chat_on_tradecard))
        self.mock_adb.clear()
        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(chat_on_tradecard)):
            rally.scan_and_join_chat_rallies(None, self.vp, self.mock_adb, self.stop_event, allow_scroll=False)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][1] / self.gw_h, 0.365, delta=0.03)

    def test_case_23_high_multi_rally_sheet_with_bottom_x_even_when_type_d_disabled(self):
        """Bảng 2+ Rally (總攻) có thanh đen + nút [X] trắng ở đáy -> Phải bấm chính tâm [X] kể cả khi allow_type_d_close_x=False."""
        frame = self._create_blank_frame(bg_bgr=(190, 90, 108))  # Nền tím bảng 總攻 (hơi sáng như ảnh chụp)
        frame[int(self.gw_h * 0.01):int(self.gw_h * 0.085), :] = (65, 35, 45)  # Header tối phía trên
        # Thẻ 1 nút xám 'Đã đầy' (已達滿員)
        frame[int(self.gw_h * 0.23):int(self.gw_h * 0.285), int(self.gw_w * 0.64):int(self.gw_w * 0.91)] = (170, 170, 170)
        # Thanh đen ở đáy + nút [X] trắng ở giữa (Y ~ 0.945)
        frame[int(self.gw_h * 0.91):self.gw_h, :] = (35, 25, 25)
        frame[int(self.gw_h * 0.93):int(self.gw_h * 0.96), int(self.gw_w * 0.47):int(self.gw_w * 0.53)] = (240, 240, 240)

        with patch("modules.rally.safe_grab", side_effect=make_mock_grab(frame)):
            is_pop, is_join = rally._handle_rally_detail_popup(
                None, self.vp, self.mock_adb, self.stop_event, allow_type_d_close_x=False
            )

        self.assertTrue(is_pop)
        self.assertFalse(is_join)
        self.assertEqual(len(self.mock_adb.taps), 1)
        self.assertAlmostEqual(self.mock_adb.taps[0][0] / self.gw_w, 0.50, delta=0.04)
        self.assertAlmostEqual(self.mock_adb.taps[0][1] / self.gw_h, 0.945, delta=0.03)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestRallyCases)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
