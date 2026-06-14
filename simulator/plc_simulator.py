import json
import random
import time
import paho.mqtt.client as mqtt

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

client.connect("mosquitto", 1883, 60)

while True:

    payload = {
        "temperature": random.randint(60, 95),
        "pressure": random.randint(15, 35),
        "humidity": random.randint(30, 70),
        "motor_rpm": random.randint(1000, 3000),
        "vibration": round(random.uniform(0.5, 5.0), 2),
        "power_kw": round(random.uniform(50, 150), 2)
    }

    client.publish(
        "factory/plc1",
        json.dumps(payload)
    )

    print(payload)

    time.sleep(5)