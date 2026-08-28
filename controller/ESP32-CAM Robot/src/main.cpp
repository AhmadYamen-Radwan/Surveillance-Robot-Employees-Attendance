#include "esp_camera.h"
#include <WiFi.h>
#include <WebSocketsServer.h>
#include <ESPmDNS.h>
#include <WiFiUdp.h>

// ========== Wi-Fi ==========
const char* ssid = "DeathKingdom";
const char* password = "20035112";

// ========== Camera Pins ==========
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ========== Server & WebSocket ==========
WiFiServer server(80);
WebSocketsServer webSocket = WebSocketsServer(81);
WiFiUDP udp;

// ========== State ==========
bool ledState = false;
bool flashState = false;
bool mirrorState = false;
bool robotRunning = false;
String deviceName = "esp32cam";
unsigned long lastBroadcast = 0;
unsigned long lastFrame = 0;
int fpsCount = 0;
unsigned long lastFpsPrint = 0;

// ========== HTML with WebSocket ==========
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ESP32-CAM</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: #0a0a0a;
            color: #fff;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 10px;
        }
        .container {
            max-width: 900px;
            width: 100%;
            background: #1a1a2e;
            border-radius: 20px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 10px 40px rgba(0,0,0,0.8);
        }
        h1 {
            font-size: 28px;
            background: linear-gradient(135deg, #e94560, #0f3460);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle { color: #666; font-size: 14px; margin-bottom: 15px; }
        .video-container {
            background: #000;
            border-radius: 10px;
            overflow: hidden;
            margin: 15px 0;
            aspect-ratio: 4/3;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }
        canvas {
            width: 100%;
            height: 100%;
            display: block;
        }
        .fps-overlay {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.7);
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 14px;
            color: #4caf50;
            font-weight: bold;
        }
        .controls {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            margin: 15px 0;
        }
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 25px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: 0.3s;
            color: #fff;
            min-width: 100px;
        }
        .btn:hover { transform: scale(1.05); }
        .btn-capture { background: #e94560; }
        .btn-led { background: #0f3460; }
        .btn-led.on { background: #f9a825; color: #000; }
        .btn-flash { background: #f57c00; }
        .btn-mirror { background: #2e7d32; }
        .btn-robot { background: #6a1b9a; }
        .btn-robot.on { background: #4caf50; }
        .info { color: #666; font-size: 12px; margin-top: 10px; }
        .fps { color: #4caf50; font-weight: bold; }
        .status {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 10px;
            font-size: 11px;
        }
        .status-online { background: #2e7d32; color: #fff; }
        .status-offline { background: #c62828; color: #fff; }
        @media (max-width: 600px) {
            .btn { padding: 10px 15px; font-size: 12px; min-width: 70px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ESP32-CAM</h1>
        <div class="subtitle">WebSocket Streaming</div>
        
        <div class="video-container">
            <canvas id="canvas"></canvas>
            <div class="fps-overlay" id="fpsDisplay">0 FPS</div>
        </div>
        
        <div class="controls">
            <button class="btn btn-capture" onclick="capturePhoto()">Capture</button>
            <button class="btn btn-led" id="ledBtn" onclick="toggleLED()">LED</button>
            <button class="btn btn-flash" id="flashBtn" onclick="toggleFlash()">Flash</button>
            <button class="btn btn-mirror" id="mirrorBtn" onclick="toggleMirror()">Mirror</button>
            <button class="btn btn-robot" id="robotBtn" onclick="toggleRobot()">Robot</button>
        </div>
        
        <div class="info">
            FPS: <span class="fps" id="fps">0</span> | 
            Status: <span id="status" class="status status-online">● Online</span> |
            IP: <span id="ip">loading...</span>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        let fpsCount = 0;
        let lastFpsTime = Date.now();
        let robotState = false;
        
        fetch('/ip')
            .then(res => res.text())
            .then(ip => document.getElementById('ip').textContent = ip);
        
        function connectWS() {
            const ws = new WebSocket('ws://' + location.hostname + ':81');
            
            ws.onopen = function() {
                console.log('WebSocket connected');
                document.getElementById('status').textContent = '● Online';
                document.getElementById('status').className = 'status status-online';
            };
            
            ws.onmessage = function(event) {
                if (event.data instanceof Blob) {
                    const reader = new FileReader();
                    reader.onload = function() {
                        const img = new Image();
                        img.onload = function() {
                            canvas.width = img.width;
                            canvas.height = img.height;
                            ctx.drawImage(img, 0, 0);
                            fpsCount++;
                        };
                        img.src = reader.result;
                    };
                    reader.readAsDataURL(event.data);
                }
            };
            
            ws.onclose = function() {
                document.getElementById('status').textContent = '● Offline';
                document.getElementById('status').className = 'status status-offline';
                setTimeout(connectWS, 3000);
            };
            
            ws.onerror = function() {
                ws.close();
            };
        }
        
        setInterval(() => {
            const now = Date.now();
            if (now - lastFpsTime >= 1000) {
                document.getElementById('fps').textContent = fpsCount;
                document.getElementById('fpsDisplay').textContent = fpsCount + ' FPS';
                fpsCount = 0;
                lastFpsTime = now;
            }
        }, 1000);
        
        function capturePhoto() {
            window.open('/capture', '_blank');
        }
        
        function toggleLED() {
            const btn = document.getElementById('ledBtn');
            fetch('/led_on')
                .then(res => res.text())
                .then(data => {
                    if (data.includes('ON')) {
                        btn.classList.add('on');
                        btn.textContent = 'ON';
                    } else {
                        btn.classList.remove('on');
                        btn.textContent = 'LED';
                    }
                });
        }
        
        function toggleFlash() {
            const btn = document.getElementById('flashBtn');
            fetch('/flash')
                .then(res => res.text())
                .then(data => {
                    if (data.includes('ON')) {
                        btn.textContent = 'ON';
                    } else {
                        btn.textContent = 'Flash';
                    }
                });
        }
        
        function toggleMirror() {
            const btn = document.getElementById('mirrorBtn');
            fetch('/mirror')
                .then(res => res.text())
                .then(data => {
                    if (data.includes('ON')) {
                        btn.textContent = 'ON';
                    } else {
                        btn.textContent = 'Mirror';
                    }
                });
        }
        
        function toggleRobot() {
            const btn = document.getElementById('robotBtn');
            robotState = !robotState;
            fetch(robotState ? '/run' : '/stop')
                .then(res => res.text())
                .then(data => {
                    if (robotState) {
                        btn.classList.add('on');
                        btn.textContent = 'RUN';
                    } else {
                        btn.classList.remove('on');
                        btn.textContent = 'Robot';
                    }
                });
        }
        
        connectWS();
    </script>
</body>
</html>
)rawliteral";

// ========== Init Camera ==========
bool initCamera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    
    config.frame_size = FRAMESIZE_VGA;  
    config.jpeg_quality = 25;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_PSRAM;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed: 0x%x\n", err);
        return false;
    }
    return true;
}

// ========== WebSocket Event ==========
void webSocketEvent(uint8_t num, WStype_t type, uint8_t *payload, size_t length) {
    if (type == WStype_CONNECTED) {
        Serial.printf("Client %d connected\n", num);
    }
}

// ========== Send UDP Broadcast ==========
void sendUDPBroadcast() {
    String message = deviceName + "|" + WiFi.localIP().toString();
    udp.beginPacket(IPAddress(255, 255, 255, 255), 9999);
    udp.print(message);
    udp.endPacket();
}

// ========== Handle HTTP ==========
void handleClient(WiFiClient client) {
    String request = "";
    while (client.connected() && !client.available()) delay(1);
    while (client.available()) {
        char c = client.read();
        request += c;
        if (c == '\n') break;
    }
    
    // Video stream
    if (request.indexOf("GET /videostream") >= 0 || request.indexOf("GET /capture") >= 0) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
            String header = "HTTP/1.1 200 OK\r\n";
            header += "Content-Type: image/jpeg\r\n";
            header += "Content-Length: " + String(fb->len) + "\r\n";
            header += "Cache-Control: no-cache\r\n\r\n";
            client.print(header);
            client.write(fb->buf, fb->len);
            esp_camera_fb_return(fb);
        }
        return;
    }
    
    // LED ON
    if (request.indexOf("GET /led_on") >= 0) {
        ledState = true;
        digitalWrite(4, HIGH);
        client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nLED ON");
        return;
    }
    
    // LED OFF
    if (request.indexOf("GET /led_off") >= 0) {
        ledState = false;
        digitalWrite(4, LOW);
        client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nLED OFF");
        return;
    }
    
    // Flash
    if (request.indexOf("GET /flash") >= 0) {
        flashState = !flashState;
        digitalWrite(2, flashState ? HIGH : LOW);
        client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n");
        client.print(flashState ? "Flash ON" : "Flash OFF");
        return;
    }
    
    // Mirror
    if (request.indexOf("GET /mirror") >= 0) {
        sensor_t *s = esp_camera_sensor_get();
        mirrorState = !mirrorState;
        s->set_vflip(s, mirrorState ? 1 : 0);
        s->set_hmirror(s, mirrorState ? 1 : 0);
        client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n");
        client.print(mirrorState ? "Mirror ON" : "Mirror OFF");
        return;
    }
    
    // Status
    if (request.indexOf("GET /status") >= 0) {
        String status = "{\"status\":\"ok\",\"led\":" + String(ledState ? "true" : "false") + 
                       ",\"flash\":" + String(flashState ? "true" : "false") +
                       ",\"mirror\":" + String(mirrorState ? "true" : "false") +
                       ",\"robot\":" + String(robotRunning ? "true" : "false") +
                       ",\"fps\":" + String(fpsCount) + "}";
        client.print("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n");
        client.print(status);
        return;
    }
    
    // Robot
    if (request.indexOf("GET /run") >= 0) {
        robotRunning = true;
        digitalWrite(13, HIGH);
        client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nRobot started");
        return;
    }
    
    if (request.indexOf("GET /stop") >= 0) {
        robotRunning = false;
        digitalWrite(13, LOW);
        client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nRobot stopped");
        return;
    }
    
    // IP
    if (request.indexOf("GET /ip") >= 0) {
        client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n");
        client.print(WiFi.localIP().toString());
        return;
    }
    
    // HTML
    client.print("HTTP/1.1 200 OK\r\n");
    client.print("Content-Type: text/html\r\n\r\n");
    client.print(index_html);
}

// ========== Setup ==========
void setup() {
    Serial.begin(115200);
    delay(2000);
    Serial.println("\n=== ESP32-CAM ===\n");

    if (!initCamera()) {
        Serial.println("Camera failed!");
        return;
    }
    Serial.println("Camera OK (QVGA @ 320x240)");

    pinMode(4, OUTPUT);
    pinMode(2, OUTPUT);
    digitalWrite(4, LOW);
    digitalWrite(2, LOW);

    pinMode(13, OUTPUT);

    WiFi.begin(ssid, password);
    Serial.print("Connecting");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());

    MDNS.begin("esp32cam");
    MDNS.addService("http", "tcp", 80);
    
    udp.begin(9999);

    webSocket.begin();
    webSocket.onEvent(webSocketEvent);
    Serial.println("WebSocket on port 81");

    server.begin();
    Serial.println("Server started");
    Serial.println("http://" + WiFi.localIP().toString());
}

// ========== Loop ==========
void loop() {
    webSocket.loop();
    
    WiFiClient client = server.available();
    if (client) {
        handleClient(client);
        client.stop();
    }
    
    // Broadcast UDP every 5 seconds
    if (millis() - lastBroadcast > 5000) {
        sendUDPBroadcast();
        lastBroadcast = millis();
    }
    
    if (millis() - lastFrame > 50) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
            webSocket.broadcastBIN(fb->buf, fb->len);
            esp_camera_fb_return(fb);
            fpsCount++;
        }
        lastFrame = millis();
    }
    
    if (millis() - lastFpsPrint > 5000) {
        Serial.printf("FPS: %d\n", fpsCount / 5);
        fpsCount = 0;
        lastFpsPrint = millis();
    }
}