import requests
import os
import json
import dotenv
import time
import re

from datetime import datetime
from dateutil import parser

import paho.mqtt.client as paho


dotenv.load_dotenv()

DEBUG = os.getenv('DEBUG', default = '')
DEBUG = not not DEBUG

FRIGATE_ENDPOINT = os.getenv('FRIGATE_ENDPOINT', default = 'http://127.0.0.1:5000')
FRIGATE_USERNAME = os.getenv('FRIGATE_USERNAME', default = '')
FRIGATE_PASSWORD =  os.getenv('FRIGATE_PASSWORD', default = '')

FRIGATE_MQTT_HOST = os.getenv('FRIGATE_MQTT_HOST', default = '')
FRIGATE_MQTT_PORT = os.getenv('FRIGATE_MQTT_PORT', default = '1883')
FRIGATE_MQTT_USERNAME = os.getenv('FRIGATE_MQTT_USERNAME', default = '')
FRIGATE_MQTT_PASSWORD = os.getenv('FRIGATE_MQTT_PASSWORD', default = '')
FRIGATE_MQTT_TOPIC = os.getenv('FRIGATE_MQTT_TOPIC', default = 'frigate')

IMMICH_ENDPOINT = os.getenv('IMMICH_ENDPOINT', default = 'http://127.0.0.1:2283')
IMMICH_API_KEY = os.getenv('IMMICH_API_KEY', default = '')


def log(message):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' [frigate-immich-connector] ' + message, flush = True)

camera_albums = {}

def check_frigate():

    ################
    # Check Frigate version
    # - https://docs.frigate.video/integrations/api/#get-apiversion

    log('Checking connection with Frigate...')

    version_response = requests.get(f'{FRIGATE_ENDPOINT}/api/version')
    version = version_response.text

    log(f'  Frigate is version {version}')

def check_immich():

    log('Checking connection with Immich...')

    ################
    # Check Immich connection and version
    # - https://immich.app/docs/api/get-about-info

    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }

    about_response = requests.get(f'{IMMICH_ENDPOINT}/api/server/about', headers = headers)
    about = about_response.json()

    version = about['version']

    log(f'  Immich is version {version}')

def initialize():
    global camera_albums
    
    ################
    # Get Frigate configuration
    # - https://docs.frigate.video/integrations/api/#get-apiconfig

    config_response = requests.get(f'{FRIGATE_ENDPOINT}/api/config')
    config = config_response.json()

    mqtt = config['mqtt']['enabled']

    cameras = config['cameras']
    cameras = [ c for c in cameras.values() if c['enabled'] and c['detect']['enabled'] ]

    log(f'Found {len(cameras)} cameras...')
    for camera in cameras:
        log(f'- {camera["name"]}')

    ################
    # Find or create the camera albums
    # - https://immich.app/docs/api/get-all-albums
    # - https://immich.app/docs/api/create-album

    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }

    albums_response = requests.get(f'{IMMICH_ENDPOINT}/api/albums', headers = headers)
    albums = albums_response.json()

    camera_albums = [ (c['name'], next(iter([ a for a in albums if a['description'] == c['name'] ]), None)) for c in cameras ]
    camera_albums = dict(camera_albums)

    # Create albums if needed
    for camera, album in camera_albums.items():

        if not album:

            camera_clean_name = camera
            camera_clean_name = camera_clean_name.replace('_', ' ')
            camera_clean_name = re.sub('camera', '', camera_clean_name, flags = re.I)
            camera_clean_name = camera_clean_name.strip().title()
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'x-api-key': IMMICH_API_KEY
            }

            payload = {
                'albumName': 'Frigate - ' + camera_clean_name,
                'description': camera
            }
            
            album_response = requests.post(f'{IMMICH_ENDPOINT}/api/albums', headers = headers, data = json.dumps(payload))
            album = album_response.json()

            camera_albums[camera] = album

            log(f'Created album {album["name"]} ({album["id"]}) for camera {camera}')

def subscribe_mqtt():

    def mqtt_on_connect(client, userdata, flags, reason_code, properties):
        client.subscribe(f'{FRIGATE_MQTT_TOPIC}/events')
        
        if DEBUG:
            log('Connected to MQTT successfully')

    def mqtt_on_connect_fail(client, userdata):
        log('MQTT connection failed')
        exit(1)

    def mqtt_on_log(client, userdata, level, buf):
        if DEBUG:
            log(buf)

    def mqtt_on_message(client, userdata, msg):
        payload = json.loads(msg.payload)
        event = payload['after']

        if DEBUG:
            log('Received MQTT event')

        process_event(event)

    client = paho.Client(protocol = paho.MQTTv5)
    client.on_connect = mqtt_on_connect
    client.on_connect_fail = mqtt_on_connect_fail
    client.on_message = mqtt_on_message
    client.on_log = mqtt_on_log

    if FRIGATE_MQTT_USERNAME:
        client.username_pw_set(FRIGATE_MQTT_USERNAME, FRIGATE_MQTT_PASSWORD)

    client.connect(FRIGATE_MQTT_HOST, int(FRIGATE_MQTT_PORT))
    client.loop_start()

def fetch_events():
    global camera_albums

    log('')

    for camera, album in camera_albums.items():

        ################
        # Get the last asset's date
        # - https://immich.app/docs/api/get-album-info

        headers = {
            'Accept': 'application/json',
            'x-api-key': IMMICH_API_KEY
        }

        album_response = requests.get(f'{IMMICH_ENDPOINT}/api/albums/{album["id"]}', headers = headers)
        album = album_response.json()

        assets = sorted(album['assets'], reverse = True, key = lambda a: a['fileModifiedAt'])
        last_asset = next(iter(assets), None)

        last_check = 0
        if last_asset:
            last_check = last_asset['fileModifiedAt']
            last_check = parser.parse(last_check)
            last_check = last_check.timestamp()

        log(f'Checking new events for {camera} after {datetime.fromtimestamp(last_check)}...')

        ################
        # List events from Frigate
        # - https://docs.frigate.video/integrations/api/#get-apievents

        events_response = requests.get(f'{FRIGATE_ENDPOINT}/api/events?has_snapshot=1&cameras={camera}&after={last_check + 0.001}')
        events = events_response.json()

        if len(events) == 0:
            log('  No new events')
            continue

        events = list(events)
        events.reverse()
        
        for event in events:
            process_event(event)

def process_event(event):
    global camera_albums

    camera = event['camera']
    album = camera_albums[camera]

    event_id = event['id']
    event_start_time = event['start_time']

    log(f'Processing event {event_id} ({event_start_time})...')


    ################
    # Download snapshot from Frigate
    # - https://docs.frigate.video/integrations/api#get-apieventsidsnapshotjpg

    event_snapshot_response = requests.get(f'{FRIGATE_ENDPOINT}/api/events/{event_id}/snapshot.jpg')
    event_snapshot = event_snapshot_response.content


    ################
    # Upload to Immich
    # - https://immich.app/docs/api/upload-asset/
    # - https://immich.app/docs/guides/python-file-upload
    # - https://immich.app/docs/api/add-assets-to-album

    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }

    data = {
        'deviceAssetId': event_id,
        'deviceId': 'Frigate',
        'fileCreatedAt': datetime.fromtimestamp(event_start_time),
        'fileModifiedAt': datetime.fromtimestamp(event_start_time)
    }

    files = [
        ('assetData', (event_id + '.jpg', event_snapshot, 'application/octet-stream'))
    ]

    upload_response = requests.post(f'{IMMICH_ENDPOINT}/api/assets', headers = headers, data = data, files = files)
    upload = upload_response.json()

    asset_id = upload['id']

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }

    data = {
        'ids': [ asset_id ]
    }

    add_to_album_response = requests.put(f'{IMMICH_ENDPOINT}/api/albums/{album["id"]}/assets', headers = headers, data = json.dumps(data))
    add_to_album = add_to_album_response.json()


    ################
    # Trigger face recognition
    # - https://immich.app/docs/api/run-asset-jobs

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }

    data = {
        'name': 'refresh-faces',
        'assetIds': [ asset_id ]
    }

    asset_job_response = requests.post(f'{IMMICH_ENDPOINT}/api/assets/jobs', headers = headers, data = json.dumps(data))
    status = asset_job_response.status_code


    ################
    # Wait for job completion
    # - https://immich.app/docs/api/get-all-jobs-status

    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }

    done = False

    while not done:
        jobs_status_response = requests.get(f'{IMMICH_ENDPOINT}/api/jobs', headers = headers)
        jobs_status = jobs_status_response.json()

        done = not jobs_status['faceDetection']['queueStatus']['isActive']


    ################
    # Get people information
    # - https://immich.app/docs/api/get-asset-info

    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }

    asset_response = requests.get(f'{IMMICH_ENDPOINT}/api/assets/{asset_id}', headers = headers)
    asset = asset_response.json()

    asset_people = asset['people']


    ################
    # Add sublabel to Frigate event
    # - https://docs.frigate.video/integrations/api#post-apieventsidsub_label

    for person in asset_people:

        person_name = person['name']

        log(f'  Found {person_name}')

        data = {
            'subLabel': person_name,
            'subLabelScore': 1
        }

        sublabel_response = requests.post(f'{FRIGATE_ENDPOINT}/api/events/{event_id}/sub_label', data = json.dumps(data))
        sublabel = sublabel_response.json()


def main():

    check_frigate()
    check_immich()

    log('')

    initialize()

    # If we have MQTT, fetch once and wait for events
    if FRIGATE_MQTT_HOST:
        fetch_events()
        subscribe_mqtt()

        while True:
            time.sleep(300)
            fetch_events()

    # If we don't have MQTT, let's poll Frigate regularly
    else:
        while True:
            fetch_events()
            time.sleep(5)


if __name__ == '__main__':
    main()
