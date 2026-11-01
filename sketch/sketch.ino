/*
  Gesture-controlled robotic arm: servo sketch for the Arduino UNO Q (runs on the STM32 MCU).

  Contract with the Linux side (README 3c):
    - Python calls  Bridge.call("set_angles", base, shoulder, elbow, gripper)  about 20 times/s.
      Angles are integers in degrees. The method name must match config.MCU_METHOD in config.py.
    - Each servo moves gradually toward its latest target (STEP_A degrees per 20 ms tick, never a jump).
    - If nothing arrives for 0.5 s, every servo freezes where it is. It resumes on the next call.
    - Start-up pose is HOME_A (matches config.HOME and config.GRIPPER_OPEN).

  Needs: Servo library 1.3.0 or newer (older versions do not compile for the UNO Q).
  First hardware test: set SWEEP_TEST to 1, flash, and watch each joint wiggle (no Python needed).
*/

#include <Servo.h>
#include "Arduino_RouterBridge.h"

#define SWEEP_TEST 0               // 1 = ignore the Bridge and wiggle each joint in turn

const int N = 4;                   // joints, in this order: base, shoulder, elbow, gripper

// ------------------------- hardware settings: edit these -------------------------
// UNO Q header pins D3, D5, D6, D9 are PWM pins. Wire the servo SIGNAL wires here.
// Servo POWER comes from the 5 V adapter (not the board), and the adapter GND joins the board GND.
const int PINS[N]   = {3, 5, 6, 9};

// Interim safe limits (deg). Replace with the measured limits once the arm is assembled (README task 4),
// and keep config.py's LIMITS equal to these.
const int MIN_A[N]  = {20, 20, 20, 30};
const int MAX_A[N]  = {160, 160, 160, 100};

// Start-up pose: base, shoulder, elbow = config.HOME; gripper = config.GRIPPER_OPEN (30)
const int HOME_A[N] = {90, 90, 90, 30};

// Max degrees moved per 20 ms tick: 1 deg = 50 deg/s (controller's fastest is 20 deg/s; home glide 30 deg/s).
// The gripper jumps between two angles, so it gets a larger step: 3 deg = 150 deg/s.
const int STEP_A[N] = {1, 1, 1, 3};

const int PULSE_MIN_US = 500;      // pulse for 0 deg   (typical SG90; check the datasheet if the ends look wrong)
const int PULSE_MAX_US = 2400;     // pulse for 180 deg
// ----------------------------------------------------------------------------------

const unsigned long TICK_MS    = 20;    // servo update period: 50 per second
const unsigned long TIMEOUT_MS = 500;   // freeze if no command for this long

Servo servos[N];
volatile int target[N];            // written by the Bridge handler, read by loop()
volatile unsigned long lastRx = 0; // time of the last command
volatile bool gotData = false;     // true after the first command (so the arm does not "time out" at power-up)
int current[N];                    // where each servo is now
unsigned long lastTick = 0;

// Called from Python: Bridge.call("set_angles", base, shoulder, elbow, gripper)
void setAngles(int base, int shoulder, int elbow, int gripper) {
  const int in[N] = {base, shoulder, elbow, gripper};
  for (int i = 0; i < N; i++) {
    target[i] = constrain(in[i], MIN_A[i], MAX_A[i]);   // safety clamp, even if Python sends garbage
  }
  lastRx = millis();
  gotData = true;
}

void setup() {
  for (int i = 0; i < N; i++) {
    target[i] = HOME_A[i];
    current[i] = HOME_A[i];
    servos[i].attach(PINS[i], PULSE_MIN_US, PULSE_MAX_US);
    servos[i].write(HOME_A[i]);
  }
  Bridge.begin();
  Bridge.provide("set_angles", setAngles);   // if calls do not arrive, try Bridge.provide_safe(...)
}

void loop() {
  unsigned long now = millis();
  if (now - lastTick < TICK_MS) return;
  lastTick = now;

#if SWEEP_TEST
  // 8 phases of 1.5 s: joint 0 up, joint 0 down, joint 1 up, ... joint 3 up, joint 3 down
  int phase = (now / 1500) % 8;
  int j = phase / 2;
  for (int i = 0; i < N; i++) target[i] = HOME_A[i];
  target[j] = constrain(HOME_A[j] + ((phase % 2) ? -15 : 15), MIN_A[j], MAX_A[j]);
#else
  // Watchdog: commands were arriving and then stopped -> hold position
  if (gotData && (now - lastRx > TIMEOUT_MS)) {
    for (int i = 0; i < N; i++) target[i] = current[i];
  }
#endif

  // Move each servo toward its target by at most STEP_A[i] degrees
  for (int i = 0; i < N; i++) {
    int diff = target[i] - current[i];
    if (diff == 0) continue;
    current[i] += constrain(diff, -STEP_A[i], STEP_A[i]);
    servos[i].write(current[i]);
  }
}
