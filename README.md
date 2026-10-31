# Gesture-Controlled Robotic Arm

ECE 211P Electronics Lab project, IIIT Bangalore. A 4-DOF robotic arm that copies your hand. A phone camera streams video to the **Arduino UNO Q**, the board tracks your hand, and the servos follow. No laptop at demo time.

**Status (Oct 31):** hand tracking works on the UNO Q: 21 hand points at **~18 FPS** while a hand is in view. Not built yet: hand → servo angles, smoothing, the Bridge link to the STM32, the servo sketch.

---

## Start here

**Done:** phone → board stream, and a hand tracker on the board (`hand.py`). Build on it; don't redo it. Section 6 explains why it's built this way.

**Open tasks:**
1. **`mapping.py`:** 21 points → 4 servo angles + gripper. Calibration, dead zone, One Euro filter, two thresholds for the gripper. Can be built on a laptop.
2. **STM32 servo sketch:** move each SG90 gradually toward its target, speed limit, safe pose if data stops.
3. **Bridge link:** send angles from Python to the sketch, at most ~20 updates/s.

---

## 1. How it works

The UNO Q is two computers on one board:

| | Linux side | Microcontroller side |
|---|---|---|
| Chip | Qualcomm QRB2210, 4× Cortex-A53 @ 2.0 GHz | STM32U585 |
| Job | Video + hand tracking (Python) | Servo PWM (Arduino sketch) |

```
Phone (IP Webcam) ──Wi-Fi hotspot──▶ camera.py   newest frame only, reconnects
                                       hand.py    palm detector → rotated crop → landmark model
                                                  → 21 points (x, y, z)
                                       mapping.py → angles          (next)
                                            │ Bridge                (next)
                                            ▼
                                       STM32 → PWM → servos         (next)
```

**The tracker** (`hand.py`) runs Google's two hand networks on TFLite with 4 threads:
- **Palm detector**: whole frame (letterboxed to 192×192) → best of 2,016 anchor boxes → palm box + 7 keypoints. Runs only when no hand is tracked.
- **Landmark model**: a 224×224 crop around the hand, rotated upright → 21 points + presence score.
- **Tracking**: each next crop is built from the last 21 points, so the palm detector is skipped until the hand is lost (presence < 0.5).

## 2. Results (measured on the UNO Q)

| Item | Result |
|---|---|
| Phone stream at 640×480 | ~30 FPS, ~1 ms wait on the board |
| Palm detector, 4 threads | ~62–65 ms |
| Landmark model, 4 threads | ~45 ms |
| **Tracking one hand** | **~18 FPS** (~50 ms/frame) |
| Searching (no hand) | 8–13 FPS |
| MediaPipe 0.10.18, for comparison | ~6 FPS |

Speed tests: `notes/benchmarks.md`. Proof the points are correct: `docs/track_test/track_out.jpg`.

## 3. Files

| File | Job |
|---|---|
| `config.py` | Settings: camera URL, model folder, thread count |
| `camera.py` | Reads the phone stream. Newest frame only, reconnects, stops cleanly |
| `hand.py` | The tracker: frame in → 21 points out (or nothing) |
| `main.py` | Live loop: prints FPS and the index fingertip |
| `check_camera.py` | 30 s camera test (FPS, reconnect) |
| `check_hand.py` | Photo test: saves pictures with the points drawn |
| `experiments/bench_tflite.py` | Benchmark: each network with 1/2/4 threads |
| `notes/benchmarks.md` | Speed test results |
| `docs/` | Proof images (section 6) |

`models/` and `probes/` are git-ignored; make them as below.

---

## 4. Setup

### 4.1 Phone (IP Webcam, Android)
1. Video preferences → **Video resolution 640×480**. Bigger images slow the board.
2. Phone Settings → Apps → IP Webcam → **Battery saver: No restrictions**, **Autostart on**. Otherwise the phone kills it when locked.
3. Turn on the **phone hotspot**, then **Start server**. After changing video settings, stop and start the server.

### 4.2 A shell on the board
Easiest: the terminal in **Arduino App Lab** (bottom right). Or over USB from Ubuntu:
```bash
sudo apt install adb
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="2341", ATTR{idProduct}=="0078", MODE="0660", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/51-arduino-unoq.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# replug the board, then:
adb kill-server
adb shell
```
Board user: `arduino`. Password: on the team WhatsApp (never commit it). On a new board, the first `sudo` makes you set one.

### 4.3 Network (on the board)
The board must be on the phone hotspot. Campus Wi-Fi blocks device-to-device traffic.
```bash
nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes'     # which Wi-Fi?
sudo nmcli dev wifi connect "<HOTSPOT>" password "<PASSWORD>"   # if not on the hotspot
ip route | grep default                            # "via X.X.X.X" = the phone's IP
curl -I http://<PHONE_IP>:8080/shot.jpg            # expect 200 OK
```
Use the `via` address. IP Webcam may show a `100.x.x.x` mobile-data address instead; that one changes on reconnect.

### 4.4 Code, models, environment (on the board)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # skip if uv exists
source $HOME/.local/bin/env

git clone https://github.com/vedsavjani/Gesture-Controlled-Robotic-Arm.git ~/gesture-arm
cd ~/gesture-arm
mkdir -p models probes
wget -O models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
python3 -m zipfile -e models/hand_landmarker.task models/

uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```
`ls models` must show `hand_detector.tflite` and `hand_landmarks_detector.tflite`. The board's own Python 3.13 is enough; don't install MediaPipe.

**Every new shell:** `cd ~/gesture-arm && source .venv/bin/activate`

### 4.5 Camera address
Edit `CAMERA_URL` in `config.py`, or per run: `export CAMERA_URL=http://<PHONE_IP>:8080/video`

---

## 5. Run

```bash
python check_camera.py
```
Pass: ~30 FPS, shape `(480, 640, 3)`. Stop/start the phone server once mid-test: FPS drops to 0 and recovers within ~5 s. Ends with `done`.

```bash
curl -o probes/open.jpg http://<PHONE_IP>:8080/shot.jpg   # open palm
curl -o probes/tilt.jpg http://<PHONE_IP>:8080/shot.jpg   # tilted ~45°
curl -o probes/far.jpg  http://<PHONE_IP>:8080/shot.jpg   # far away
curl -o probes/none.jpg http://<PHONE_IP>:8080/shot.jpg   # no hand
python check_hand.py probes/open.jpg probes/tilt.jpg probes/far.jpg probes/none.jpg
```
Pass: `HAND` ×3, `no hand` ×1. Then **look at the images**: the points must sit on the real joints (`*_out.jpg`), and the hand must be upright and fully inside `*_crop.jpg`. View them with `adb pull`, or serve them: `python -m http.server 8000 --directory probes` and open `http://<BOARD_IP>:8000` (`hostname -I` gives the board's own IP, which differs from the phone's).

```bash
python main.py        # Ctrl+C to stop
```
Pass: ≥15 FPS with a hand in view; recovers after you pull your hand out and back.

**Laptop (no board):** same steps from 4.4 without uv's install line (install uv per its site), Python 3.12 or 3.13. Tested on Linux; on Windows use WSL. Laptop FPS is higher; confirm numbers on the board.

---

## 6. Why it's built this way

1. **Not MediaPipe.** MediaPipe 1.2.0 crashes on the board (`Illegal instruction`: built for ARMv8.1 LSE instructions; the Cortex-A53 is ARMv8.0). 0.10.18 runs but at ~6 FPS: `top` showed ~120% CPU, i.e. it used about one of the four cores.
2. **TFLite with 4 threads.** The same two networks on `ai-edge-litert` with `num_threads=4` run ~3× faster each (`experiments/bench_tflite.py`). We wrote the parts MediaPipe did for us (anchor decoding, rotated crop, tracking) → ~18 FPS.
3. **Palm detector input must be scaled 0..1.** With −1..1 the model returns score 1.00 with boxes far outside the image, even with no hand. Compare `docs/palm_test/hand1_out_01.jpg` (correct) with `hand1_out_11.jpg` (wrong). A high score doesn't prove correctness; check the picture.
4. **Phone as camera** over the hotspot: no camera hardware or USB hub needed; the stream is ~30 FPS, so the network is not the bottleneck.

The original experiment scripts (MediaPipe baseline, model inspection, single-photo palm test, the first tracker) are in commit `af3f9e0`.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `Connection refused` | IP Webcam server stopped. Start it; check the battery setting |
| `curl` times out | Wrong IP or not on the hotspot (campus Wi-Fi blocks devices) |
| Phone IP changed | `ip route \| grep default` again; update `CAMERA_URL` |
| Frame is 1920×1080 | Set 640×480, then stop and start the server |
| adb `no permissions` | Add the udev rule (4.2), replug, `adb kill-server` |
| `command not found: uv` | `source $HOME/.local/bin/env` |
| `ModuleNotFoundError` | Venv not active: `source .venv/bin/activate` |
| `Illegal instruction` | MediaPipe 1.x installed. Don't use it on this board |
| `hand_detector.tflite` not found | Redo the model step; check `ls models` |
| 0-byte photo in `probes/` | `curl` failed; check the phone IP |
| No hand found | Better light, plain background, whole hand in view, palm to camera |
| adb session drops | Laptop slept or low battery (the board is USB-powered from it) |
| `adb` not found on the board | `adb push/pull` run on the laptop, not in the board shell |

## 8. Rules for the code

- `opencv-python-headless` only. The board has no screen: never `cv2.imshow`; save images.
- Don't modify a frame returned by `camera.read()`; copy it first.
- Settings go in `config.py`, not hard-coded.
- Every loop handles a dropped stream and stops cleanly.
- Pinned package versions; don't upgrade during the project.
- Nothing added without a current reason; when the reason goes, it goes.

## 9. Work log

| Date | Who | What |
|---|---|---|
| Oct 28 | Ved Savjani | Phone as camera: IP Webcam → Wi-Fi → OpenCV, 31 FPS on laptop |
| Oct 29 | Ved Savjani | UNO Q bring-up (adb, hotspot, Python env), stream 30 FPS on the board; diagnosed MediaPipe 1.2.0 crash (LSE) and 0.10.18 single-core bottleneck (5.8 FPS); 4-thread TFLite benchmark (3×); first custom tracker (palm decoding, rotated crop, tracking), verified with images, ~18 FPS |
| Oct 30 | Krtin Singhvi | Re-benchmarked independently; refactored the tracker into `hand.py` (`HandTracker`); `camera.py` with reconnect, timeouts, clean shutdown, frame age; `config.py`, `main.py`, check scripts; verified Python 3.13 (single venv) |
| Oct 31 | Ved Savjani | Merged both into `main`, trimmed to what's required, README |