import time
import ctypes
from ctypes import wintypes
import threading
import json
import os
import tkinter as tk
from tkinter import ttk
from pynput import mouse, keyboard
from typing import Callable, Optional

# ==============================================================================
# 1. DÜŞÜK SEVİYE WIN32 API (SendInput C-Structures & Native Memory Layout)
# ==============================================================================
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION)
    ]

class Win32InputInjector:
    """Windows Native API kullanarak düşük gecikmeli vektör enjeksiyonu sağlar."""
    @staticmethod
    def inject_vector(dx: int, dy: int) -> None:
        if dx == 0 and dy == 0:
            return
        extra = ctypes.c_ulong(0)
        ii_ = INPUT_UNION()
        ii_.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, ctypes.pointer(extra))
        command = INPUT(INPUT_MOUSE, ii_)
        ctypes.windll.user32.SendInput(1, ctypes.byref(command), ctypes.sizeof(command))


# ==============================================================================
# 2. AKILLI DİKEY BASKI VE YATAY EKSEN FİLTRELEME MOTORU (RecoilEngine)
# ==============================================================================
class RecoilEngine:
    CONFIG_FILE = "recoil_config.json"

    def __init__(self, ui_callback: Callable[[bool, str], None]):
        self.ui_callback = ui_callback
        self.lock = threading.Lock()
        
        self.is_active: bool = False
        self.is_firing: bool = False
        self.running: bool = True
        
        # Dürbün profilleri: dy (dikey baskı), ms (hız)
        self.profiles = {
            "1x": {"name": "Red Dot / 1x", "dy": 4, "ms": 12},
            "2x": {"name": "2x Dürbün", "dy": 7, "ms": 11},
            "3x": {"name": "3x Dürbün", "dy": 11, "ms": 10},
            "4x": {"name": "4x Dürbün", "dy": 15, "ms": 9}
        }
        self.current_profile: str = "1x"
        self.ramp_up: bool = True

        self.load_config()

        self.mouse_listener = mouse.Listener(on_click=self._on_click)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self.worker_thread = threading.Thread(target=self._loop, daemon=True)

    def load_config(self) -> None:
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "profiles" in data:
                        self.profiles.update(data["profiles"])
                    if "current_profile" in data:
                        self.current_profile = data["current_profile"]
                    if "ramp_up" in data:
                        self.ramp_up = data["ramp_up"]
            except Exception as e:
                print(f"[Uyarı] Konfigürasyon yüklenemedi: {e}")

    def save_config(self) -> None:
        with self.lock:
            data = {
                "profiles": self.profiles,
                "current_profile": self.current_profile,
                "ramp_up": self.ramp_up
            }
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Hata] Konfigürasyon kaydedilemedi: {e}")

    def start_services(self) -> None:
        self.mouse_listener.start()
        self.keyboard_listener.start()
        self.worker_thread.start()

    def stop_services(self) -> None:
        self.running = False
        try:
            self.mouse_listener.stop()
            self.keyboard_listener.stop()
        except Exception:
            pass

    def toggle_active(self, force_state: Optional[bool] = None) -> None:
        with self.lock:
            if force_state is not None:
                self.is_active = force_state
            else:
                self.is_active = not self.is_active
            active_status = self.is_active
            profile = self.current_profile
        self.ui_callback(active_status, profile)

    def set_profile(self, profile_key: str) -> None:
        with self.lock:
            if profile_key in self.profiles:
                self.current_profile = profile_key
                active_status = self.is_active
        self.save_config()
        self.ui_callback(active_status, profile_key)

    def update_custom_params(self, dy: int, interval_ms: int, ramp_up: bool) -> None:
        with self.lock:
            self.ramp_up = ramp_up
            if self.current_profile in self.profiles:
                self.profiles[self.current_profile]["dy"] = dy
                self.profiles[self.current_profile]["ms"] = interval_ms
        self.save_config()

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if button == mouse.Button.left:
            with self.lock:
                self.is_firing = pressed

    def _on_key_press(self, key) -> None:
        try:
            if hasattr(key, 'char'):
                if key.char in ['1', '2']:
                    self.toggle_active(True)
                elif key.char in ['4', '5']:
                    self.toggle_active(False)

            if key == keyboard.Key.f6:
                self.toggle_active()
            elif key == keyboard.Key.f1:
                self.set_profile("1x")
            elif key == keyboard.Key.f2:
                self.set_profile("2x")
            elif key == keyboard.Key.f3:
                self.set_profile("3x")
            elif key == keyboard.Key.f4:
                self.set_profile("4x")
        except AttributeError:
            pass

    def _loop(self) -> None:
        """Yüksek hassasiyetli zamanlayıcı ve yatay eksen filtreleme motoru."""
        shot_ticks = 0
        while self.running:
            with self.lock:
                active = self.is_active
                firing = self.is_firing
                prof = self.current_profile
                dy_val = self.profiles[prof]["dy"]
                delay_sec = self.profiles[prof]["ms"] / 1000.0
                use_ramp = self.ramp_up

            if active and firing:
                shot_ticks += 1
                if use_ramp and shot_ticks < 8:
                    applied_dy = max(1, int(dy_val * 0.7))
                else:
                    applied_dy = dy_val

                # Yatay eksen (dx) tamamen sıfıra kilitlenir, silahın sağa sola 
                # istemsiz sekmesi donanımsal olarak filtrelenip engellenir.
                applied_dx = 0

                Win32InputInjector.inject_vector(applied_dx, applied_dy)
                
                target_time = time.perf_counter() + delay_sec
                while time.perf_counter() < target_time:
                    if not self.running:
                        break
                    time.sleep(0.0005)
            else:
                shot_ticks = 0
                time.sleep(0.005)


# ==============================================================================
# 3. MODERN GRAFİK ARAYÜZ (GUI Kontrol Paneli)
# ==============================================================================
class ControlPanelApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Win32 Axis-Lock Stabilizer v8.3 [Laser Lock]")
        self.root.geometry("420x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        self.engine = RecoilEngine(self.update_status_ui)
        self._build_ui()
        self.init_ui_values()
        self.engine.start_services()

    def _build_ui(self) -> None:
        header = tk.Label(
            self.root, text="EKSEN KİLİTLİ LAZER KONTROLÜ",
            font=("Segoe UI", 12, "bold"), bg="#1e1e2e", fg="#cdd6f4"
        )
        header.pack(pady=(12, 2))

        sub_header = tk.Label(
            self.root, text="[1/2]: Aç | [4/5]: Kapat | [F6]: Toggle\n[F1]-[F4]: Dürbün Profilleri (Axis-Lock Active)",
            font=("Segoe UI", 8, "bold"), bg="#1e1e2e", fg="#89b4fa", justify="center"
        )
        sub_header.pack(pady=(0, 6))

        self.status_frame = tk.Frame(self.root, bg="#313244", padx=15, pady=6)
        self.status_frame.pack(fill="x", padx=20, pady=4)

        self.status_lbl = tk.Label(
            self.status_frame, text="DURUM: DEVRE DIŞI",
            font=("Segoe UI", 9, "bold"), bg="#313244", fg="#f38ba8"
        )
        self.status_lbl.pack()

        scope_frame = tk.LabelFrame(
            self.root, text=" Dürbün Profilleri ",
            font=("Segoe UI", 9, "bold"), bg="#1e1e2e", fg="#89b4fa", padx=10, pady=6
        )
        scope_frame.pack(fill="x", padx=20, pady=6)

        self.btn_1x = tk.Button(scope_frame, text="[F1] 1x Red Dot", bg="#45475a", fg="white", relief="flat", width=10, command=lambda: self.engine.set_profile("1x"))
        self.btn_1x.pack(side="left", padx=3)
        
        self.btn_2x = tk.Button(scope_frame, text="[F2] 2x Dürbün", bg="#45475a", fg="white", relief="flat", width=10, command=lambda: self.engine.set_profile("2x"))
        self.btn_2x.pack(side="left", padx=3)
        
        self.btn_3x = tk.Button(scope_frame, text="[F3] 3x Dürbün", bg="#45475a", fg="white", relief="flat", width=10, command=lambda: self.engine.set_profile("3x"))
        self.btn_3x.pack(side="left", padx=3)
        
        self.btn_4x = tk.Button(scope_frame, text="[F4] 4x Dürbün", bg="#45475a", fg="white", relief="flat", width=10, command=lambda: self.engine.set_profile("4x"))
        self.btn_4x.pack(side="left", padx=3)

        ctrl_frame = tk.LabelFrame(
            self.root, text=" Seçili Dürbün İnce Ayarı ",
            font=("Segoe UI", 9, "bold"), bg="#1e1e2e", fg="#89b4fa", padx=10, pady=6
        )
        ctrl_frame.pack(fill="x", padx=20, pady=4)

        # Dikey Baskı (DY)
        self.dy_var = tk.IntVar(value=4)
        self.dy_lbl = tk.Label(ctrl_frame, text="Dikey Baskı (DY): 4 px", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 9))
        self.dy_lbl.pack(anchor="w")
        self.dy_slider = ttk.Scale(ctrl_frame, from_=1, to=30, variable=self.dy_var, command=self._on_slider_change)
        self.dy_slider.pack(fill="x", pady=(0, 6))

        # Enjeksiyon Aralığı (MS - Hız)
        self.ms_var = tk.IntVar(value=12)
        self.ms_lbl = tk.Label(ctrl_frame, text="Enjeksiyon Aralığı (Hız): 12 ms", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 9))
        self.ms_lbl.pack(anchor="w")
        self.ms_slider = ttk.Scale(ctrl_frame, from_=5, to=30, variable=self.ms_var, command=self._on_slider_change)
        self.ms_slider.pack(fill="x", pady=(0, 6))

        self.ramp_var = tk.BooleanVar(value=True)
        self.ramp_chk = tk.Checkbutton(
            ctrl_frame, text="Kademeli Başlangıç Algoritması (Ramp-Up)",
            variable=self.ramp_var, command=self._on_slider_change,
            bg="#1e1e2e", fg="#a6adc8", selectcolor="#313244", activebackground="#1e1e2e"
        )
        self.ramp_chk.pack(anchor="w")

        btn_frame = tk.Frame(self.root, bg="#1e1e2e")
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame, text="SİSTEMİ AÇ (1/2)", font=("Segoe UI", 9, "bold"),
            bg="#a6e3a1", fg="#11111b", width=14, pady=4, relief="flat",
            command=lambda: self.engine.toggle_active(True)
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame, text="KAPAT (4/5)", font=("Segoe UI", 9, "bold"),
            bg="#f38ba8", fg="#11111b", width=14, pady=4, relief="flat",
            command=lambda: self.engine.toggle_active(False)
        ).pack(side="left", padx=5)

    def init_ui_values(self) -> None:
        prof = self.engine.current_profile
        p_data = self.engine.profiles[prof]
        self.dy_var.set(p_data["dy"])
        self.ms_var.set(p_data["ms"])
        self.ramp_var.set(self.engine.ramp_up)
        self.update_status_ui(self.engine.is_active, prof)

    def _on_slider_change(self, _=None) -> None:
        dy = int(self.dy_var.get())
        ms = int(self.ms_var.get())
        ramp = self.ramp_var.get()

        self.dy_lbl.config(text=f"Dikey Baskı (DY): {dy} px")
        self.ms_lbl.config(text=f"Enjeksiyon Aralığı (Hız): {ms} ms")
        self.engine.update_custom_params(dy, ms, ramp)

    def update_status_ui(self, active: bool, profile_key: str) -> None:
        def _update():
            p_data = self.engine.profiles[profile_key]
            self.dy_var.set(p_data["dy"])
            self.ms_var.set(p_data["ms"])
            
            self.dy_lbl.config(text=f"Dikey Baskı (DY): {p_data['dy']} px")
            self.ms_lbl.config(text=f"Enjeksiyon Aralığı (Hız): {p_data['ms']} ms")

            for key, btn in [("1x", self.btn_1x), ("2x", self.btn_2x), ("3x", self.btn_3x), ("4x", self.btn_4x)]:
                if key == profile_key:
                    btn.config(bg="#89b4fa", fg="#11111b")
                else:
                    btn.config(bg="#45475a", fg="white")

            p_name = p_data["name"]
            if active:
                self.status_lbl.config(text=f"DURUM: AKTİF | Dürbün: {p_name}", fg="#a6e3a1")
            else:
                self.status_lbl.config(text=f"DURUM: DEVRE DIŞI | Dürbün: {p_name}", fg="#f38ba8")

        self.root.after(0, _update)

    def on_close(self) -> None:
        """Pencere kapatıldığında arka plan servislerini ve dinleyicileri güvenle durdurur."""
        self.engine.stop_services()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ControlPanelApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()