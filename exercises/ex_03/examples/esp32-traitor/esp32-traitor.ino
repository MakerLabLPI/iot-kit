// Lab 3, The Traitor's Game: reference sketch.
// Button 1 = Cooperate (C), button 2 = Betray (B). After each round the
// game master sends back the points scored (0, 1, 3 or 5); >= 3 lights
// the "good" LED, otherwise the "bad" one.
#include <WiFi.h>
#include <PubSubClient.h>

const char* SSID   = "iot-kit";
const char* PASS   = "SuperStrongPassword1234";
const char* BROKER = "192.168.50.1";

// Your nickname, shown on the board and used in the topics. Letters, digits,
// dash and underscore only: no spaces, no accents. Unique in the room.
const char* NAME = "Sev";

// Buttons between these pins and GND (internal pull-ups), LEDs between
// these pins and GND through a resistor, same pins as Lab 2b.
const int BTN_C = 32, BTN_B = 33;      // cooperate, betray
const int LED_GOOD = 25, LED_BAD = 26;

WiFiClient net;
PubSubClient client(net);

String topicJoin   = String("bme/s04/game/") + NAME + "/join";
String topicMove   = String("bme/s04/game/") + NAME + "/move";
String topicResult = String("bme/s04/game/") + NAME + "/result";

unsigned long ledOffAt = 0;

void onMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];

  int points = msg.toInt();
  digitalWrite(points >= 3 ? LED_GOOD : LED_BAD, HIGH);
  ledOffAt = millis() + 1000;
}

void setup() {
  pinMode(BTN_C, INPUT_PULLUP);
  pinMode(BTN_B, INPUT_PULLUP);
  pinMode(LED_GOOD, OUTPUT);
  pinMode(LED_BAD, OUTPUT);

  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  WiFi.setSleep(false);                // results arrive at once, as in Lab 2b

  client.setServer(BROKER, 1883);
  client.setCallback(onMessage);
  while (!client.connect(NAME)) delay(500);

  client.subscribe(topicResult.c_str());
  client.publish(topicJoin.c_str(), "hi");   // enter the pool, once
}

void loop() {
  client.loop();

  if (digitalRead(BTN_C) == LOW) {
    client.publish(topicMove.c_str(), "C");
    delay(200);                        // crude debounce (extension: millis())
  } else if (digitalRead(BTN_B) == LOW) {
    client.publish(topicMove.c_str(), "B");
    delay(200);
  }

  if (ledOffAt && millis() > ledOffAt) {
    digitalWrite(LED_GOOD, LOW);
    digitalWrite(LED_BAD, LOW);
    ledOffAt = 0;
  }
}
