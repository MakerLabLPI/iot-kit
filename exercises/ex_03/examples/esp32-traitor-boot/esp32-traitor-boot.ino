// The Traitor's Game on a bare dev board (AZ-Delivery ESP32-WROOM-32, no
// wiring): the BOOT button (GPIO 0) is Betray, the on-board blue LED
// (GPIO 2) shows the result: solid 1 s for 3 or 5 points, three quick
// blinks for 0 or 1. Everything is also printed on the Serial monitor.
// Cooperate stays on pin 32 (to GND) if you wire a button later.
#include <WiFi.h>
#include <PubSubClient.h>

const char* SSID   = "iot-kit";
const char* PASS   = "SuperStrongPassword1234";
const char* BROKER = "192.168.50.1";

// Your nickname, shown on the board and used in the topics. Letters, digits,
// dash and underscore only: no spaces, no accents. Unique in the room.
const char* NAME = "Sev";

const int BTN_C = 32;   // cooperate, optional external button to GND
const int BTN_B = 0;    // betray: the BOOT button
const int LED = 2;      // on-board blue LED

WiFiClient net;
PubSubClient client(net);

String topicJoin   = String("bme/s04/game/") + NAME + "/join";
String topicMove   = String("bme/s04/game/") + NAME + "/move";
String topicResult = String("bme/s04/game/") + NAME + "/result";

// Blink pattern: how many flashes are left and when the LED changes next
int blinksLeft = 0;
unsigned long nextToggle = 0;

void onMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];

  int points = msg.toInt();
  Serial.printf("result: %d points -> %s\n", points, points >= 3 ? "GOOD" : "bad");
  digitalWrite(LED, HIGH);
  if (points >= 3) {
    blinksLeft = 1;                    // one long flash
    nextToggle = millis() + 1000;
  } else {
    blinksLeft = 3;                    // three short ones
    nextToggle = millis() + 120;
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BTN_C, INPUT_PULLUP);
  pinMode(BTN_B, INPUT_PULLUP);
  pinMode(LED, OUTPUT);

  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  WiFi.setSleep(false);
  Serial.print("wifi ok, ip "); Serial.println(WiFi.localIP());

  client.setServer(BROKER, 1883);
  client.setCallback(onMessage);
  while (!client.connect(NAME)) delay(500);
  Serial.println("broker ok");

  client.subscribe(topicResult.c_str());
  client.publish(topicJoin.c_str(), "hi");   // enter the pool, once
  Serial.printf("joined as %s\n", NAME);
}

void loop() {
  client.loop();

  if (digitalRead(BTN_C) == LOW) {
    client.publish(topicMove.c_str(), "C");
    Serial.println("move: C");
    delay(200);                        // crude debounce
  } else if (digitalRead(BTN_B) == LOW) {
    client.publish(topicMove.c_str(), "B");
    Serial.println("move: B");
    delay(200);
  }

  // Drive the blink pattern without blocking
  if (blinksLeft > 0 && millis() > nextToggle) {
    if (digitalRead(LED) == HIGH) {
      digitalWrite(LED, LOW);
      blinksLeft--;
      nextToggle = millis() + 120;
    } else {
      digitalWrite(LED, HIGH);
      nextToggle = millis() + 120;
    }
  }
}
