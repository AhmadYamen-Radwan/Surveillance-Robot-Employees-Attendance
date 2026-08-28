import requests
import json

class ESP32CAMController:
    """
        Controller for ESP32-CAM commands via HTTP
    """
    
    def __init__(self, ip, port=80):
        self.ip = ip
        self.port = port
        self.base_url = f"http://{ip}:{port}"
        self.session = requests.Session()
        self.session.timeout = 3
        
    def send_command(self, command):
        """
            Send command to ESP32-CAM via HTTP
            Commands: led_on, led_off, status, run, stop, flash, mirror
        """
        endpoints = {
            "led_on": "/led_on",
            "led_off": "/led_off",
            "status": "/status",
            "run": "/run",
            "stop": "/stop",
            "flash": "/flash",
            "mirror": "/mirror"
        }
        
        endpoint = endpoints.get(command)
        if not endpoint:
            return f"Unknown command: {command}"
        
        try:
            response = self.session.get(self.base_url + endpoint, timeout=2)
            if response.status_code == 200:
                return response.text.strip()
            else:
                return f"Error: HTTP {response.status_code}"
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to ESP32-CAM"
        except requests.exceptions.Timeout:
            return "Error: Connection timeout"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def close(self):
        """ 
            Close the session
        """
        self.session.close()
    
    def is_connected(self):
        """
            Check if ESP32-CAM is reachable
        """
        try:
            response = self.session.get(self.base_url + "/status", timeout=1)
            return response.status_code == 200
        except:
            return False