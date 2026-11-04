// Minimal ESP32 + PubSubClient sketch for the iot-kit broker.
// Library: "PubSubClient" by Nick O'Leary (Arduino Library Manager).

#include <WiFi.h>
#include <PubSubClient.h>

const char *WIFI_SSID = "CHANGE-ME";
const char *WIFI_PASS = "CHANGE-ME";

// "broker.lan" works too, the kit's DNS resolves it to this address.
const char *MQTT_HOST = "192.168.50.1";
const uint16_t MQTT_PORT = 1883;

WiFiClient net;
PubSubClient mqtt(net);
String clientId;

void onMessage(char *topic, byte *payload, unsigned int length) {
  Serial.printf("[%s] ", topic);
  Serial.write(payload, length);
  Serial.println();
}

void connectMqtt() {
  while (!mqtt.connected()) {
    Serial.print("MQTT connecting... ");
    if (mqtt.connect(clientId.c_str())) {
      Serial.println("ok");
      mqtt.subscribe("test/#");
    } else {
      Serial.printf("failed, state=%d, retry in 2 s\n", mqtt.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi ok, IP %s\n", WiFi.localIP().toString().c_str());

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

  static unsigned long last = 0;
  if (millis() - last > 5000) {
    last = millis();
    String topic = "test/" + clientId + "/uptime";
    mqtt.publish(topic.c_str(), String(millis() / 1000).c_str());
  }
}
