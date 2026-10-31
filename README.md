# Gesture-Controlled Robotic Arm

ECE 211P Electronics Lab project, IIIT Bangalore. A 4-DOF robotic arm that copies your hand. A phone camera streams video over Wi-Fi to the **Arduino UNO Q**, the board finds 21 points on your hand in real time, and the arm's servos follow. **No laptop is used at demo time**: the board does all the processing.

**Status (Oct 31):** hand tracking works on the UNO Q: 21 hand points at **~18 FPS** while a hand is in view, verified correct with images. Not built yet: hand → servo angles, smoothing, the Bridge link to the STM32, the servo sketch, the physical arm.

---

## Contents

0. [Start here](#0-start-here)
1. [How the system works](#1-how-the-system-works)
2. [Results](#2-results-measured-on-the-uno-q)
3. [Files](#3-files)
4. [What you need](#4-what-you-need)
5. [Setup](#5-setup)
6. [Run the checks](#6-run-the-checks)
7. [Laptop setup (no board)](#7-laptop-setup-no-board)
8. [Why it's built this way](#8-why-its-built-this-way)
9. [Pitfalls](#9-pitfalls-each-one-cost-us-time)
10. [Troubleshooting](#10-troubleshooting)
11. [Rules for the code](#11-rules-for-the-code)
12. [Next steps](#12-next-steps)
13. [Work log](#13-work-log)

---

## 0. Start here

**Done:** phone camera → board stream, and a hand tracker on the board (`hand.py`). **Build on it; don't redo it.** Section 8 explains every design decision and what was tried before.

**Open tasks: pick one, tell the group, then start:**

| # | Task | Needs the board? |
|---|---|---|
| 1 | **`mapping.py`**: turn the 21 points into 4 servo angles + a gripper value (calibration, dead zone, One Euro filter, two thresholds for the gripper) | No: develop on a laptop with recorded landmark clips |
| 2 | **STM32 servo sketch**: move each SG90 gradually toward its target, speed limit, safe pose if data stops | No camera needed; needs the board's MCU side |
| 3 | **Bridge link**: send the angles from Python (Linux side) to the sketch (MCU side), at most ~20 updates/s | Yes |
| 4 | **Arm assembly + power**: build the 4-DOF frame, wire the servos with their **own 5 V supply** (4 SG90s through the board can make it reset) | Hardware |

There's only one board, so do task 1 on your laptop first. The tracker runs there unchanged (section 7).

---

## 1. How the system works

### The board: two computers in one

| | Linux side (MPU) | Microcontroller side (MCU) |
|---|---|---|
| Chip | Qualcomm QRB2210, 4× ARM Cortex-A53 @ 2.0 GHz, 4 GB RAM | STM32U585 (Cortex-M33, 160 MHz) |
| Runs | Debian Linux, Python | Arduino sketch |
| Good at | Heavy computation: video, neural networks | Precise real-time timing (PWM) |
| Bad at | Guaranteed timing (the OS can pause a program anytime) | Anything heavy; it can't run OpenCV |
| Job in this project | Video + hand tracking + angle mapping | Driving the servos |
| Programmed via | A terminal (App Lab terminal or `adb shell`) | Arduino IDE / App Lab |
| Talk to each other via | **Bridge** (Arduino's RPC link between the two chips) | Bridge |

### The pipeline

```
Phone (IP Webcam app)
   │  Wi-Fi: the phone's own hotspot. Video = stream of JPEG images over HTTP
   ▼
camera.py   background thread; keeps ONLY the newest frame (no lag build-up); reconnects if the stream drops
   ▼
hand.py     palm detector (only when no hand is tracked) → rotated crop → landmark model
            → 21 points (x, y in frame pixels; z = rough depth)
   ▼
mapping.py  points → 4 servo angles + gripper                       (next)
   │  Bridge                                                         (next)
   ▼
STM32 sketch → PWM → SG90 servos → the arm moves                     (next)
```

### The tracker (`hand.py`)

Google's hand model is **two neural networks** run in sequence. We run them on the TFLite runtime (`ai-edge-litert`) with **4 threads**:

1. **Palm detector** (`hand_detector.tflite`)
   - Input: the whole frame, **letterboxed** to 192×192 (shrunk without stretching, black padding), pixels scaled **0..1**.
   - Output: **2,016 candidate boxes**, each with a score and 7 palm keypoints (0 = wrist, 1–4 = finger bases, 5–6 = thumb). Each box is an adjustment relative to a fixed **anchor** position (a 24×24 grid with 2 anchors per cell + a 12×12 grid with 6 per cell = 2,016). We take the best-scoring one; below 0.5 means "no hand".
   - It detects the **palm**, not the whole hand, because a palm is rigid and looks similar in every gesture; fingers don't.
2. **Landmark model** (`hand_landmarks_detector.tflite`)
   - Input: a 224×224 crop around the hand, **rotated so the hand points straight up** (using the wrist → middle-finger-base direction) and enlarged so the fingers fit (2.6× the palm box on first detection).
   - Output: **21 landmarks** (x, y, z), a **presence score** (is there really a hand?), handedness, and world landmarks.
3. **Tracking**: once a hand is found, each next frame's crop is built from the **previous frame's 21 points** (2.0× their extent), so the expensive palm detector is skipped. It runs again only when the presence score drops below 0.5 (hand lost) or the crop gets tiny. That's why tracking (~18 FPS) is faster than searching (8–13 FPS).

The 21 landmarks: 0 = wrist; thumb 1–4; index 5–8; middle 9–12; ring 13–16; pinky 17–20 (the last number of each finger is its tip; 8 = index tip, 4 = thumb tip).

---

## 2. Results (measured on the UNO Q)

| Item | Result |
|---|---|
| Phone → board stream at 640×480 | ~30–37 FPS, ~1 ms wait on the board (network is not the bottleneck) |
| Palm detector, 1 / 2 / 4 threads | 190–194 / 101–108 / 62–65 ms |
| Landmark model, 1 / 2 / 4 threads | 136 / 76–78 / 45–46 ms |
| **Tracking one hand** | **~18 FPS** (~50 ms per frame) |
| Searching (no hand in view) | 8–13 FPS |
| MediaPipe 0.10.18 (for comparison) | ~6 FPS tracking, ~4.5 searching |
| MediaPipe 1.2.0 | Crashes (`Illegal instruction`) |

Both of us benchmarked independently and got the same numbers. Details: `notes/benchmarks.md`. Correctness proof: `docs/track_test/track_out.jpg` (the 21-point skeleton lands on the real joints).

### Verified on the board (Oct 31, merged code, fresh setup from this README)

| Check | Result |
|---|---|
| `check_camera.py` | ~30 FPS, 640×480, ~1 ms wait on the board; phone found automatically; recovered after the IP Webcam server was stopped and restarted (twice); clean exit |
| `check_hand.py` | `HAND` for open / tilted / far photos (presence 0.88–1.00), `no hand` for the empty photo; points on the real joints. Search path ~110–136 ms, tracking path ~48 ms |
| `main.py` | ~18 FPS while tracking (hand in 19/19 frames); 8–9 FPS searching when the hand leaves; finds the hand again within ~1 s |

**Known limits (from that run):**
- **Palm should face the camera.** With the hand edge-on (palm sideways, fingers stacked), the hand is still found but finger positions are partly guessed. Design gestures that keep the palm roughly toward the camera.
- **Points can be outside the frame** (e.g. y = −35) when a fingertip goes past the image edge: the model estimates where it would be. Clamp before mapping to angles.
- **Tracking drops at frame edges and on fast moves**, then recovers within ~1 s. The mapping should hold the last angles briefly instead of jumping.

---

## 3. Files

| File | Job |
|---|---|
| `config.py` | All settings in one place: model folder, thread count, and the camera URL, which is **found automatically** (the phone = the hotspot gateway) or set with the `CAMERA_URL` environment variable |
| `camera.py` | Reads the phone stream in a background thread. Gives out only **new** frames plus their age. Reconnects if the stream drops (5 s open / 3 s read timeouts). Stops cleanly |
| `hand.py` | The tracker: `HandTracker().process(frame)` → `(21×3 points, presence)` or `None` |
| `main.py` | Live loop: camera → tracker → prints FPS, how many frames had a hand, and the index fingertip. Ctrl+C to stop |
| `check_camera.py` | 30-second camera test: FPS, frame size, board-side wait, reconnect |
| `check_hand.py` | Photo test: runs the full tracker on photos, saves the points drawn (`*_out.jpg`) and what the model saw (`*_crop.jpg`) |
| `experiments/bench_tflite.py` | Benchmark: each network with 1, 2 and 4 threads. Re-run if threads, models or the board change |
| `notes/benchmarks.md` | Speed test results |
| `docs/palm_test/` | Proof that the palm detector input must be scaled 0..1 (section 8) |
| `docs/track_test/track_out.jpg` | Proof the tracker is correct |
| `requirements.txt` | Three pinned packages |

How the files depend on each other:
```
main.py ──▶ camera.py ──▶ config.py
   └─────▶ hand.py ─────▶ config.py
```

Not in git (in `.gitignore`); every clone makes them itself:
- `models/`: Google's model files (section 5.5)
- `probes/`: your test photos and their outputs (section 6.2)
- `.venv/`: the Python environment (section 5.6)

---

## 4. What you need

- **Arduino UNO Q (4 GB)**
- A way to get a **shell on the board**: the terminal in **Arduino App Lab** (easiest), or `adb` over USB from a laptop
- An **Android phone** with the **IP Webcam** app (by Pavel Khlebovich)
- A network both can join: the **phone's own hotspot**. Campus Wi-Fi usually blocks devices from talking to each other (client isolation), so the stream won't reach the board. The hotspot is also the demo network
- **Internet on the board for setup only**: roughly 1 GB of downloads (uv, Python packages, models). The phone's mobile data through its hotspot works
- For laptop work: Python 3.12 or 3.13 and `uv`

---

## 5. Setup

### 5.1 Install Arduino App Lab (on your laptop)

App Lab gives the board's first-time setup (password, Wi-Fi) and a terminal on the board.
- Linux: follow the [official Linux setup guide](https://docs.arduino.cc/software/app-lab/setup/linux/).
- Windows / Mac: download from arduino.cc. Installing App Lab is easy; the commands in this README are Linux commands and run **on the board**, so they're the same from any laptop.

### 5.2 Phone (IP Webcam)

1. Install **IP Webcam**.
2. **Video preferences → Video resolution → 640×480.** A bigger image only slows the board (the neural networks shrink every frame to 192 or 224 px anyway; 1080p would be 6.75× more decoding work for nothing).
3. Phone **Settings → Apps → IP Webcam → Battery saver → No restrictions**, and turn on **Autostart**. On Redmi/HyperOS, also open recent apps, long-press the IP Webcam card and tap the lock icon. Without this, the phone kills the app when the screen locks and the stream dies mid-demo.
4. Turn on the **phone hotspot**.
5. In IP Webcam, tap **Start server**.
6. After **any** change to video settings: **Stop server**, then **Start server**, or the old resolution stays.

About the address the app shows: it may be a `100.x.x.x` address. That's the phone's **mobile-data** address; it changes every time data reconnects. Use the **hotspot address** from section 5.4 instead.

### 5.3 Get a shell on the board

**Option A: App Lab (easiest).** Open App Lab, connect the board, open the terminal (bottom right). On a brand-new board, App Lab's first-time setup also sets the password and Wi-Fi.

**Option B: `adb` over USB (Ubuntu laptop).**
```bash
sudo apt install adb
# Allow your user to access the UNO Q over USB (its USB ID is 2341:0078).
# Without this, adb shows "no permissions (missing udev rules?)".
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="2341", ATTR{idProduct}=="0078", MODE="0660", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/51-arduino-unoq.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# Unplug the board, plug it back in, wait ~30 s for it to boot, then:
adb kill-server
adb devices      # must show:  <serial>   device
adb shell        # your prompt becomes arduino@<board-name>: you are now on the board
```
- `adb push <file> /home/arduino/...` copies a file laptop → board; `adb pull <path>` copies board → laptop. Both run **on the laptop**, not inside `adb shell`.
- Windows/Mac: adb setup differs (no udev rule); use App Lab instead.

**Board login:** user `arduino`. The password is on the **team WhatsApp**; never put it in the repo. On a brand-new board, the first `sudo` says the password is expired and makes you set a new one. That's the board's own account password (not your laptop's, not the hotspot's).

### 5.4 Network (on the board)

The board remembers Wi-Fi networks: once it has joined your hotspot, it rejoins automatically whenever the hotspot is on. Check:

```bash
nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes'     # which Wi-Fi is the board on?
ip route | grep default                            # "default via X.X.X.X" → X.X.X.X is the PHONE
ping -c 3 pypi.org                                 # internet works? want 0% packet loss
```

If the board isn't on your hotspot:
```bash
sudo nmcli dev wifi connect "<HOTSPOT_NAME>" password "<HOTSPOT_PASSWORD>"
```
If that fails with `key-mgmt: property is missing`, join the hotspot from App Lab instead.

**Addresses:**
- **Phone IP** = the `via` address from `ip route`. On the hotspot, the phone is the board's router (its gateway).
- **Board IP** = `hostname -I`. It's a **different** address on the same network (e.g. phone `10.138.189.35`, board `10.138.189.158`).
- `10.x.x.x`, `192.168.x.x` and `172.16–31.x.x` are private (local) addresses; `100.x.x.x` is the carrier's.

Test that the board can reach the phone's camera:
```bash
curl -I http://<PHONE_IP>:8080/shot.jpg            # expect "200 OK"
```
`Connection refused` = the phone is reachable but the IP Webcam server is off → tap **Start server**. A timeout = wrong IP or wrong network.

### 5.5 Get the code and models (on the board)

```bash
git clone https://github.com/vedsavjani/Gesture-Controlled-Robotic-Arm.git ~/gesture-arm
cd ~/gesture-arm
mkdir -p models probes

wget -O models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
python3 -m zipfile -e models/hand_landmarker.task models/
ls models
```
You must see three files:
```
hand_detector.tflite
hand_landmarker.task
hand_landmarks_detector.tflite
```
The `.task` file is a zip archive containing the two networks; we use only the two `.tflite` files.

### 5.6 Python environment (on the board)

`python3 -m venv` doesn't work on the board out of the box (Debian leaves out `python3-venv`), so we use **uv**, which makes environments itself and installs nothing system-wide.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # skip if `uv --version` already works
source $HOME/.local/bin/env                        # puts uv on PATH in this shell
uv --version

cd ~/gesture-arm
uv venv --python 3.13 .venv                        # the board's own Python 3.13 is enough
source .venv/bin/activate                          # prompt now starts with (.venv)
uv pip install -r requirements.txt
python -c "import cv2, numpy, ai_edge_litert; print('ok')"   # must print: ok
```
- **Don't install MediaPipe** (section 8 explains why).
- **Never `pip install` without the venv active**: it would go into the board's system Python, which App Lab depends on.

**In every new shell** (each new App Lab terminal or `adb shell` starts fresh):
```bash
source $HOME/.local/bin/env
cd ~/gesture-arm
source .venv/bin/activate
```

### 5.7 Camera address (automatic)

**Nothing to set on the phone hotspot.** The code finds the phone itself: on the hotspot, the phone is the board's default gateway, so `config.py` reads it from Linux's routing table (`/proc/net/route`, the same info as `ip route`) and uses `http://<gateway>:8080/video`. Each run prints which URL it picked, e.g. `Camera: http://10.138.189.35:8080/video (auto: phone = hotspot gateway)`.

This is what lets the demo start with no laptop: the phone's IP can change and nobody needs to type it.

**Override** (a different network, a laptop not on the hotspot, Windows/Mac where `/proc` doesn't exist):
```bash
export CAMERA_URL=http://<PHONE_IP>:8080/video
```
If neither works, the program stops with a clear message instead of silently retrying a wrong address.

`/video` is the continuous stream; `/shot.jpg` is a single photo.

---

## 6. Run the checks

All from `~/gesture-arm` with the venv active and the IP Webcam server running.

### 6.1 Camera check (30 s)

```bash
python check_camera.py
```
Prints one line per second: FPS, average wait of a frame on the board, frame shape.

**Pass:**
- ~30 FPS and shape `(480, 640, 3)` (if it says `(1080, 1920, 3)`, the resolution wasn't saved: section 5.2 step 6)
- During the test, **stop and start the phone server once**: FPS drops to 0, then comes back within ~5 seconds
- It ends with `done` (clean shutdown, no crash)

### 6.2 Photo check

Take four photos, one pose each. Get the pose ready, **then** run its `curl`:
```bash
curl -o probes/open.jpg http://<PHONE_IP>:8080/shot.jpg     # open hand, palm to camera, whole hand in view
curl -o probes/tilt.jpg http://<PHONE_IP>:8080/shot.jpg     # hand tilted about 45°
curl -o probes/far.jpg  http://<PHONE_IP>:8080/shot.jpg     # hand at arm's length
curl -o probes/none.jpg http://<PHONE_IP>:8080/shot.jpg     # no hand at all
ls -l probes                                                # none of them should be 0 bytes
python check_hand.py probes/open.jpg probes/tilt.jpg probes/far.jpg probes/none.jpg
```
For each photo it runs the tracker twice (the second call uses the crop built from the first, i.e. the tracking path) and prints presence, wrist and index-tip positions, and time.

**Pass:** `HAND` for the first three, `no hand` for the last. **Then look at the images**; a high score alone proves nothing (section 8.3):
- `*_out.jpg`: the red points must sit on the real finger joints
- `*_crop.jpg`: what the landmark model saw; the hand must be upright and fully inside

**How to view the images** (the board has no screen):
- With adb, on the laptop: `adb pull /home/arduino/gesture-arm/probes`
- Or serve them from the board: `python -m http.server 8000 --directory probes`, then on a phone/laptop on the **same hotspot** open `http://<BOARD_IP>:8000` (board IP from `hostname -I`, **not** the phone's IP). Ctrl+C to stop.

### 6.3 Live run

```bash
python main.py
```
One line per second. Hold your hand in view, move it, pull it out, bring it back. Stop with Ctrl+C.
```
18.2 FPS | hand in 18/18 frames | index tip 312,201
```
**Pass:** ≥15 FPS while your hand is in view; it finds the hand again after you pull it out and back.

### 6.4 Benchmark (optional)

```bash
python experiments/bench_tflite.py
```
Times each network with 1, 2 and 4 threads (random input, 5 warm-up + 50 timed runs). Expect roughly the numbers in section 2. Re-run whenever you change the thread count, the models or the board.

---

## 7. Laptop setup (no board)

For work that doesn't need the board (e.g. `mapping.py`). Tested on Linux; on Windows use **WSL**. Python 3.12 or 3.13.

```bash
# install uv first: https://docs.astral.sh/uv/
git clone https://github.com/vedsavjani/Gesture-Controlled-Robotic-Arm.git
cd Gesture-Controlled-Robotic-Arm
mkdir -p models probes
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
python -c "import cv2, numpy, ai_edge_litert; print('ok')"
```
Then download the models as in section 5.5 (use `curl -L -o ...` instead of `wget` if you don't have wget), connect the laptop to the phone hotspot, and run the same checks (on Linux the camera URL is found automatically; on Windows/Mac set `CAMERA_URL`).

Laptop FPS will be much higher than the board's. **Always confirm final numbers on the UNO Q.**

---

## 8. Why it's built this way

### 8.1 Not MediaPipe
We first ran Google's MediaPipe hand tracker on the board:
- **MediaPipe 1.2.0 crashes** with `Illegal instruction` ("compiled with lse enabled"). Its ARM build uses **LSE** instructions from the ARMv8.1 architecture; the board's Cortex-A53 is **ARMv8.0** and doesn't have them (`atomics` is missing from `/proc/cpuinfo`). It installs and even imports fine, then crashes the moment the model is created. Python 3.12 and 3.13 fail the same way.
- **MediaPipe 0.10.18 works**, but at only **~6 FPS** (165 ms per frame tracking, 217 ms searching). `top` showed the Python process at **~120% CPU**, i.e. about **one** of the four cores (the maximum is 400%); the other three sat idle. MediaPipe's Python build runs the networks essentially single-threaded.
- It also needed numpy 1.x and its own venv, which conflicted with everything else.

### 8.2 TFLite with 4 threads
The same two networks, run directly on `ai-edge-litert` with `num_threads=4`, are **~3× faster each** (`experiments/bench_tflite.py`): each layer's math is split across all four cores. The 1-thread times match MediaPipe's, which confirmed the single-core diagnosis. We then wrote the parts MediaPipe used to do for us (anchor decoding, the rotated crop, tracking), checked each step with images, and got **~18 FPS**, up from ~6. Less time per frame also means **less lag** between hand and arm, not just more FPS.

### 8.3 Palm detector input must be scaled 0..1
The input scaling wasn't documented, so we tested both on the same photos:
- **0..1:** box on the palm (score 0.94 open, 0.78 tilted, 0.84 far), and **0.05 with no hand** (correctly nothing).
- **−1..1:** score **1.00 on every photo, including the empty one**, with boxes thousands of pixels outside the image.

See `docs/palm_test/hand1_out_01.jpg` (correct) vs `hand1_out_11.jpg` (wrong: no box on the image). **A confident score is not a correct answer: always check the picture.**

### 8.4 Phone as the camera
No camera hardware, drivers or USB hub needed (the board has one USB-C port, also used for power). The stream reaches the board at ~30 FPS with ~1 ms wait, so the network is not the bottleneck. Trade-off: the phone must stay mounted, charged and unlocked; a USB webcam on a powered hub is the fallback (section 12).

### 8.5 One venv, Python 3.13
Python 3.12 was originally used only because MediaPipe doesn't support 3.13. Once MediaPipe was dropped, that reason was gone, so we use the board's own Python 3.13 and one environment.

### 8.6 Code structure
The first tracker was a single test script. It was refactored into `hand.py` (a `HandTracker` class anyone can call), `camera.py` (reconnect, timeouts, clean shutdown), and `config.py` (settings in one place), so the mapping and servo code can build on it without touching it.

The original experiment scripts (MediaPipe baseline, model inspection, single-photo palm test, the first tracker, the first camera reader) are preserved in git history at commit `af3f9e0`.

---

## 9. Pitfalls (each one cost us time)

1. **adb "no permissions"** → add the udev rule (5.3), replug, `adb kill-server`.
2. **Campus Wi-Fi blocks devices from talking to each other** → use the phone hotspot.
3. **Wrong phone IP**: IP Webcam may show the `100.x` mobile-data IP, which changes. Use the `via` address from `ip route` on the board.
4. **Phone kills IP Webcam when locked** → Battery saver: No restrictions, Autostart, lock it in recent apps.
5. **First `sudo` on a new board** makes you set a password: it's the board's `arduino` account.
6. **`python3 -m venv` fails** (no `ensurepip`) → use `uv venv`.
7. **MediaPipe 1.x on this board** → `Illegal instruction`.
8. **"Installed" ≠ "works"**: MediaPipe 1.2.0 installed and imported fine and only crashed when creating the model. Always test the real operation.
9. **Palm detector input scaling must be 0..1**; −1..1 gives confident garbage.
10. **No screen on the board**: `cv2.imshow` fails. Use `opencv-python-headless`, save images.
11. **Every new shell starts fresh**: `source $HOME/.local/bin/env`, `cd ~/gesture-arm`, `source .venv/bin/activate`.
12. **The adb session drops when the laptop sleeps or the battery is low** (the board is USB-powered from it) → keep the laptop charging.
13. **`adb push`/`pull` run on the laptop**, not in the board shell (the board has no adb).
14. **Pushing an empty file**: check `ls -l <file>` before `adb push`; 0 bytes means nothing was copied.
15. **Board clock is UTC** (5:30 behind IST); matters only when reading log timestamps.
16. **Image rotated 90°** if the phone is held sideways → mount the phone so the image is upright.
17. **Video settings changed but nothing different** → stop and start the IP Webcam server.

---

## 10. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `Connection refused` | IP Webcam server is off. Tap **Start server**; check the battery setting (5.2) |
| `curl` times out | Wrong IP, or the board isn't on the hotspot. Check `ip route`, use the hotspot |
| Phone IP changed | Nothing to do on the hotspot (found automatically). If you set `CAMERA_URL` by hand, update or `unset CAMERA_URL` |
| Connects to the wrong IP / times out | Check the `Camera: ...` line it prints. A leftover `CAMERA_URL` overrides auto-detection: `unset CAMERA_URL` |
| Frame is 1920×1080 | Resolution wasn't saved. Set 640×480, then stop and start the server |
| `0.0 FPS` for a few seconds | Stream dropped; `camera.py` retries every second. If it never recovers, restart the server |
| adb `no permissions` | Missing udev rule (5.3); replug; `adb kill-server` |
| adb device `unauthorized` / not listed | Run App Lab's first-time setup once; try another USB-C cable (some are power-only) |
| `key-mgmt: property is missing` | Join the hotspot from App Lab instead of `nmcli` |
| `sudo: password is expired` | Set the board password (5.3) |
| `command not found: uv` | `source $HOME/.local/bin/env` |
| `ensurepip is not available` | Use `uv venv`, not `python3 -m venv` |
| `ModuleNotFoundError` | Venv not active: `source .venv/bin/activate` |
| `Illegal instruction` | MediaPipe 1.x installed. Remove it; it's not used |
| Cannot find `hand_detector.tflite` | Redo section 5.5; check `ls models`; run from `~/gesture-arm` |
| A photo in `probes/` is 0 bytes | The `curl` failed; check the phone IP and that the server is on |
| No hand found, but a hand is in view | Better light, plain background, whole hand in view, palm toward the camera |
| Points in the wrong place | Check `*_crop.jpg`; don't trust the score alone |
| Hand found then lost repeatedly | Move slower, keep the whole hand in frame, avoid a second hand in view |
| Finger points look wrong but a hand is found | Hand is probably edge-on; turn the palm toward the camera |
| Coordinates negative or bigger than 640×480 | Fingertip is outside the frame; the model extrapolates. Clamp them |
| `adb: command not found` on the board | `adb` runs on the laptop |

---

## 11. Rules for the code

- **`opencv-python-headless` only.** The board has no screen: never `cv2.imshow`; save images instead.
- **Don't modify a frame returned by `camera.read()`.** It's shared with the camera thread; copy it first (`frame.copy()`).
- **Settings go in `config.py`**, never hard-coded in scripts.
- **Every loop handles a dropped stream and stops cleanly** (no background thread left running at exit).
- **Pin package versions**; don't upgrade them during the project.
- **Palm detector input stays scaled 0..1.**
- **Verify visually, not just by score**, whenever the model pipeline changes (`check_hand.py`).
- **Nothing added without a current reason**, whether it's a file, package, copy or venv; when the reason goes, it goes.
- **Experiments can be quick and dirty; anything kept becomes a clean module** with a clear interface.

---

## 12. Next steps

1. **`record.py`**: record short clips of landmarks (hand left-right, up-down, near-far, pinch) to files, so the mapping can be developed and tested on a laptop with no camera, on the same data every time.
2. **Decide the mapping** as a team, e.g. wrist x → base, wrist y → shoulder, palm size (wrist → middle-finger base) → elbow (a stand-in for distance), thumb–index pinch → gripper.
3. **`mapping.py`**: raw mapping → calibration (your hand's range → the servo's range) → dead zone (ignore tiny movements) → One Euro filter (removes jitter without much lag) → gripper with two thresholds (close below one distance, open above a larger one, so it doesn't flicker).
4. **Define the message to the MCU**: 4 angles in degrees + gripper state, ~20 updates/s max, and what to send when the hand is lost (hold position or a safe pose).
5. **End-to-end latency test** (hand moves → result printed). `camera.py` already measures the board-side wait (~1 ms); the full delay including the phone and Wi-Fi isn't measured yet.
6. **STM32 sketch**: servo control with gradual movement (interpolation), a speed limit, a safe pose if data stops.
7. **Bridge link** from Python to the sketch.
8. **Auto-start on boot**, so the demo needs no laptop to launch the program.
9. **Robustness tests**: 10-minute run (memory, overheating, FPS drop), two hands in view, dim light, demo distance.
10. **Fallback camera**: a USB webcam on a powered USB-C hub, if the phone proves unreliable.

---

## 13. Work log

| Date | Who | What |
|---|---|---|
| Oct 28 | Ved Savjani | Phone as camera: IP Webcam → Wi-Fi → OpenCV, 31 FPS on laptop |
| Oct 29 | Ved Savjani | UNO Q bring-up (adb, udev rule, hotspot, Python env), stream 30 FPS on the board; diagnosed MediaPipe 1.2.0 crash (LSE) and 0.10.18 single-core bottleneck (5.8 FPS); 4-thread TFLite benchmark (3×); first custom tracker (palm decoding, rotated crop, tracking), verified with images, ~18 FPS |
| Oct 30 | Krtin Singhvi | Re-benchmarked independently; refactored the tracker into `hand.py` (`HandTracker`); `camera.py` with reconnect, timeouts, clean shutdown, frame age; `config.py`, `main.py`, check scripts; verified Python 3.13 with a single venv; setup guide via App Lab |
| Oct 31 | Ved Savjani | Merged both into `main`, trimmed to what's required; camera URL auto-detection (no hard-coded IP); verified the merged code on the board from a fresh setup; detailed README |