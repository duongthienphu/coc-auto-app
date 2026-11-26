"""
Module Quản lý Kết nối và Điều khiển ADB (Android Debug Bridge)
Hỗ trợ tự động dò tìm cổng của BlueStacks 5, LDPlayer, MuMu Player, NoxPlayer.
"""

import os
import sys
import re
import subprocess
import winreg
from typing import Optional, List, Dict, Tuple


def get_base_dir() -> str:
    """Trả về thư mục gốc của ứng dụng (hỗ trợ cả môi trường PyInstaller .exe)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_adb_binary() -> str:
    """Tìm file thực thi adb.exe trong dự án hoặc trong hệ thống.
    Khi chạy dưới dạng PyInstaller .exe (frozen), copy adb sang %LOCALAPPDATA%
    để tránh khóa thư mục tạm _MEIPASS gây lỗi 'Failed to remove temporary directory'.
    """
    ld_adb = r"D:\LDPlayer\LDPlayer9\adb.exe"
    if os.path.isfile(ld_adb):
        return ld_adb
    # 1. Nếu là PyInstaller frozen .exe
    if getattr(sys, "frozen", False):
        try:
            local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            target_bin_dir = os.path.join(local_appdata, "COC_AutoMaster", "bin")
            os.makedirs(target_bin_dir, exist_ok=True)

            target_adb = os.path.join(target_bin_dir, "adb.exe")
            src_bin_dir = os.path.join(sys._MEIPASS, "binaries")  # type: ignore

            import shutil
            for name in ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]:
                src = os.path.join(src_bin_dir, name)
                tgt = os.path.join(target_bin_dir, name)
                if os.path.isfile(src) and (not os.path.isfile(tgt) or os.path.getsize(tgt) != os.path.getsize(src)):
                    shutil.copy2(src, tgt)

            if os.path.isfile(target_adb):
                return target_adb
        except Exception:
            pass

    # 2. Tìm trong binaries/ của app (môi trường phát triển python thường)
    local_bin = os.path.join(get_base_dir(), "binaries", "adb.exe")
    if os.path.isfile(local_bin):
        return local_bin

    # 3. Tìm trong LDPlayer nếu có (giúp đồng bộ 100% phiên bản adb daemon của LDPlayer)
    try:
        for reg_key in [r"SOFTWARE\leidian\ldplayer9", r"SOFTWARE\WOW6432Node\leidian\ldplayer9"]:
            for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(hive, reg_key) as key:
                        install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                        ld_adb = os.path.join(install_dir, "adb.exe")
                        if os.path.isfile(ld_adb):
                            return ld_adb
                except Exception:
                    pass
    except Exception:
        pass

    for drive in ["C", "D", "E", "F"]:
        for candidate in [
            rf"{drive}:\LDPlayer\LDPlayer9\adb.exe",
            rf"{drive}:\LDPlayer\LDPlayer4.0\adb.exe",
            rf"{drive}:\leidian\LDPlayer9\adb.exe",
            rf"{drive}:\Program Files\LDPlayer\LDPlayer9\adb.exe",
            rf"{drive}:\Program Files (x86)\LDPlayer\LDPlayer9\adb.exe",
        ]:
            if os.path.isfile(candidate):
                return candidate

    # 4. Tìm trong BlueStacks_nxt nếu có
    bs_adb = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
    if os.path.isfile(bs_adb):
        return bs_adb

    # 5. Mặc định gọi "adb" từ PATH
    return "adb"


class ADBManager:
    """Quản lý các kết nối ADB tới máy ảo/giả lập Android."""

    def __init__(self, adb_path: Optional[str] = None):
        self.adb_bin = adb_path or find_adb_binary()
        self.active_serial: Optional[str] = None
        self.screen_size: Optional[Tuple[int, int]] = None  # (width, height)
        self.last_error: str = ""

    def run_cmd(self, args: List[str], timeout: float = 5.0) -> Tuple[int, str]:
        """Chạy một lệnh ADB và trả về (exit_code, output).
        Trả về kết hợp cả stdout và stderr để không bao giờ bị nuốt thông báo lỗi từ ADB.
        """
        cmd = [self.adb_bin] + args
        try:
            # CREATE_NO_WINDOW = 0x08000000 để không bật cửa sổ cmd đen
            flags = 0x08000000 if sys.platform.startswith("win") else 0
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=flags,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            out = proc.stdout.strip()
            err = proc.stderr.strip()
            # Kết hợp hoặc ưu tiên thông tin lỗi nếu thất bại
            combined = out if not err else (f"{out}\n{err}".strip() if out else err)
            return proc.returncode, combined
        except subprocess.TimeoutExpired:
            return -1, f"Lệnh ADB bị quá thời gian ({timeout}s)"
        except Exception as e:
            return -1, str(e)

    def scan_bluestacks_ports(self) -> List[Dict[str, str]]:
        """Quét các cổng ADB của BlueStacks 5 từ file bluestacks.conf."""
        found = []
        conf_path = None

        # Đọc UserDefinedDir từ Registry
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\BlueStacks_nxt") as key:
                user_dir, _ = winreg.QueryValueEx(key, "UserDefinedDir")
                test_conf = os.path.join(user_dir, "bluestacks.conf")
                if os.path.isfile(test_conf):
                    conf_path = test_conf
        except Exception:
            pass

        # Thử đường dẫn mặc định nếu không đọc được registry
        if not conf_path:
            for p in [r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf", r"D:\BlueStacks_nxt\bluestacks.conf"]:
                if os.path.isfile(p):
                    conf_path = p
                    break

        if not conf_path or not os.path.isfile(conf_path):
            return found

        try:
            with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Tìm cấu hình của từng instance: bst.instance.<inst>.adb_port="<port>"
            # và display_name
            instance_ports: Dict[str, str] = {}
            instance_names: Dict[str, str] = {}

            for line in content.splitlines():
                m_port = re.match(r'bst\.instance\.([^.]+)\.(?:status\.)?adb_port="(\d+)"', line.strip())
                if m_port:
                    inst_id, port = m_port.group(1), m_port.group(2)
                    instance_ports[inst_id] = port

                m_name = re.match(r'bst\.instance\.([^.]+)\.display_name="([^"]+)"', line.strip())
                if m_name:
                    inst_id, name = m_name.group(1), m_name.group(2)
                    instance_names[inst_id] = name

            for inst_id, port in instance_ports.items():
                name = instance_names.get(inst_id, inst_id)
                found.append({
                    "name": f"BlueStacks - {name}",
                    "port": port,
                    "host": "127.0.0.1",
                    "serial": f"127.0.0.1:{port}",
                })
        except Exception:
            pass

        return found

    def get_candidate_ports(self) -> List[Dict[str, str]]:
        """Lấy danh sách tất cả các cổng giả lập có khả năng đang chạy."""
        candidates = []

        # 1. Quét BlueStacks
        bs_list = self.scan_bluestacks_ports()
        candidates.extend(bs_list)

        # 2. Cổng mặc định của LDPlayer, MuMu, Nox, MEmu
        common_ports = [
            ("LDPlayer", "5555"),
            ("LDPlayer 2", "5557"),
            ("LDPlayer 3", "5559"),
            ("MuMu Player", "7555"),
            ("MuMu Player 12", "16384"),
            ("NoxPlayer", "62001"),
            ("MEmu", "21503"),
        ]
        for name, port in common_ports:
            serial = f"127.0.0.1:{port}"
            if not any(c["serial"] == serial for c in candidates):
                candidates.append({
                    "name": name,
                    "port": port,
                    "host": "127.0.0.1",
                    "serial": serial,
                })

        return candidates

    def get_connected_devices(self) -> List[str]:
        """Lấy danh sách các serial thiết bị đã kết nối thành công và ở trạng thái 'device'."""
        code, out = self.run_cmd(["devices"])
        if code != 0:
            return []

        devices = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def auto_connect(self, emulator_hint: Optional[str] = None) -> Optional[str]:
        """
        Tự động quét và kết nối tới giả lập đang mở.
        Sử dụng TCP socket ping siêu tốc (0.08s) để lọc các cổng thực sự mở,
        kết hợp ưu tiên loại giả lập đang hiển thị để kết nối ngay lập tức (dưới 0.2s),
        tránh bị treo 20-30 giây khi máy có nhiều instance BlueStacks cũ đã tắt.
        """
        # Kiểm tra xem có thiết bị nào đã sẵn sàng chưa
        ready = self.get_connected_devices()
        if ready:
            # Nếu có hint LDPlayer, ưu tiên emulator-5554 hơn 127.0.0.1:5555 nếu cả 2 cùng xuất hiện
            if emulator_hint and any(k in emulator_hint.lower() for k in ["ld", "dn"]):
                ready.sort(key=lambda d: 0 if "emulator" in d else 1)
            self.active_serial = ready[0]
            self.refresh_screen_size()
            return self.active_serial

        import socket

        def _is_port_open(host: str, port: int, timeout: float = 0.08) -> bool:
            try:
                with socket.create_connection((host, int(port)), timeout=timeout):
                    return True
            except Exception:
                return False

        # Thử kết nối lần lượt các candidate ports
        candidates = self.get_candidate_ports()

        # Ưu tiên các cổng tương ứng với loại giả lập đang phát hiện trên màn hình
        if emulator_hint:
            hl = emulator_hint.lower()
            if any(k in hl for k in ["ldplayer", "ld", "dnplayer"]):
                candidates.sort(key=lambda c: 0 if "ld" in c["name"].lower() else 1)
            elif any(k in hl for k in ["mumu", "nemu"]):
                candidates.sort(key=lambda c: 0 if "mumu" in c["name"].lower() else 1)
            elif "nox" in hl:
                candidates.sort(key=lambda c: 0 if "nox" in c["name"].lower() else 1)
            elif "memu" in hl:
                candidates.sort(key=lambda c: 0 if "memu" in c["name"].lower() else 1)
            elif any(k in hl for k in ["blue", "bst"]):
                candidates.sort(key=lambda c: 0 if "blue" in c["name"].lower() else 1)

        for cand in candidates:
            # Bỏ qua ngay các cổng không có dịch vụ nào lắng nghe (tránh bị delay 2.0s mỗi cổng đóng)
            if not _is_port_open(cand["host"], int(cand["port"])):
                continue

            serial = cand["serial"]
            self.run_cmd(["connect", serial], timeout=2.0)
            if serial in self.get_connected_devices():
                self.active_serial = serial
                self.refresh_screen_size()
                return self.active_serial

        return None

    def refresh_screen_size(self) -> Optional[Tuple[int, int]]:
        """
        Lấy độ phân giải nội bộ hiện tại của màn hình Android (Width, Height).
        Ưu tiên lệnh 'wm size' siêu tốc (0.03s) thay vì 'dumpsys window' (mất 3-5s),
        giúp kết nối và quét giả lập hoàn tất ngay lập tức dưới 1 giây.
        """
        if not self.active_serial:
            return None

        # 1. Ưu tiên 'wm size' siêu tốc (chỉ mất ~0.03s)
        code, out = self.run_cmd(["-s", self.active_serial, "shell", "wm", "size"], timeout=1.5)
        if code == 0 and out:
            override_m = re.search(r"Override size:\s*(\d+)x(\d+)", out)
            if override_m:
                self.screen_size = (int(override_m.group(1)), int(override_m.group(2)))
                return self.screen_size
            m = re.search(r"Physical size:\s*(\d+)x(\d+)", out) or re.search(r"(\d+)x(\d+)", out)
            if m:
                self.screen_size = (int(m.group(1)), int(m.group(2)))
                return self.screen_size

        # 2. Dự phòng: dumpsys window displays (nếu wm size không trả kết quả)
        code, out = self.run_cmd(["-s", self.active_serial, "shell", "dumpsys", "window", "displays"], timeout=2.0)
        if code == 0 and out:
            m = re.search(r"cur=(\d+)x(\d+)", out) or re.search(r"app=(\d+)x(\d+)", out)
            if m:
                self.screen_size = (int(m.group(1)), int(m.group(2)))
                return self.screen_size

        # 3. Dự phòng cuối: dumpsys display
        code, out = self.run_cmd(["-s", self.active_serial, "shell", "dumpsys", "display"], timeout=2.0)
        if code == 0 and out:
            m = re.search(r"mCurrentDisplayRect=\w+\[\d+,\d+\]\[(\d+),(\d+)\]", out)
            if m:
                self.screen_size = (int(m.group(1)), int(m.group(2)))
                return self.screen_size

        return None

    def tap(self, x: int, y: int, jitter: bool = True) -> bool:
        """
        Thực hiện click ngầm (tap) vào tọa độ (x, y) trên màn hình Android.
        Mặc định tạo độ lệch ngẫu nhiên nhẹ (±2 pixel) mô phỏng ngón tay người bấm thực tế,
        loại bỏ hoàn toàn nguy cơ bị server game phát hiện việc lặp lại tọa độ chuẩn xác tuyệt đối.
        Tự động fallback qua lệnh su nếu Android/LDPlayer yêu cầu quyền root.
        """
        if not self.active_serial:
            self.last_error = "Chưa kết nối thiết bị ADB"
            return False

        tap_x = int(x)
        tap_y = int(y)
        if jitter:
            import random
            tap_x += random.randint(-2, 2)
            tap_y += random.randint(-2, 2)

        # 1. Thử gửi lệnh input tap tiêu chuẩn
        code, out = self.run_cmd(
            ["-s", self.active_serial, "shell", "input", "tap", str(tap_x), str(tap_y)]
        )
        if code == 0:
            self.last_error = ""
            return True

        # 2. Fallback: Nếu không gửi được, thử với quyền root (su) cho LDPlayer / giả lập bật Root
        code_su, out_su = self.run_cmd(
            ["-s", self.active_serial, "shell", "su", "0", "input", "tap", str(tap_x), str(tap_y)]
        )
        if code_su == 0:
            self.last_error = ""
            return True

        # 3. Fallback 2: Thử su -c
        code_su2, out_su2 = self.run_cmd(
            ["-s", self.active_serial, "shell", f"su -c 'input tap {tap_x} {tap_y}'"]
        )
        if code_su2 == 0:
            self.last_error = ""
            return True

        self.last_error = out or out_su or out_su2 or "Không nhận được phản hồi từ ADB"
        return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Thực hiện vuốt ngầm (swipe) từ (x1, y1) tới (x2, y2)."""
        if not self.active_serial:
            self.last_error = "Chưa kết nối thiết bị ADB"
            return False

        code, out = self.run_cmd(
            [
                "-s",
                self.active_serial,
                "shell",
                "input",
                "swipe",
                str(int(x1)),
                str(int(y1)),
                str(int(x2)),
                str(int(y2)),
                str(int(duration_ms)),
            ]
        )
        if code == 0:
            self.last_error = ""
            return True

        # Fallback qua su
        code_su, out_su = self.run_cmd(
            [
                "-s",
                self.active_serial,
                "shell",
                "su",
                "0",
                "input",
                "swipe",
                str(int(x1)),
                str(int(y1)),
                str(int(x2)),
                str(int(y2)),
                str(int(duration_ms)),
            ]
        )
        if code_su == 0:
            self.last_error = ""
            return True

        self.last_error = out or out_su or "Không nhận được phản hồi từ ADB"
        return False
