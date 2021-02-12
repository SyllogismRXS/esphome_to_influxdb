from setuptools import setup

setup(name='esphome_to_influxdb',
      version='0.1',
      description='Subscribes to esphome devices and writes data to influxdb',
      url='http://www.kevindemarco.com',
      author='Kevin DeMarco',
      author_email='kevin@kevindemarco.com',
      license='BSD',
      packages=['esphome_to_influxdb'],
      install_requires=[
          'influxdb',
          'argparse',
          'aioesphomeapi',
          'pyyaml'
      ],
      entry_points = {
          'console_scripts': ['esphome_to_influxdb_server=esphome_to_influxdb.command_line.server:main']
      },
      zip_safe=False)
