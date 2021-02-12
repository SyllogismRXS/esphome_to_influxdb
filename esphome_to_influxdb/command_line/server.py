import sys
import argparse
import yaml
import logging
from datetime import datetime

import aioesphomeapi
import asyncio

from influxdb import InfluxDBClient

async def process_line_protocols(host, port, database, line_protocol_queue):
    """ Setup the InfluxDB client and process the line protocol queue"""
    # Connect to the database
    client = InfluxDBClient(host=host, port=port)
    client.create_database(database)
    client.switch_database(database)

    logger = logging.getLogger('write_to_influxdb')

    while True:
        lines = await line_protocol_queue.get()

        logger.debug('Writing lines...')
        logger.debug(lines)

        client.write_points(lines, protocol='line')

def make_influx_safe(my_str):
    return my_str.replace(' ', '\ ')

def create_line(info, data):
    """ Write sensor measurements to InfluxDB"""
    device_name = make_influx_safe(info['DeviceInfo'].name)
    sensor_name = make_influx_safe(info['entity_map'][data.key].name)
    unit_of_measurement = make_influx_safe(info['entity_map'][data.key].unit_of_measurement)
    unique_id = make_influx_safe(info['entity_map'][data.key].unique_id)
    measurement = data.state
    return f"{sensor_name},device={device_name},unit_of_measurement={unit_of_measurement},unique_id={unique_id}  state={measurement}"

async def create_lines(info_queue, data_queue, line_protocol_queue):
    """ Setup the InfluxDB client and process sensor measurements from the queue"""
    # Get the device info before consuming data
    info = await info_queue.get()

    while True:
        data = await data_queue.get()
        line_protocol_queue.put_nowait(create_line(info, data))

async def get_info(client):
    """Get the device info and create a map of the entities."""
    # Show device details
    device_info = await client.device_info()

    info = {}
    info['DeviceInfo'] = device_info

    # List all entities of the device
    entities, services = await client.list_entities_services()

    # Create a map of the entity based on its key
    entity_map = { entity.key: entity for entity in entities }
    info['entity_map'] = entity_map

    return info

async def process_esphome(name, port, password, info_queue, data_queue):
    """Connect to an ESPHome device and wait for state changes."""
    loop = asyncio.get_running_loop()
    client = aioesphomeapi.APIClient(loop, name, port, password)

    await client.connect(login=True)

    # Get the info from the device
    info = await get_info(client)

    # Send the info the database writing queue
    await info_queue.put(info)

    def change_callback(state):
        data_queue.put_nowait(state)

    # Subscribe to the state changes
    await client.subscribe_states(change_callback)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--settings', default='settings.yaml', help='Path to settings file.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output.')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    log_main = logging.getLogger('esphome_to_influxdb')

    # Load the settings file
    with open(args.settings) as f:
        settings = yaml.load(f, Loader=yaml.FullLoader)

    log_main.debug('Settings...')
    log_main.debug(settings)

    esphome_instances = settings['esphome']

    info_queue = asyncio.Queue()
    data_queue = asyncio.Queue()
    line_protocol_queue = asyncio.Queue()

    loop = asyncio.get_event_loop()
    try:
        # There is one InfluxDB instance that processes a queue of line
        # protocols to write to the database.
        asyncio.ensure_future(process_line_protocols(
            settings['influxdb']['host'],
            settings['influxdb']['port'],
            settings['influxdb']['database'],
            line_protocol_queue
        ))

        # There are possibly multiple instances of esphome clients subscribing
        # to changes from multiple devices
        for esphome in esphome_instances:
            # The routine reads the measurements (data_queue), converts the
            # measurements into line protocols, and sends the lines to the
            # InfluxDB client routine.
            asyncio.ensure_future(create_lines(
                info_queue, data_queue, line_protocol_queue))

            # The routine that subscribes to changes from devices and sends the
            # measurements via the data queue to the next routine.
            asyncio.ensure_future(process_esphome(
                esphome['host'],
                esphome['port'],
                esphome['password'],
                info_queue, data_queue))

        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

if __name__ == '__main__':
    sys.exit(main())
