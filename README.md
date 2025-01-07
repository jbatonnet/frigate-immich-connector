This script allows to use Immich facial recognition to label persons from Frigate
It uses either Polling or MQTT to monitor for new events, upload the snapshot to Immich, trigger facial recognition and then label the event accordingly.
You can use Immich to manually tag persons, and add more pictures if you want.

To use it, you will need a Frigate instance and an Immich instance. I personally use a dedicated Immich instance not to polute my main one.

If setup with MQTT, the script can subscribe to MQTT to react to events. Else, it will poll Frigate regularly.
You can run the script or use the docker container.

You will need the following environment variables:
- **DEBUG** (optional): Enable verbose log output
- **EVENTS_LIMIT** (optional): Maximum number of events being fetched at once (default: `100`)
- **LABEL_FILTER** (optional): Filter Frigate events with this label. Set empty to disable fitlering (default: `person`)
- **CROP_SNAPSHOT** (optional): Enable croping snapshot to the Frigate detected region (default: `1`)
- **FRIGATE_ENDPOINT**: Endpoint of your Frigate instance (default: `http://127.0.0.1:5000`)
- **FRIGATE_MQTT_HOST** (optional): If specified, will subscribe to the MQTT instance (ex: `my-mqtt`)
- **FRIGATE_MQTT_PORT** (optional): Self-explanatory (default: `1883`)
- **FRIGATE_MQTT_USERNAME** (optional): Self-explanatory
- **FRIGATE_MQTT_PASSWORD** (optional): Self-explanatory
- **FRIGATE_MQTT_TOPIC** (optional): The base topic for Frigate on this MQTT instance (default: `frigate`)
- **IMMICH_ENDPOINT**: Endpoint of your Immich instance (ex: `http://my-immich`)
- **IMMICH_API_KEY**: Immich API key generated from `Account settings` > `API Keys`

Have fun!
