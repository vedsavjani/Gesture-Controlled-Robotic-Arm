# Gesture Arm: hand-tracking prototype

ECE 211P Electronics Lab project. A 4-DOF robotic arm that copies your hand.

This repo holds **prototype 1**: a phone camera sends video to the Arduino UNO Q, and the board finds 21 points on your hand in real time. No laptop is needed while it runs.

Not built yet: hand-to-angle mapping, smoothing, and the Bridge link to the STM32 servo sketch.

## What works (measured on the UNO Q)

| Item | Result |
|---|---|
| Phone stream at 640×480 | 33–37 FPS, about 1 ms wait on the board |
| Palm detector, 4 threads | about 62 ms |
| Landmark model, 4 threads | about 45 ms |
| Tracking one hand | about 48 ms per frame after the first frame |

See `notes/benchmarks.md` for the speed tests.

## Why not MediaPipe? [NOTE: Not really important]

We tested it on the board.

- MediaPipe 1.2.0 crashes ("compiled with lse enabled"). The board's CPU lacks the ARMv8.1 LSE instructions. Python 3.12 and 3.13 fail the same way.
- MediaPipe 0.10.18 works, but only at about 6 FPS.
- We run Google's two hand models directly with `ai-edge-litert` on 4 threads. This is about 3× faster per model.

## Files

| File | Job |
|---|---|
| `config.py` | Settings: camera URL, model folder, thread count |
| `camera.py` | Reads the phone stream. Keeps only the newest frame. Reconnects. Stops cleanly |
| `hand.py` | The tracker. Frame in, 21 points out (or nothing) |
| `main.py` | Live loop: camera, tracker, print FPS and fingertip |
| `check_camera.py` | 30-second camera test [NOTE: Not relevant to the main code; just a check] |
| `check_hand.py` | Photo test. Saves pictures with the points drawn [NOTE: Same thing] |
| `requirements.txt` | Three pinned packages |
| `notes/benchmarks.md` | Speed test results |

`models/` and `probes/` are in `.gitignore`. A new clone does not have them. Make them as shown below.

```text
main.py ──▶ camera.py ──▶ config.py
   └─────▶ hand.py ─────▶ config.py
```

## You need [NOTE: Just use mobile data, turn on hotspot, and connect App Lab to the same network]

- Arduino UNO Q (4 GB). A shell on it: App Lab terminal.
- An Android phone with the **IP Webcam** app.
- A network both can join. The **phone hotspot** is best. Campus Wi-Fi often blocks device-to-device traffic.
- Internet on the board for setup only (about 1 GB of downloads).

## Installing Arduino App Lab

If you are installing App Lab on Linux, please see the [official Linux setup guide](https://docs.arduino.cc/software/app-lab/setup/linux/).

If you are using Windows, ask Claude to translate the instructions below. App Lab installation should be easy, but everything else is hard.

## 1. Phone setup (IP Webcam)

1. Install **IP Webcam**.
2. Open **Video preferences**. Set **Video resolution** to **640×480**. A bigger image slows the board.
3. Turn on the **phone hotspot**.
4. In IP Webcam, tap **Start server**. The app shows an address, such as `http://192.168.x.x:8080`. [NOTE: In reality, it will be different because it is not a local IP. It would look something like `10.11.19.xx`.]
5. After any change to video settings, tap **Stop server**, then **Start server**.

## 2. Board setup

Run these on the **board shell**.

### 2.1 Join the network and check it [NOTE: This will probably already be working. Run these commands just in case. They only check that your board is actually connected to the hotspot. If App Lab shows that it is connected, skip this section.]

```bash
nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes'     # which Wi-Fi is the board on?
ip route | grep default                            # on the phone hotspot, the "via" address is the phone
ping -c 2 8.8.8.8                                  # internet works?
```

If the board is not on your hotspot:

```bash
sudo nmcli dev wifi connect "<HOTSPOT_NAME>" password "<HOTSPOT_PASSWORD>"
```

If you see `key-mgmt: property is missing`, run `nmcli connection show` and join the network from App Lab instead. The first `sudo` on a new board asks you to set a password.

Find the phone address. On the phone hotspot, it is the `via` address above. On other networks, read it in the IP Webcam app. Test it:

```bash
curl -I http://<PHONE_IP>:8080/shot.jpg            # expect "200 OK"
```

"Connection refused" means the server is off. Tap **Start server**.

### 2.2 Install uv [NOTE: Run this on the board's shell. You can start it at the bottom right in App Lab. Skip this if you already have the board I used, because it is already installed.]

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv --version
```

In a new shell, run `source $HOME/.local/bin/env` again.

### 2.3 Get the code [NOTE: Same thing as above.]

```bash
git clone https://github.com/krtin-singhvi/gesture-arm.git ~/gesture-arm
cd ~/gesture-arm
mkdir -p models probes
```

### 2.4 Download the models [NOTE: Same thing again.]

```bash
wget -O models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
python3 -m zipfile -e models/hand_landmarker.task models/
ls models
```

You must see three files:

```text
hand_detector.tflite
hand_landmarker.task
hand_landmarks_detector.tflite
```

(`.task` is a zip file. We only use the two `.tflite` files inside.)

### 2.5 Make the Python environment [NOTE: Same thing again, v3.]

```bash
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
python -c "import cv2, numpy, ai_edge_litert; print('ok')"
```

The board's own Python 3.13 is enough. Do not install MediaPipe.

In every new shell, run the following. [NOTE: Please do this to avoid corrupting global Python packages. This is on the board btw.]

```bash
cd ~/gesture-arm
source .venv/bin/activate
```

### 2.6 Set the camera address

Open `config.py` and set `CAMERA_URL`, or set it for one run:

```bash
export CAMERA_URL=http://<PHONE_IP>:8080/video
```

## 3. Run the tests

All from `~/gesture-arm` with the environment active.

### 3.1 Camera test (30 s)

```bash
python check_camera.py
```

Pass: about 30 FPS and shape `(480, 640, 3)`. During the test, stop and start the phone server once. FPS should drop to 0 and come back within about 5 seconds. It must end with `done`.

### 3.2 Photo test

Take four photos, one pose each. Run each `curl` right after you set the pose.

```bash
curl -o probes/open.jpg http://<PHONE_IP>:8080/shot.jpg     # open hand, palm to camera
curl -o probes/tilt.jpg http://<PHONE_IP>:8080/shot.jpg     # hand tilted about 45°
curl -o probes/far.jpg  http://<PHONE_IP>:8080/shot.jpg     # hand far away
curl -o probes/none.jpg http://<PHONE_IP>:8080/shot.jpg     # no hand
python check_hand.py probes/open.jpg probes/tilt.jpg probes/far.jpg probes/none.jpg
```

Pass: `HAND` for the first three, `no hand` for the last. Then look at the pictures.

```bash
hostname -I                                          # the board address
python -m http.server 8000 --directory probes        # Ctrl+C to stop
```

On a device on the same network, open `http://<BOARD_IP>:8000`. Open `open_out.jpg` and `tilt_out.jpg`. The red points must sit on the real finger joints. `*_crop.jpg` shows what the model saw. The hand must be upright and fully inside it.

[NOTE: The board IP will be the same as the phone IP, or at least it was in my case.]

### 3.3 Live run

```bash
python main.py
```

It prints one line per second. Hold your hand in view, move it, then pull it out. Stop with `Ctrl+C`.

```text
18.2 FPS | hand in 18/18 frames | index tip 312,201
```

Expected: 15 FPS or more while the hand is in view.

## Laptop setup (optional)

Use it to work on code that does not need the board. Use Python 3.12 or 3.13.

```bash
git clone https://github.com/krtin-singhvi/gesture-arm.git
cd gesture-arm
mkdir -p models probes
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Then download the models as in 2.4. Tested on Linux only. If it fails on Windows, use WSL. FPS on a laptop is higher. Confirm final numbers on the board.

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| `Connection refused` | Phone server is off. Tap **Start server**. Check the battery setting in step 1 |
| `curl` times out | Wrong IP, or the network blocks device-to-device traffic. Use the phone hotspot |
| Phone IP changed | Run `ip route \| grep default` again. Update `CAMERA_URL` |
| Frame is 1920×1080 | Video resolution was not saved. Set 640×480, then stop and start the server |
| `0.0 FPS` for a while | Stream dropped. The camera retries every second |
| `ModuleNotFoundError` | The environment is not active. Run `source .venv/bin/activate` |
| `Illegal instruction` | You installed MediaPipe 1.x. Do not use it on this board |
| Cannot find `hand_detector.tflite` | Do step 2.4 again. Check `ls models` |
| `probes/hand.jpg` is 0 bytes | The `curl` failed. Check the phone address |
| `command not found: uv` | Run `source $HOME/.local/bin/env` |
| No hand found, but a hand is in view | Better light, plain background, hand fully in view, palm toward the camera |
| Points are in the wrong place | Check `*_crop.jpg`. Do not trust the score alone |

## Rules for the code [NOTE: Not important.]

- Use `opencv-python-headless`. The board has no screen, so never use `cv2.imshow`. Save images instead.
- The palm detector input must be scaled 0 to 1. The scale −1 to 1 gives confident wrong answers.
- Do not change a frame that `camera.read()` returns. Copy it first.
- Pin package versions. Do not upgrade them during the project.

## Next steps

1. `mapping.py`: turn the 21 points into 4 angles plus a gripper value. Add a calibration, a dead-band, a One Euro filter, and two thresholds for the gripper.
2. Record short test clips of landmarks. Test the mapping on a laptop with no camera.
3. STM32 sketch: servo control, speed limit, and a safe pose if data stops.
4. Bridge link from Python to the sketch. Send at most 20 updates per second.
5. Swap the phone for a USB webcam on a powered USB-C hub.
