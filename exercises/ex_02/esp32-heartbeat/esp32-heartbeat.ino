// Heartbeat and breath, reference solution (Lab 2b): one LED flashes with
// the heart shown on the board (exercises/ex_02/index.html), another lights
// up with the breath, and the heart never stops while the breath LED is on.
//
// The page publishes one message per beat on "bme/s04/heartbeat" and one
// per breath on "bme/s04/breath". The payloads are the current rates per
// minute, as text ("72", "12"); this sketch does not need them.
//
// Library: "PubSubClient" by Nick O'Leary (Arduino Library Manager).

#include <WiFi.h>
#include <PubSubClient.h>

const char *WIFI_SSID = "iot-kit";
const char *WIFI_PASS = "SuperStrongPassword1234";

const char *MQTT_HOST = "192.168.50.1";
const uint16_t MQTT_PORT = 1883;
const char *HEARTBEAT_TOPIC = "bme/s04/heartbeat";
const char *BREATH_TOPIC = "bme/s04/breath";

// LEDs between these pins and GND, through a resistor
const int HEART_PIN = 25;
const int BREATH_PIN = 26;
const unsigned long HEART_MS = 100;
const unsigned long BREATH_MS = 2000;

WiFiClient net;
PubSubClient mqtt(net);
String clientId;

// When each LED must switch off again (0: it is off)
unsigned long heartOff = 0;
unsigned long breathOff = 0;

void onMessage(char *topic, byte *payload, unsigned int length) {
  // Switch the LED on and remember when to switch it off. Never delay()
  // here: while this function runs, mqtt.loop() does not, and the messages
  // of the other rhythm wait.
  if (strcmp(topic, HEARTBEAT_TOPIC) == 0) {
    digitalWrite(HEART_PIN, HIGH);
    heartOff = millis() + HEART_MS;
  } else if (strcmp(topic, BREATH_TOPIC) == 0) {
    digitalWrite(BREATH_PIN, HIGH);
    breathOff = millis() + BREATH_MS;
  }
}

void connectMqtt() {
  while (!mqtt.connected()) {
    Serial.print("MQTT connecting... ");
    if (mqtt.connect(clientId.c_str())) {
      Serial.println("ok");
      mqtt.subscribe(HEARTBEAT_TOPIC);
      mqtt.subscribe(BREATH_TOPIC);
    } else {
      Serial.printf("failed, state=%d, retry in 2 s\n", mqtt.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(HEART_PIN, OUTPUT);
  pinMode(BREATH_PIN, OUTPUT);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi ok, IP %s\n", WiFi.localIP().toString().c_str());

  // By default the radio sleeps between two beacons of the access point and
  // gets its messages up to a few 100 ms late, each board differently.
  // Awake all the time, the boards beat together.
  WiFi.setSleep(false);

  // Client ids must be unique on the broker: derive it from the MAC.
  clientId = "esp32-" + WiFi.macAddress();
  clientId.replace(":", "");

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
}

void loop() {
  if (!mqtt.connected()) {
    connectMqtt();
  }
  mqtt.loop();

  // Switch the LEDs off when their time is up. (long) handles millis()
  // wrapping around after 49 days.
  unsigned long now = millis();
  if (heartOff && (long)(now - heartOff) >= 0) {
    digitalWrite(HEART_PIN, LOW);
    heartOff = 0;
  }
  if (breathOff && (long)(now - breathOff) >= 0) {
    digitalWrite(BREATH_PIN, LOW);
    breathOff = 0;
  }
}
