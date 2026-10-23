// Morning Sloth: shows one face on the LED matrix for whatever the Linux side decided.
// The sketch only animates; all reading and judging happens in python/main.py.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

#include "faces.h"

Arduino_LED_Matrix matrix;
uint8_t frame[104];

void show(const uint8_t *face, uint8_t brightness) {
  // brightness 0-7 scales the face; 7 draws it as authored
  for (int i = 0; i < 104; i++) {
    frame[i] = (face[i] * brightness + 6) / 7;
  }
  matrix.draw(frame);
}

void blank() {
  memset(frame, 0, sizeof(frame));
  matrix.draw(frame);
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  blank();
  Bridge.begin();
}

void breathe(const uint8_t *face) {
  // a slow inhale and exhale, about four seconds
  const uint8_t levels[] = {1, 2, 3, 4, 4, 3, 2, 1, 1};
  for (uint8_t level : levels) {
    show(face, level);
    delay(450);
  }
}

void blinkAwake() {
  show(FACE_AWAKE, 7);
  delay(2600);
  show(FACE_BLINK, 7);
  delay(140);
  show(FACE_AWAKE, 7);
  delay(1200);
}

bool showBus() {
  // During bus time the Linux side sends a ready-drawn frame as 104 digits, '0' to '7'
  String bus;
  if (!Bridge.call("get_bus").result(bus) || bus.length() != 104) {
    return false;
  }
  for (int i = 0; i < 104; i++) {
    frame[i] = bus[i] - '0';
  }
  matrix.draw(frame);
  delay(4000);
  return true;
}

void loop() {
  showBus();
  String state;
  if (!Bridge.call("get_state").result(state)) {
    show(FACE_LOST, 7);
    delay(2000);
    return;
  }
  if (state == "off") {
    blank();
    delay(5000);
  } else if (state == "asleep") {
    breathe(FACE_ASLEEP);
  } else if (state == "peek") {
    show(FACE_PEEK, 5);
    delay(4000);
  } else if (state == "awake") {
    blinkAwake();
  } else {
    show(FACE_LOST, 7);
    delay(2000);
  }
}
