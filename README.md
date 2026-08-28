# Surveillance Robot — Employees Attendance

Repository: AhmadYamen-Radwan/Surveillance-Robot-Employees-Attendance  
Repo ID: 1349672226

## Overview
A surveillance robot that patrols a facility, captures images/video, performs face recognition, and logs employee attendance automatically. This project integrates robotics (movement and camera), computer vision (face detection/recognition), and a lightweight backend for attendance records.

## Features
- Autonomous or remote-controlled patrol routes
- Real-time face detection and recognition using a trained model
- Attendance logging with timestamp and location
- Video/image capture with optional retention policy
- Web dashboard / API to view attendance logs
- Configurable hardware and software stack (modular)

## Architecture
- Robot controller: handles movement (motor drivers), route logic, and camera capture
- Vision pipeline: runs face detection and recognition (OpenCV / DNN / PyTorch / TensorFlow)
- Backend: REST API + database to store attendance events (SQLite/Postgres)
- Dashboard: lightweight web UI (Flask / FastAPI / React optional)

## Requirements
- Hardware (example build)
  - Raspberry Pi 4 (or similar SBC) or NVIDIA Jetson (for accelerated inference)
  - USB / CSI camera module (e.g., Raspberry Pi camera, Logitech)
  - Motor driver and motors (H-bridge, wheels/chassis)
  - Power supply and battery pack
- Software
  - Python 3.8+
  - OpenCV
  - face-recognition libs (dlib or deep-learning model + framework)
  - Flask or FastAPI
  - SQLite3 or PostgreSQL
  - (Optional) Docker

## Installation (quick start)
1. Clone the repo:
   git clone https://github.com/AhmadYamen-Radwan/Surveillance-Robot-Employees-Attendance.git
2. Create a Python virtual environment and activate:
   python3 -m venv venv
   source venv/bin/activate
3. Install Python dependencies:
   pip install -r requirements.txt
4. Configure hardware and camera in `config.yml` (see Configuration)
5. Initialize the database:
   python scripts/init_db.py
6. Start the backend:
   python backend/app.py
7. Start the robot controller on the robot:
   python robot/controller.py --config config.yml

(If using Docker, see `docker/README.md` for image build/run instructions.)

## Configuration
- `config.yml` (example)
  - camera:
      device: 0
      width: 1280
      height: 720
  - recognition:
      model: models/face_recognition.pt
      threshold: 0.6
  - robot:
      patrol_routes: routes/default.json
      max_speed: 0.5
  - backend:
      db_url: sqlite:///attendance.db
      host: 0.0.0.0
      port: 8000

## Dataset & Model Training
- Provide a dataset of labeled employee images (one folder per employee).
- Use the training scripts in `scripts/train_recognition.py` to produce a model file.
- Recommended pipeline:
  1. Collect and verify labeled images (good lighting, multiple angles).
  2. Augment and preprocess images (resize, normalize).
  3. Train embedding-based model (e.g., FaceNet or ArcFace) or fine-tune a classifier.
  4. Export model to `models/`.

## Usage
- To run the recognition pipeline locally:
  python vision/recognize.py --source 0 --model models/face_recognition.pt
- To run the full stack (robot + backend), launch backend first then start the controller on the robot.
- Attendance events are stored in the DB table `attendance` with fields:
  - id, employee_id, name, timestamp, image_path, location, confidence

## Privacy & Security
- Store images and logs only as required by your policy — provide retention and deletion policies.
- Secure access to the backend with authentication (JWT/HTTPS).
- Notify employees and comply with local laws for biometric data processing.

## Troubleshooting
- Camera not detected: check `v4l2-ctl --list-devices` (Linux) and `config.yml` device index.
- Low recognition accuracy: add more training images per person, improve lighting, or lower the recognition threshold.
- Robot movement issues: verify motor driver wiring and test with `scripts/test_motors.py`.

## Contributing
Contributions welcome. Suggested workflow:
- Fork the repo
- Create a feature branch: git checkout -b feat/your-feature
- Add tests and update README/docs
- Open a PR with a clear description

Please follow the code style and include documentation for hardware changes.

## Roadmap / Ideas
- Improve edge inference performance (TensorRT, ONNX)
- Add multi-robot coordination
- Integrate BLE/Wi-Fi presence detection as a fallback
- Add role-based access and audit logs

## License
This project is provided under the MIT License. See LICENSE file for details.

## Contact
Maintainer: Ahmad Yamen Radwan (GitHub: @AhmadYamen-Radwan)  
For questions or hardware specifics, open an issue in the repository.
