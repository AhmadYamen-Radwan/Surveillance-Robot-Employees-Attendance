import tkinter as tk
import subprocess
import re
import socket
import threading
import time
import requests
import asyncio
import websocket
import cv2
import numpy as np

from cv2 import cvtColor, COLOR_BGR2RGB
from PIL import ImageTk, Image
from recognition_engine_v1_0_1 import Engine
from send_command import ESP32CAMController

class FaceRecognitionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Face Recognition Employee Attendance")
        self.discovered_cameras = {}
        self.camera_list = ["Local"]
        self.scanning = False
        self.scan_thread = None
        self.current_source = "Local"
        self.command_handler = None

        self.create_widgets()

        # Start the engine (default to local)
        self.engine = Engine()

        # Start UDP listener for ESP32-CAM broadcasts
        self.start_udp_listener()

        # Start periodic network scan
        self.start_network_scan()

        # Polling loop
        self.update_frame()
        self.update_discovery()
        # Start periodic refresh of unknown faces
        self.root.after(500, self.refresh_unknown_display)
        # Start periodic refresh of attendance log
        self.root.after(1000, self.update_attendance)

        # Cleanup on close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def connect_websocket(self, ip):
        """
            Connect to ESP32-CAM WebSocket for faster streaming
        """

        self.ws_url = f"ws://{ip}:81"
        self.ws_connected = False

        def ws_listener():
            try:
                ws = websocket.WebSocket()
                ws.connect(self.ws_url)
                self.ws_connected = True
                print(f"[WS] Connected to {self.ws_url}")

                while self.ws_connected:
                    try:
                        data = ws.recv()
                        if data:
                            # Convert binary to image
                            nparr = np.frombuffer(data, np.uint8)
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if img is not None:
                                self.engine.current_frame = img
                    except:
                        break
            except Exception as e:
                print(f"[WS] Error: {e}")
                self.ws_connected = False

        threading.Thread(target=ws_listener, daemon=True).start()
    
    def create_widgets(self):
        self.camera_frame = tk.Frame(self.root)
        self.camera_frame.place(x=2, y=40, width=800, height=550)

        self.video_label = tk.Label(self.camera_frame)
        self.video_label.pack()

        self.end_buttons_frames = tk.Frame(self.root)
        self.end_buttons_frames.place(x=190, y=600, width=350, height=80)

        self.end_buttons_frames.grid_columnconfigure(0, weight=1)
        self.end_buttons_frames.grid_columnconfigure(1, weight=1)
        self.end_buttons_frames.grid_rowconfigure(0, weight = 1)
        self.end_buttons_frames.grid_rowconfigure(1, weight = 1)

        self.start_btn = tk.Button(self.end_buttons_frames, text="Start", width=40, relief="flat", bg="#C0C0C0", command=self.start_btn_command)
        self.start_btn.grid(row=0, column=0, padx=5, pady=5)

        self.stop_btn = tk.Button(self.end_buttons_frames, text="Stop", width=40, relief="flat", bg="#C0C0C0", command=self.stop_btn_command)
        self.stop_btn.grid(row=0, column=1, padx=5, pady=5)

        self.start_robot = tk.Button(self.end_buttons_frames, text = "Start Robot", width = 40, relief = "flat", bg = "#C0C0C0", command = self.start_rbt_command)
        self.start_robot.grid(row = 1, column = 0, padx = 5, pady = 5)

        self.stop_robot = tk.Button(self.end_buttons_frames, text = "Stop Robot", width = 40, relief = "flat", bg = "#C0C0C0", command = self.stop_rbt_command)
        self.stop_robot.grid(row = 1, column = 1, padx = 5, pady = 5)

        self.disco_label = tk.Label(self.root, text="Discovered Faces", bg="#C0C0C0")
        self.disco_label.place(x=820, y=20)

        self.disco_frame = tk.Frame(self.root)
        self.disco_frame.place(x=820, y=40, width=200, height=130)

        self.disco_text_box = tk.Text(self.disco_frame)
        self.disco_text_box.pack()

        self.source_frame = tk.Frame(self.root)
        self.source_frame.place(x=2, y=2, width=800, height=35)

        self.source_label = tk.Label(self.source_frame, text="Camera Source:")
        self.source_label.grid(row=0, column=0, padx=5, pady=5)

        self.source_string = tk.StringVar(value="Local")
        self.source_menu = tk.OptionMenu(self.source_frame, self.source_string, *self.camera_list, command=self.on_source_change)
        self.source_menu.grid(row=0, column=1, padx=5, pady=5)

        # Status label
        self.status_label = tk.Label(self.source_frame, text="", fg="blue")
        self.status_label.grid(row=0, column=2, padx=10, pady=5)

        # Scan button
        self.scan_btn = tk.Button(self.source_frame, text="Scan Network", command=self.scan_network_manual)
        self.scan_btn.grid(row=0, column=3, padx=5, pady=5)

        # Remote URL entry 
        self.url_label = tk.Label(self.source_frame, text="Custom URL:")
        self.url_label.grid(row=0, column=4, padx=5, pady=5)

        self.url_entry = tk.Entry(self.source_frame, width=30)
        self.url_entry.grid(row=0, column=5, padx=5, pady=5)

        self.connect_btn = tk.Button(self.source_frame, text="Connect", command=self.connect_custom_url)
        self.connect_btn.grid(row=0, column=6, padx=5, pady=5)

        self.unknown_label = tk.Label(self.root, text="Unknown Profiles", bg="#C0C0C0")
        self.unknown_label.place(x=820, y=180)

        self.unknown_frame = tk.Frame(self.root)
        self.unknown_frame.place(x=820, y=200, width=280, height=230)

        # Canvas, Scrollbar for unknown faces
        self.unknown_canvas = tk.Canvas(self.unknown_frame, highlightthickness=0)
        self.unknown_scrollbar = tk.Scrollbar(self.unknown_frame, orient="vertical", command=self.unknown_canvas.yview)
        self.unknown_canvas.configure(yscrollcommand=self.unknown_scrollbar.set)

        self.unknown_canvas.pack(side="left", fill="both", expand=True)
        self.unknown_scrollbar.pack(side="right", fill="y")

        # Inner frame that holds the thumbnail grid
        self.unknown_inner = tk.Frame(self.unknown_canvas)
        self.unknown_canvas.create_window((0, 0), window=self.unknown_inner, anchor="nw")

        # Update scroll region when inner frame changes size
        self.unknown_inner.bind("<Configure>", self._on_unknown_inner_configure)

        # Store references to PhotoImage objects to prevent garbage collection
        self.unknown_thumb_refs = []

        # Command buttons for ESP32
        self.command_label = tk.Label(self.root, text="ESP32-CAM Commands", bg="#C0C0C0", font=("Arial", 10, "bold"))
        self.command_label.place(x=820, y=445)

        self.command_frame = tk.Frame(self.root)
        self.command_frame.place(x=820, y=465, width=280, height=60)

        self.led_on_btn = tk.Button(self.command_frame, text="LED ON", width=10, 
                                   command=self.send_led_on, bg="#FFD700", font=("Arial", 9, "bold"))
        self.led_on_btn.grid(row=0, column=0, padx=5, pady=5)

        self.led_off_btn = tk.Button(self.command_frame, text="LED OFF", width=10, 
                                    command=self.send_led_off, bg="#FFD700", font=("Arial", 9, "bold"))
        self.led_off_btn.grid(row=0, column=1, padx=5, pady=5)

        self.status_btn = tk.Button(self.command_frame, text="Status", width=10, 
                                   command=self.send_status, bg="#87CEEB", font=("Arial", 9, "bold"))
        self.status_btn.grid(row=0, column=2, padx=5, pady=5)

        # Attendance Panel
        self.attendance_label = tk.Label(self.root, text="Attendance Log (Today)", bg="#90EE90", font=("Arial", 10, "bold"))
        self.attendance_label.place(x=1120, y=20)

        self.present_label = tk.Label(self.root, text="Present: 0", bg="#E0FFE0", font=("Arial", 9))
        self.present_label.place(x=1120, y=40)

        self.attendance_frame = tk.Frame(self.root)
        self.attendance_frame.place(x=1120, y=60, width=230, height=580)

        self.attendance_text = tk.Text(self.attendance_frame, wrap="word", font=("Courier", 9))
        self.attendance_text.pack(side="left", fill="both", expand=True)

        self.attendance_scroll = tk.Scrollbar(self.attendance_frame, command=self.attendance_text.yview)
        self.attendance_scroll.pack(side="right", fill="y")
        self.attendance_text.config(yscrollcommand=self.attendance_scroll.set)

        self.attendance_btn_frame = tk.Frame(self.root)
        self.attendance_btn_frame.place(x=1120, y=650, width=230, height=30)

        self.export_btn = tk.Button(self.attendance_btn_frame, text="Export CSV", command=self.export_attendance, bg="#4CAF50", fg="white")
        self.export_btn.pack(side="left", padx=5)

        self.refresh_attendance_btn = tk.Button(self.attendance_btn_frame, text="Refresh", command=self.update_attendance)
        self.refresh_attendance_btn.pack(side="left", padx=5)

    def _on_unknown_inner_configure(self, event=None):
        """
            Update canvas scroll region when inner frame size changes.
        """
        self.unknown_canvas.configure(scrollregion=self.unknown_canvas.bbox("all"))

    def refresh_unknown_display(self):
        """
            Refresh the grid of unknown face thumbnails
        """
        # Clear existing thumbnails
        for widget in self.unknown_inner.winfo_children():
            widget.destroy()
        self.unknown_thumb_refs.clear()

        unknown_list = self.engine.get_unknown_profiles_safe()  # safe copy

        if not unknown_list:
            self.root.after(500, self.refresh_unknown_display)
            return

        thumb_size = 70
        cols = 3
        padx, pady = 3, 3

        for idx, profile in enumerate(unknown_list):
            try:
                face_crop = profile.face_crop
                if face_crop is None or face_crop.size == 0:
                    continue

                rgb_img = cvtColor(face_crop, COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_img)
                pil_img.thumbnail((thumb_size, thumb_size))
                photo = ImageTk.PhotoImage(pil_img)
                self.unknown_thumb_refs.append(photo)

                # Create a frame for each thumbnail
                frame = tk.Frame(self.unknown_inner, relief="solid", borderwidth=1)
                frame.grid(row=idx // cols, column=idx % cols, padx=padx, pady=pady, sticky="nsew")

                lbl_img = tk.Label(frame, image=photo)
                lbl_img.pack()

                # ID label
                id_label = tk.Label(frame, text=f"ID:{profile.face_id}", font=("Arial", 7))
                id_label.pack()

                frame.bind("<Button-3>", lambda e, pid=profile.face_id: self._show_unknown_context_menu(e, pid))
                lbl_img.bind("<Button-3>", lambda e, pid=profile.face_id: self._show_unknown_context_menu(e, pid))
                id_label.bind("<Button-3>", lambda e, pid=profile.face_id: self._show_unknown_context_menu(e, pid))

            except Exception as e:
                print(f"[GUI] Error displaying unknown face: {e}")

        # Configure columns
        for c in range(cols):
            self.unknown_inner.grid_columnconfigure(c, weight=1)

        self.root.after(500, self.refresh_unknown_display)

    def _show_unknown_context_menu(self, event, profile_id):
        """
            Show popup menu for unknown face actions.
        """
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Delete", command=lambda: self._delete_unknown(profile_id))
        menu.add_command(label="Label as Known...", command=lambda: self._prompt_label_unknown(profile_id))
        menu.post(event.x_root, event.y_root)

    def _delete_unknown(self, profile_id):
        """
            Delete an unknown face profile.
        """
        if self.engine.delete_unknown_profile(profile_id):
            self.status_label.config(text=f"Deleted unknown ID {profile_id}", fg="orange")
        else:
            self.status_label.config(text=f"Failed to delete ID {profile_id}", fg="red")
        self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))

    def _prompt_label_unknown(self, profile_id):
        """
            Ask for a name and convert unknown to known.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Label Unknown Face")
        dialog.geometry("300x150")
        tk.Label(dialog, text="Enter name for this person:").pack(pady=5)
        entry = tk.Entry(dialog)
        entry.pack(pady=5)
        
        feedback_label = tk.Label(dialog, text="", fg="red")
        feedback_label.pack(pady=2)
        
        def submit():
            name = entry.get().strip()
            if name:
                # Check if name already exists in known profiles
                exists = False
                if hasattr(self.engine, 'known_profiles'):
                    for profile in self.engine.known_profiles:
                        if profile.face_name.lower() == name.lower():
                            exists = True
                            break
                    if not exists and hasattr(self.engine, 'labels'):
                        for label in self.engine.labels:
                            if label.lower() == name.lower():
                                exists = True
                                break
                
                if exists:
                    feedback_label.config(text=f"'{name}' already exists in database!", fg="red")
                    return
                
                if self.engine.convert_unknown_to_known(profile_id, name):
                    self.status_label.config(text=f"Added {name} to known faces", fg="green")
                    # Refresh the discovery display
                    self.update_discovery()
                    # Refresh attendance display
                    self.update_attendance()
                    dialog.destroy()
                else:
                    self.status_label.config(text="Failed to convert", fg="red")
                    dialog.destroy()
                self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            else:
                feedback_label.config(text="Please enter a name", fg="red")
        
        def on_enter(event):
            submit()
        
        entry.bind('<Return>', on_enter)
        tk.Button(dialog, text="Confirm", command=submit).pack(pady=5)

    def start_udp_listener(self):
        """
            Start a UDP listener to receive ESP32-CAM broadcasts on port 9999
        """
        def udp_listener():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(('', 9999))
            sock.settimeout(1.0)

            while self.scanning:
                try:
                    data, addr = sock.recvfrom(1024)
                    message = data.decode('utf-8')
                    if '|' in message:
                        hostname, ip = message.split('|')
                        display_name = f"{hostname} ({ip})"
                        url = f"http://{ip}/videostream"
                        if display_name not in self.discovered_cameras:
                            self.discovered_cameras[display_name] = url
                            self.update_camera_menu()
                            print(f"[DISCOVERED] {hostname} at {ip}")
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[UDP ERROR] {e}")
            sock.close()

        self.scanning = True
        self.udp_thread = threading.Thread(target=udp_listener, daemon=True)
        self.udp_thread.start()

    def start_network_scan(self):
        """
            Periodically check for ESP32-CAMs via ARP
        """
        def scan_loop():
            while self.scanning:
                self.scan_network()
                time.sleep(30)  # Scan every 30 seconds

        self.scan_thread = threading.Thread(target=scan_loop, daemon=True)
        self.scan_thread.start()

    def scan_network(self):
        """
            Scan network for ESP32-CAM devices
        """
        try:
            try:
                mdns_ip = socket.gethostbyname('esp32cam.local')
                display_name = f"esp32cam ({mdns_ip})"
                url = f"http://{mdns_ip}/videostream"
                if display_name not in self.discovered_cameras:
                    self.discovered_cameras[display_name] = url
                    self.update_camera_menu()
                    print(f"[mDNS] Found esp32cam at {mdns_ip}")
            except:
                pass

            # ARP scan to find devices
            result = subprocess.run(['arp', '-n'], capture_output=True, text=True)
            lines = result.stdout.splitlines()

            for line in lines:
                # Look for IP addresses in ARP table
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if match:
                    ip = match.group(1)
                    # Try to resolve hostname
                    try:
                        hostname = socket.gethostbyaddr(ip)[0]
                        if 'esp32' in hostname.lower():
                            display_name = f"{hostname} ({ip})"
                            url = f"http://{ip}/videostream"
                            if display_name not in self.discovered_cameras:
                                self.discovered_cameras[display_name] = url
                                self.update_camera_menu()
                                print(f"[ARP] Found {hostname} at {ip}")
                    except:
                        pass

        except Exception as e:
            print(f"[SCAN ERROR] {e}")

    def scan_network_manual(self):
        """
            Manual network scan triggered by button
        """
        self.status_label.config(text="Scanning network...", fg="orange")
        self.status_label.update()

        def scan():
            # Clear old discoveries
            self.discovered_cameras.clear()

            self.scan_network()

            # Try ping common ESP32-CAM IPs
            common_ips = ['192.168.1.100', '192.168.1.101', '192.168.0.100', '192.168.0.101']
            for ip in common_ips:
                response = subprocess.run(['ping', '-c', '1', '-W', '1', ip], capture_output=True)
                if response.returncode == 0:
                    display_name = f"esp32cam ({ip})"
                    url = f"http://{ip}/videostream"
                    if display_name not in self.discovered_cameras:
                        self.discovered_cameras[display_name] = url
                        self.update_camera_menu()
                        print(f"[MANUAL] Found device at {ip}")

            self.root.after(0, lambda: self.status_label.config(text="Scan complete", fg="green"))
            self.root.after(3000, lambda: self.status_label.config(text="", fg="blue"))

        threading.Thread(target=scan, daemon=True).start()

    def update_camera_menu(self):
        """
            Update the option menu with discovered cameras
        """
        # Rebuild menu with current discovered cameras
        menu = self.source_menu['menu']
        menu.delete(0, 'end')

        self.camera_list = ["Local"]
        for display_name in self.discovered_cameras.keys():
            self.camera_list.append(display_name)

        for option in self.camera_list:
            menu.add_command(label=option, command=lambda value=option: self.source_string.set(value))

        # Keep current selection if still valid
        current = self.source_string.get()
        if current not in self.camera_list:
            self.source_string.set("Local")

    def on_source_change(self, selected):
        """
            Handle camera source selection change,
            connects immediately
        """
        if not selected or selected == self.current_source:
            return

        self.current_source = selected
        self.status_label.config(text=f"Connecting to {selected}...", fg="orange")
        self.status_label.update()

        if selected == "Local":
            # Stop and restart engine with local source
            def switch():
                if self.engine.is_running():
                    self.engine.stop()
                    time.sleep(0.5)
                self.engine.start(source="local")
                self.root.after(0, lambda: self.status_label.config(text="Using local camera", fg="green"))
                self.root.after(3000, lambda: self.status_label.config(text="", fg="blue"))
            threading.Thread(target=switch, daemon=True).start()
        else:
            # Get URL from discovered cameras
            url = self.discovered_cameras.get(selected)
            if url:
                # Initialize command handler
                try:
                    ip = url.split('/')[2].split(':')[0]
                    self.command_handler = ESP32CAMController(ip)
                    print(f"[GUI] Command handler initialized for {ip}")
                except Exception as e:
                    print(f"[GUI] Error initializing command handler: {e}")

                def switch():
                    if self.engine.is_running():
                        self.engine.stop()
                        time.sleep(0.5)
                    self.engine.start(source="remote", url=url)
                    self.root.after(0, lambda: self.status_label.config(text=f"Connected to {selected}", fg="green"))
                    self.root.after(3000, lambda: self.status_label.config(text="", fg="blue"))
                threading.Thread(target=switch, daemon=True).start()
            else:
                self.status_label.config(text="Connection failed: No URL found", fg="red")
                self.root.after(3000, lambda: self.status_label.config(text="", fg="blue"))

    def connect_custom_url(self):
        """
            Connect to custom streaming URL
        """
        url = self.url_entry.get().strip()
        if url:
            self.status_label.config(text=f"Connecting to custom URL...", fg="orange")
            self.current_source = url

            # Initialize command handler
            try:
                ip = url.split('/')[2].split(':')[0]
                self.command_handler = ESP32CAMController(ip)
                print(f"[GUI] Command handler initialized for {ip}")
            except Exception as e:
                print(f"[GUI] Error initializing command handler: {e}")

            def switch():
                if self.engine.is_running():
                    self.engine.stop()
                    time.sleep(0.5)
                self.engine.start(source="remote", url=url)
                self.root.after(0, lambda: self.status_label.config(text="Connected to custom source", fg="green"))
                self.root.after(3000, lambda: self.status_label.config(text="", fg="blue"))

            threading.Thread(target=switch, daemon=True).start()

            # Add to discovered Text Box
            display_name = f"custom ({url})"
            if display_name not in self.discovered_cameras:
                self.discovered_cameras[display_name] = url
                self.update_camera_menu()
        else:
            self.status_label.config(text="Please enter a URL", fg="red")
            self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))

    def update_frame(self):
        """
            Get the latest overlayed frame and display it.
        """
        pil_img = self.engine.get_overlayed_frame_as_pil()
        if pil_img is not None:
            # Resize to fit the window
            pil_img = pil_img.resize((800, 550))
            imgtk = ImageTk.PhotoImage(image=pil_img)
            self.video_label.config(image=imgtk)
            self.video_label.image = imgtk # for keeping reference
        self.root.after(30, self.update_frame) # 30 fps

    def update_discovery(self):
        """
            Update discovered faces display
        """
        if hasattr(self.engine, 'known_profiles') and self.engine.known_profiles:
            self.disco_text_box.delete('1.0', tk.END)
            for profile in self.engine.known_profiles:
                self.disco_text_box.insert(tk.END, profile.face_name + '\n')
        self.root.after(1000, self.update_discovery)

    def update_attendance(self):
        """
            Update the attendance log display with today's records.
        """
        if self.engine and self.engine.attendance:
            records = self.engine.attendance.get_today_records()
            present = self.engine.attendance.get_present_employees()

            self.present_label.config(text=f"Present: {len(present)}")

            self.attendance_text.config(state='normal')
            self.attendance_text.delete('1.0', tk.END)

            if not records:
                self.attendance_text.insert(tk.END, "No attendance records today.\n")
            else:
                self.attendance_text.insert(tk.END, f"{'Name':<12} {'In':<9} {'Out':<9} {'Duration'}\n")
                self.attendance_text.insert(tk.END, "-" * 32 + "\n")
                for rec in records:
                    name = rec['name'][:12]
                    check_in = rec['check_in']
                    check_out = rec.get('check_out', '---')
                    duration = rec.get('duration_seconds', 0)
                    if check_out is None:
                        check_out = "PRESENT"
                        duration_str = ""
                    else:
                        hours = duration // 3600
                        minutes = (duration % 3600) // 60
                        secs = duration % 60
                        duration_str = f"{hours:02d}:{minutes:02d}:{secs:02d}"
                    self.attendance_text.insert(tk.END, f"{name:<12} {check_in:<9} {check_out:<9} {duration_str}\n")

            self.attendance_text.config(state='disabled')

        self.root.after(2000, self.update_attendance)

    def export_attendance(self):
        """
            Export attendance records to CSV.
        """
        if self.engine and self.engine.attendance:
            try:
                filepath = self.engine.attendance.export_to_csv()
                self.status_label.config(text=f"Exported to {filepath}", fg="green")
                print(f"[ATTENDANCE] Exported to {filepath}")
            except Exception as e:
                self.status_label.config(text=f"Export failed: {e}", fg="red")
                print(f"[ATTENDANCE] Export error: {e}")
        else:
            self.status_label.config(text="Attendance tracker not available", fg="red")
        self.root.after(3000, lambda: self.status_label.config(text="", fg="blue"))

    def send_led_on(self):
        """
            Send LED ON command to ESP32-CAM
        """
        if self.command_handler:
            try:
                response = self.command_handler.send_command("led_on")
                self.status_label.config(text=f"LED ON: {response}", fg="green")
                self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="red")
        else:
            self.status_label.config(text="No camera connected", fg="red")

    def send_led_off(self):
        """
            Send LED OFF command to ESP32-CAM
        """
        if self.command_handler:
            try:
                response = self.command_handler.send_command("led_off")
                self.status_label.config(text=f"LED OFF: {response}", fg="green")
                self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="red")
        else:
            self.status_label.config(text="No camera connected", fg="red")

    def send_status(self):
        """
            Send STATUS command to ESP32-CAM
        """
        if self.command_handler:
            try:
                response = self.command_handler.send_command("status")
                self.status_label.config(text=f"Status: {response}", fg="green")
                self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="red")
        else:
            self.status_label.config(text="No camera connected", fg="red")

    def start_rbt_command(self):
        """
            Start robot command
        """
        if self.command_handler:
            try:
                response = self.command_handler.send_command("run")
                self.status_label.config(text=f"Robot started: {response}", fg="green")
                self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="red")
        else:
            self.status_label.config(text="No camera connected", fg="red")

    def stop_rbt_command(self):
        """
            Stop robot command
        """
        if self.command_handler:
            try:
                response = self.command_handler.send_command("stop")
                self.status_label.config(text=f"Robot stopped: {response}", fg="green")
                self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="red")
        else:
            self.status_label.config(text="No camera connected", fg="red")

    def start_btn_command(self):
        """
            Start the face recognition engine
        """
        if self.engine.is_running():
            self.status_label.config(text="Engine already running", fg="orange")
            self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            return

        # Get current source selection
        selected = self.source_string.get()

        if selected == "Local":
            self.engine.start(source="local")
            self.status_label.config(text="Started with local camera", fg="green")
        else:
            url = self.discovered_cameras.get(selected)
            if url:
                # Initialize command handler if not already done
                if not self.command_handler:
                    try:
                        ip = url.split('/')[2].split(':')[0]
                        self.command_handler = ESP32CAMController(ip)
                    except Exception as e:
                        print(f"[GUI] Error initializing command handler: {e}")

                self.engine.start(source="remote", url=url)
                self.status_label.config(text=f"Started with {selected}", fg="green")
            else:
                self.status_label.config(text="Failed: No URL for selected source", fg="red")

        self.root.after(3000, lambda: self.status_label.config(text="", fg="blue"))

    def stop_btn_command(self):
        """
            Stop the face recognition engine
        """
        if self.engine.is_running():
            # Use a thread to stop asynchronously
            def stop_async():
                self.status_label.config(text="Stopping...", fg="orange")
                self.engine.stop()
                # Close command handler if exists
                if self.command_handler:
                    try:
                        self.command_handler.close()
                    except:
                        pass
                    self.command_handler = None
                # Update status on main thread
                self.root.after(0, lambda: self.status_label.config(text="Stopped", fg="orange"))
                self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))
            
            threading.Thread(target=stop_async, daemon=True).start()
        else:
            self.status_label.config(text="Engine not running", fg="orange")
            self.root.after(2000, lambda: self.status_label.config(text="", fg="blue"))

    def on_close(self):
        """
            Clean up on window close
        """
        self.scanning = False
        if hasattr(self, 'engine'):
            self.engine.stop()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1370x800")
    root.configure(bg="#C0C0C0")
    app = FaceRecognitionGUI(root)
    root.mainloop()