#!/usr/bin/env python3

# Requires python3-hamlib (Debian/Ubuntu package name)
#
# you need to create the config directory and copy/edit the file
CONFIG_FILE = "~/.config/cloudlog-sync/config.ini"

import Hamlib
import urllib3
import requests
from datetime import datetime
from datetime import timezone
import sys
import signal
import time
import configparser
from pathlib import Path

rig = None
config = None

def graceful_exit(signal_number, stack_frame):
    closeHamlib()
    print("Stopping syncing Cloudlog. Received signal {}".format(signal.Signals(signal_number).name))
    sys.exit(0)

def readConfig():
    global config
    config = configparser.ConfigParser()
    config.read(Path(CONFIG_FILE).expanduser())
    if config['DEFAULT'].getboolean('disable_InsecureRequestWarning'):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if config['DEFAULT'].getboolean('disable_SubjectAltNameWarning'):
        urllib3.disable_warnings(urllib3.exceptions.SubjectAltNameWarning)
    
def startHamlib():
    Hamlib.rig_set_debug(Hamlib.RIG_DEBUG_NONE)
    global rig
    rig = Hamlib.Rig(int(config['HAMLIB']['model']))
    rig.set_conf("rig_pathname",config['HAMLIB']['path'])
    rig.set_conf("retry", "5")
    rig.open()
    if rig.error_status != 0:
        print("status(str):\t\t%s" % Hamlib.rigerror(rig.error_status))
        sys.exit(1)
    if config['DEFAULT'].getboolean('debug'):
        # rig.caps.rig_model
        print("Hamlib correctly connected to radio {} {} with path {}".format(rig.caps.mfg_name, rig.caps.model_name, config['HAMLIB']['path']))

def closeHamlib():
    rig.close()

def syncCloudlog():
    "get data from Hamlib and sync with cloudlog instance"

    rig_freq=0
    rig_old_freq=-1
    rig_mode=0
    rig_old_mode=-1
    rig_power=0
    rig_old_power=-1

    try:
        verify_tls = config['CLOUDLOG'].getboolean('verifyCert')
    except ValueError as err:
        verify_tls = Path(config['CLOUDLOG']['verifyCert']).expanduser()

    while True:

        rig_freq=int(rig.get_freq())
        (rig_mode, rig_width) = rig.get_mode()
        rig_power=int(rig.get_level_f(Hamlib.RIG_LEVEL_RFPOWER)*100)

        if rig.error_status != 0:
            # probably the connection is closed; try to restart
            closeHamlib()
            startHamlib()

        if rig_freq != rig_old_freq or rig_mode != rig_old_mode or rig_power != rig_old_power:
            rig_old_freq = rig_freq
            rig_old_mode = rig_mode
            rig_old_power = rig_power
            mode_str = Hamlib.rig_strrmode(rig_mode)
            timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M")
            response = requests.post(config['CLOUDLOG']['url'], timeout=5, verify=verify_tls,
                                     json={
                                         'key': config['CLOUDLOG']['api_key'],
                                         'radio': config['CLOUDLOG']['name'],
                                         'frequency': rig_freq,
                                         'mode': mode_str,
                                         'power': rig_power,
                                         'timestamp': timestamp
                                     }
                                     )
            if config['DEFAULT'].getboolean('debug'):
                print(f"Update Cloudlog radio {config['CLOUDLOG']['name']} with frequency {rig_freq}, mode {mode_str} and RF power {rig_power} ")
            if response.status_code != 200:
                print(f"Error syncing with Cloudlog. Error: {response}")

        time.sleep(int(config['DEFAULT']['update_frequency']))

if __name__ == '__main__':
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    print('Starting up Cloudlog sync ...')
    readConfig()
    startHamlib()
    print('Startup complete')
    syncCloudlog()
    closeHamlib()
