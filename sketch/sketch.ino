#include <Servo.h>
#include "Arduino_RouterBridge.h"

const int N = 4;  // 0:base, 1:shoulder, 2:elbow, 3:gripper

const int PINS[N]   = {3, 5, 6, 9};
const int MIN_A[N]  = {0, 5, 5, 0};
const int MAX_A[N]  = {180, 90, 90, 130};
const int HOME_A[N] = {90, 90, 90, 30};

const int PULSE_MIN_US = 544;
const int PULSE_MAX_US = 2400;
const float US_PER_DEG = (float)(PULSE_MAX_US - PULSE_MIN_US) / 180.0f;

const unsigned long TICK_MS    = 20;     // 50 Hz
const unsigned long TIMEOUT_MS = 1500;
const float ACCEL_PER_TICK     = 1.0f;   // deg/s change per 20 ms tick
const float GRIP_STEP_US       = 25.0f;

Servo servos[N];
float currentUs[N];
float curSpeed[3] = {0.0f, 0.0f, 0.0f};
int lastWrittenUs[N];
float minUs[N], maxUs[N], homeUs[N];

volatile int cmdJoint = -1;
volatile int cmdSpeed = 0;
volatile int targetGripDeg = 30;
volatile unsigned long lastRx = 0;

unsigned long lastTick = 0;

static inline float angleToUs(int deg) {
  return PULSE_MIN_US + (float)deg * US_PER_DEG;
}

void setCmd(int joint, int speedDegS, int gripDeg) {
  cmdJoint = joint;
  cmdSpeed = constrain(speedDegS, -60, 60);
  targetGripDeg = constrain(gripDeg, MIN_A[3], MAX_A[3]);
  lastRx = millis();
}

void setup() {
  for (int i = 0; i < N; i++) {
    minUs[i] = angleToUs(MIN_A[i]);
    maxUs[i] = angleToUs(MAX_A[i]);
    homeUs[i] = angleToUs(HOME_A[i]);
    currentUs[i] = homeUs[i];
    lastWrittenUs[i] = (int)roundf(homeUs[i]);
    servos[i].writeMicroseconds(lastWrittenUs[i]);
    servos[i].attach(PINS[i], PULSE_MIN_US, PULSE_MAX_US);
  }
  targetGripDeg = HOME_A[3];
  lastTick = millis();
  Bridge.begin();
  Bridge.provide_safe("set_cmd", setCmd);
}

void loop() {
  unsigned long now = millis();
  if (now - lastTick < TICK_MS) return;
  lastTick += TICK_MS;
  if (now - lastTick >= TICK_MS) lastTick = now;

  int j = cmdJoint;
  int spd = cmdSpeed;
  unsigned long rx = lastRx;

  if (j != -1 && now >= rx && (now - rx > TIMEOUT_MS)) {
    j = -1;
    cmdJoint = -1;
  }

  float dt = (float)TICK_MS / 1000.0f;

  // 1. Arm joints (0..2): ramp velocity smoothly
  for (int i = 0; i < 3; i++) {
    float desired = 0.0f;
    if (j == i) {
      desired = (float)spd;
    } else if (j == 99) {
      float diffDeg = (homeUs[i] - currentUs[i]) / US_PER_DEG;
      float maxHome = (float)max(abs(spd), 10);
      desired = constrain(diffDeg * 3.0f, -maxHome, maxHome);
      if (fabsf(diffDeg) < 0.2f) desired = 0.0f;
    }
    float dv = desired - curSpeed[i];
    curSpeed[i] += constrain(dv, -ACCEL_PER_TICK, ACCEL_PER_TICK);
    if (fabsf(curSpeed[i]) < 0.1f && desired == 0.0f) curSpeed[i] = 0.0f;

    if (curSpeed[i] != 0.0f) {
      float nextUs = currentUs[i] + curSpeed[i] * US_PER_DEG * dt;
      if (nextUs <= minUs[i] || nextUs >= maxUs[i]) {
        currentUs[i] = constrain(nextUs, minUs[i], maxUs[i]);
        curSpeed[i] = 0.0f;
      } else {
        currentUs[i] = nextUs;
      }
    }
  }

  // 2. Gripper (joint 3)
  float gripTarget = angleToUs(targetGripDeg);
  float gDiff = gripTarget - currentUs[3];
  if (fabsf(gDiff) > 0.5f) {
    currentUs[3] += constrain(gDiff, -GRIP_STEP_US, GRIP_STEP_US);
  } else {
    currentUs[3] = gripTarget;
  }

  // 3. Write PWM only when integer microseconds change
  for (int i = 0; i < N; i++) {
    int us = (int)roundf(currentUs[i]);
    if (us != lastWrittenUs[i]) {
      lastWrittenUs[i] = us;
      servos[i].writeMicroseconds(us);
    }
  }
}