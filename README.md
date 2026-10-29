# Gesture-Controlled Robotic Arm

ECE 211P Electronics Lab project, IIIT Bangalore. A 4-DOF robotic arm that copies your hand movements. A phone camera watches your hand, the **Arduino UNO Q** tracks it, and the arm's servos follow. No laptop at demo time.

**Status (Oct 29):** the vision half works. Our own hand tracker runs on the UNO Q at **~18 FPS** while tracking a hand (MediaPipe managed only ~5.8 FPS). Next: hand → servo angles, smoothing, and the link to the STM32 that drives the servos.

---

## Start here

**Done:** phone camera → board stream (30 FPS) and a custom hand tracker giving 21 hand points at ~18 FPS on the UNO Q. The working code is `vision/track_test.py` (uses `vision/camera.py`). Don't redo this; read sections 6–8 to see what was tried and why.

**Open tasks: pick one, tell the group, build on `vision/`:**
1. **Hand → servo angles.** Decide which hand motion drives which joint (e.g. wrist x → base, wrist y → shoulder, thumb–index pinch → gripper) and turn landmarks into 4 angles. Can be built and tested entirely on a laptop (quick start below).
2. **Smoothing.** Landmarks jitter by a few pixels; filter them before converting to angles (One Euro filter recommended) so the servos don't twitch.
3. **Board ↔ STM32 link + servo sketch.** Send the angles from Python to the STM32 over Arduino's Bridge; the sketch moves each SG90 *gradually* toward its target (interpolation) instead of jumping. Can start with fake angle sweeps, no camera needed.

There's only one board, so do tasks 1–2 on your laptop first. The tracker runs there unchanged.

## Laptop quick start (no board needed)

Tested on Ubuntu. macOS should work the same. Windows: not tested; if the install fails, use WSL.

```bash
# 1. Python 3.12 venv (install uv first: https://docs.astral.sh/uv/)
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Models
mkdir -p models
curl -L -o models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
python -m zipfile -e models/hand_landmarker.task models/

# 3. Phone: IP Webcam at 640x480, hotspot ON, Start server. Connect your laptop to that hotspot.
# 4. Run (use the URL IP Webcam shows, or the hotspot gateway IP):
python vision/track_test.py http://<PHONE_IP>:8080/video
```
Laptop FPS will be higher than the board's. Always confirm final numbers on the UNO Q.
The adb / udev steps in section 4.2 are Ubuntu-only; adb setup differs on Windows/Mac.

## Work log

| Date | Who | What |
|---|---|---|
| Oct 28 | Ved Savjani | Phone as camera: IP Webcam → Wi-Fi → OpenCV on laptop, 31 FPS |
| Oct 29 | Ved Savjani | UNO Q bring-up: adb access, hotspot networking, Python 3.12 env via uv |
| Oct 29 | Ved Savjani | Phone → board stream: 30 FPS at 640×480 (Exp 2) |
| Oct 29 | Ved Savjani | MediaPipe on the board: diagnosed the 1.2.0 crash (ARMv8.1 LSE vs Cortex-A53), 0.10.18 baseline 5.8 FPS, found single-core bottleneck (Exp 3) |
| Oct 29 | Ved Savjani | 4-thread TFLite benchmark: 3× per network (Exp 4–5) |
| Oct 29 | Ved Savjani | Custom hand tracker (palm decoding, rotated crop, tracking), verified with images: ~18 FPS (Exp 6–7) |

---

## 1. How the system works

The UNO Q is two computers on one board:

| | Linux side (MPU) | Microcontroller side (MCU) |
|---|---|---|
| Chip | Qualcomm QRB2210, 4× Cortex-A53 @ 2.0 GHz | STM32U585 |
| Runs | Debian Linux, Python | Arduino sketch |
| Job here | Video + hand tracking | Servo PWM (precise real-time timing) |
| Programmed via | Terminal (`adb shell`) | Arduino IDE |

```
Phone (IP Webcam) ──Wi-Fi (phone hotspot)──▶ UNO Q Linux side
                                              camera.py: newest frame only
                                              palm detector ─▶ crop ─▶ landmark model
                                              21 hand points (x, y, z)
                                              → servo angles            (next)
                                                   │ Bridge             (next)
                                                   ▼
                                              STM32 → PWM → SG90 servos  (next)
```

## 2. Results so far

| What | Result |
|---|---|
| Phone → board video stream | 30 FPS steady at 640×480 (network is not the bottleneck) |
| MediaPipe 1.2.0 on the board | Crashes ("Illegal instruction") |
| MediaPipe 0.10.18 on the board | Works, but ~5.8 FPS tracking / ~4.5 FPS searching |
| **Our tracker (TFLite, 4 threads)** | **~18 FPS tracking / 8–13 FPS searching** |

---

## 3. Repo layout

```
README.md
requirements.txt            packages for the tracker (board + laptop)
requirements-mediapipe.txt  ONLY for the MediaPipe baseline experiment
vision/                     the working tracker
  camera.py                 phone stream reader (keeps only the newest frame)
  stream_test.py            Experiment 2: does video reach the board? how fast?
  track_test.py             Experiment 7: our hand tracker, live, with FPS
experiments/                how we got here (results in section 6)
  hand_test.py              Experiment 3: MediaPipe baseline
  bench_tflite.py           Experiment 4: 1 vs 2 vs 4 threads benchmark
  inspect_models.py         Experiment 5: prints the models' inputs/outputs
  palm_test.py              Experiment 6: palm detector on single photos
docs/                       output images from the experiments
  palm_test/                Experiment 6 outputs
  track_test/               Experiment 7 outputs
models/                     NOT committed - download it (section 4.5)
```

---

## 4. Setup

### 4.1 Phone camera
1. Install **IP Webcam** (Android) → Video preferences → resolution **640×480**.
2. Phone Settings → Apps → IP Webcam → **Battery saver → No restrictions**, and turn on **Autostart**. Otherwise the phone kills the app when it locks.
3. Turn on your **phone hotspot**. Open IP Webcam → **Start server**.

### 4.2 Laptop → board (Ubuntu)
```bash
sudo apt install adb
# allow your user to access the UNO Q over USB (USB ID 2341:0078)
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="2341", ATTR{idProduct}=="0078", MODE="0660", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/51-arduino-unoq.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# unplug + replug the board, then:
adb kill-server
adb devices      # should show <serial>  device
adb shell        # you are now on the board
```
Board user is `arduino`. The password is on the team WhatsApp. On a brand-new board, the first `sudo` forces you to set one.

### 4.3 Board → phone hotspot (on the board)
```bash
sudo nmcli dev wifi connect "<HOTSPOT_NAME>" password "<HOTSPOT_PASSWORD>"
ip route         # "default via X.X.X.X" = the phone's IP
```
The stream URL is `http://<that IP>:8080/video`. Ved's phone: `http://10.138.189.35:8080/video`.

### 4.4 Python 3.12 environment (on the board)
The board ships Python 3.13; we use a separate Python 3.12 via `uv`. See section 7 for why.
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
mkdir -p ~/gesture-arm
cd ~/gesture-arm
uv venv --python 3.12 venv-tflite
source venv-tflite/bin/activate
uv pip install -r requirements.txt    # after copying requirements.txt to the board (4.6)
```

### 4.5 Models (on the board, in ~/gesture-arm)
```bash
mkdir -p models
wget -O models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
python -m zipfile -e models/hand_landmarker.task models/
ls models   # hand_landmarker.task  hand_detector.tflite  hand_landmarks_detector.tflite
```
The `.task` file is a zip archive holding Google's two hand networks (section 5).

### 4.6 Copy the code to the board (on the laptop, from the repo folder)
```bash
adb push vision experiments requirements.txt requirements-mediapipe.txt /home/arduino/gesture-arm/
```

### 4.7 Every new `adb shell` session
```bash
cd ~/gesture-arm
source venv-tflite/bin/activate
```
Run all scripts **from `~/gesture-arm`** (they look for `models/` there).

---

## 5. Background: the two hand networks

Google's hand model (inside `hand_landmarker.task`) is two neural networks run in sequence:

1. **Palm detector** (`hand_detector.tflite`). Input: the whole frame, letterboxed to 192×192. Output: 2,016 candidate boxes (positions relative to fixed "anchors"), each with a score and 7 palm keypoints. It detects the **palm** because a palm is rigid and looks similar in every gesture; fingers don't.
2. **Landmark model** (`hand_landmarks_detector.tflite`). Input: a 224×224 crop around the hand, **rotated upright** and enlarged 2.6× from the palm box so the fingers fit. Output: **21 landmarks** (x, y, z), a hand presence score, and left/right.

**Tracking:** once a hand is found, each next frame skips the palm detector and crops around the previous frame's landmarks. The palm detector runs again only when the presence score drops, i.e. the hand is lost. That's why tracking is faster than searching.

---

## 6. Experiments, in order

| # | Script | Question | Answer |
|---|---|---|---|
| 1 | (old `phone_cam_demo.py`, laptop) | Can a phone be the camera? | Yes, 31 FPS on laptop (Oct 28) |
| 2 | `vision/stream_test.py` | Does video reach the board fast enough? | Yes, 30 FPS steady |
| 3 | `experiments/hand_test.py` | Does MediaPipe hand tracking run on the board? | Yes (0.10.18 only), but ~5.8 FPS |
| 4 | `experiments/bench_tflite.py` | Would 4 threads make the networks faster? | Yes, ~3× |
| 5 | `experiments/inspect_models.py` | What exactly do the networks take/return? | Shapes in table below |
| 6 | `experiments/palm_test.py` | Does our palm detection code work? | Yes, with 0–1 input scaling |
| 7 | `vision/track_test.py` | Our full tracker, live: correct and fast? | Yes, ~18 FPS |

### Experiment 2: stream test
`python vision/stream_test.py http://<PHONE_IP>:8080/video`
Counts frames arriving from the phone each second for 10 s and saves one frame. **Result: 30 FPS steady at 640×480.** That's the phone camera's maximum, so the network is not the bottleneck. (The first line says ~60: frames from the 1 s warm-up get counted there. Ignore it.)

### Experiment 3: MediaPipe baseline
Needs its own venv (section 7): `uv venv --python 3.12 venv-mp`, `source venv-mp/bin/activate`, `uv pip install -r requirements-mediapipe.txt`
`python experiments/hand_test.py http://<PHONE_IP>:8080/video`
- **MediaPipe 1.2.0 crashed** with `Illegal instruction`. Its ARM build uses ARMv8.1 "LSE" instructions; the board's Cortex-A53 is ARMv8.0 and doesn't have them.
- **MediaPipe 0.10.18 works**: tracking ~5.8 FPS (165 ms/frame), searching ~4.5 FPS (217 ms/frame). Hand detection is correct.
- **Why so slow:** `top` showed the Python process at **~120% CPU**, i.e. about 1.2 of the 4 cores (400% max). MediaPipe's Python build runs the network on essentially **one core**. The other three sat idle.

### Experiment 4: thread benchmark
`python experiments/bench_tflite.py`
Runs each network directly on the TFLite runtime with 1, 2 and 4 threads (random input, 50 timed runs).

| Network | 1 thread | 4 threads | Speedup |
|---|---|---|---|
| Palm detector | 194 ms | 65 ms | 3.0× |
| Landmark model | 136 ms | 46 ms | 3.0× |

The 1-thread times match MediaPipe's, which confirms the single-core diagnosis. 4 threads split each layer's math across all cores. This is why we built our own tracker (section 7).

### Experiment 5: model inspection
`python experiments/inspect_models.py`

| Network | Input | Outputs |
|---|---|---|
| Palm detector | `[1,192,192,3]` float32 | `[1,2016,18]` boxes (4 box + 7×2 keypoints), `[1,2016,1]` scores |
| Landmark model | `[1,224,224,3]` float32 | `[1,63]` 21×(x,y,z), `[1,1]` presence, `[1,1]` handedness, `[1,63]` world landmarks |

### Experiment 6: palm detector on single photos
```bash
curl -o hand1.jpg http://<PHONE_IP>:8080/shot.jpg     # one photo from the phone
python experiments/palm_test.py hand1.jpg
```
It runs the palm detector with two possible input scalings (pixels → 0..1 and → −1..1) and saves `<photo>_out_01.jpg` and `<photo>_out_11.jpg`, with the palm box (green) and the 7 keypoints (red; 0 = wrist, 1–4 = finger bases, 5–6 = thumb).

| Photo | 0..1 | −1..1 |
|---|---|---|
| hand1 open palm | ✅ box on palm, 0.94 | ❌ box at (−27222, −27231), score 1.00 |
| hand2 tilted | ✅ 0.78 | ❌ off-image, 1.00 |
| hand3 far away | ✅ 0.84 | ❌ invalid box, 1.00 |
| no hand | ✅ 0.05 (correctly no palm) | ❌ 37 "palms", 1.00 |

**Conclusion: input must be scaled 0..1.** −1..1 gives *confident but completely wrong* answers. A high score does not prove correctness; always check the picture.
Outputs: `docs/palm_test/` (`hand1/2/3_out_01.jpg` and `_11.jpg`; `palm_out.jpg` is the first close-up attempt with −1..1, with no box visible).

### Experiment 7: our tracker, live
`python vision/track_test.py http://<PHONE_IP>:8080/video`
Palm detector + rotated crop + landmark model + tracking, both networks with 4 threads, for 15 s. It prints FPS, tracking/searching state, ms per network and presence score each second, and saves the last tracked frame.

**Result:**
| | MediaPipe (Exp 3) | Our tracker |
|---|---|---|
| Tracking | 5.8 FPS | **~18 FPS** |
| Landmark model per frame | 165 ms | ~53 ms |
| Searching | 4.5 FPS | 8–13 FPS |

Presence 0.99–1.00 while tracking. Outputs in `docs/track_test/`: `track_out.jpg` (21-point skeleton drawn on the hand: lands on the real joints, so it's correct, not just fast) and `track_crop.jpg` (the 224×224 crop the landmark model saw: the whole hand fits).

---

## 7. Why we changed approach (and why two venvs)

1. **System Python 3.13 → uv's Python 3.12.** MediaPipe only publishes builds for Python 3.9–3.12, and the board ships 3.13. `uv` downloads a ready-made Python 3.12 into your home folder without touching the system Python, which the board's own tools (App Lab) depend on. 3.12 also matches our laptops.
2. **MediaPipe 1.2.0 → 0.10.18.** 1.2.0 crashes on the A53 (Experiment 3). 0.10.18 runs.
3. **MediaPipe → our own tracker on TFLite.** MediaPipe was correct but used only ~1 of 4 cores: 5.8 FPS. Running the *same two networks* on the TFLite runtime lets us set `num_threads=4` → 3× faster per network (Experiment 4). We wrote the parts MediaPipe did for us (anchor decoding, rotated crop, tracking), checked each with images (Experiments 6, 7), and got **~18 FPS**, up from 5.8. Lower time per frame means less lag between hand and arm, not just more FPS.
4. **Two venvs.** MediaPipe 0.10.18 needs numpy 1.x; the TFLite runtime installs numpy 2.x. In one venv, installing one breaks the other. So: `venv-tflite` (requirements.txt) for the tracker, and a separate MediaPipe venv only for re-running Experiment 3. **For normal work you only need `venv-tflite`.**

---

## 8. Pitfalls (each cost us time)

1. **adb "no permissions"** → add the udev rule (4.2), then replug and `adb kill-server`.
2. **Campus Wi-Fi blocks devices talking to each other** → use the phone hotspot.
3. **Wrong phone IP**: IP Webcam shows the mobile-data IP (100.x.x.x), which changes on reconnect. Use the hotspot IP from `ip route` on the board.
4. **"Connection refused"** = the phone is reachable but IP Webcam stopped → restart the server, and set Battery saver → No restrictions.
5. **First `sudo` on a new board** asks you to set a new password; that's the board's own `arduino` account password.
6. **`python3 -m venv` fails** (no `python3-venv`) → use `uv venv` instead.
7. **MediaPipe 1.x on the UNO Q** → "Illegal instruction". Use `mediapipe<1` if you need MediaPipe at all.
8. **"Installed" ≠ "works"**: MediaPipe 1.2.0 installed and imported fine and only crashed when creating the model. Always test the real operation.
9. **Palm detector input scaling must be 0..1**; −1..1 gives confident garbage (Experiment 6).
10. **No screen on the board**: never use `cv2.imshow`; use `opencv-python-headless` and save images instead.
11. **New `adb shell` = fresh state**: `cd ~/gesture-arm` and activate the venv again.
12. **Laptop sleep / low battery drops the adb session** (the board is USB-powered from the laptop) → keep it charging.
13. **`adb push`/`pull` run on the laptop**, not inside `adb shell` (the board has no adb).
14. **Empty file pushed**: check `ls -l <file>` before `adb push`; 0 bytes means you pushed nothing.
15. **Board clock is UTC** (5:30 behind IST). Only matters when reading log timestamps.
16. **Phone image comes out rotated** if the phone is held sideways → mount the phone so the image is upright.

## 9. Known issues / next steps

- `track_test.py` prints `Segmentation fault` **after** finishing. It's harmless: the camera's background thread is still running while Python shuts down. To fix in the real program with a clean shutdown.
- `camera.py` doesn't reconnect if the stream drops; the final program needs that.
- Next: map landmarks → servo angles, add smoothing (One Euro filter on Linux, interpolation on the STM32), and the Bridge link to the STM32 servo sketch.