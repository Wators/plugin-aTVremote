# This file is part of Jeedom.
#
# Jeedom is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# Jeedom is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Jeedom. If not, see <http://www.gnu.org/licenses/>.

import subprocess
import os,re
import logging
import sys
import argparse
import time
import datetime
import signal
import json
import traceback
import globals
import threading
import asyncio
import pyatv
#from pytradfri import Gateway
#from pytradfri import color
#from pytradfri.api.libcoap_api import api_factory
try:
	from jeedom.jeedom import *
except ImportError as e:
	print("Error: importing module from jeedom folder" +str(e))
	sys.exit(1)
	
try:
    import queue
except ImportError:
    import Queue as queue

def listen():
	jeedom_socket.open()
	logging.info("Start listening...")
	threading.Thread(target=read_socket, args=('socket',)).start()
	logging.debug('Read Socket Thread Launched')
	threading.Thread(target=thread_follower, args=('thread_follower',)).start()
	logging.debug('Thread_follower Thread Launched')
	#thread.start_new_thread( ikeademon, ('ikeademon',))
	#logging.debug('Ikea Deamon Thread Launched')

def read_socket(name):
	while 1:
		try:
			global JEEDOM_SOCKET_MESSAGE
			if not JEEDOM_SOCKET_MESSAGE.empty():
				logging.debug("Message received in socket JEEDOM_SOCKET_MESSAGE")
				message = json.loads(JEEDOM_SOCKET_MESSAGE.get().decode('utf-8'))
				if message['apikey'] != globals.apikey:
					logging.error("Invalid apikey from socket : " + str(message))
					return
				logging.debug('Received command from jeedom : '+str(message['cmd']))
				if message['cmd'] == 'send':
					logging.debug('Executing action on : ' + str(message['model']) + ' with id ' + str(message['id']))
					action(message)
				if message['cmd'] == 'scanikea':
					logging.debug('Received Scan Action')
					scanner()
				if message['cmd'] == 'add':
					logging.debug('Add device : '+str(message['id']))
					globals.KNOWN_DEVICES[message['id']] = message['model']
					observe(globals.api,globals.api(globals.gateway.get_device(message['id'])))
				elif message['cmd'] == 'remove':
					logging.debug('Remove device : '+str(message['id']))
					del globals.KNOWN_DEVICES[message['id']]
		except Exception as e:
			logging.error("Exception on socket : %s" % str(e))
		time.sleep(0.3)

def scanner():
	logging.debug('Discovering ')
	devices = globals.api(*globals.api(globals.gateway.get_devices()))
	lights = [dev for dev in devices if dev.has_light_control]
	for light in lights:
		logging.debug('Found ' + str(light.name))
		globals.JEEDOM_COM.add_changes('devices::'+str(light.id),{'name' : str(light.name),'id':str(light.id),'model':str(light.device_info.model_number),\
		'serial':str(light.device_info.serial),\
		'firm':str(light.device_info.firmware_version),'power':str(light.device_info.power_source_str)});

def action(data):
	logging.debug('Executing')
	command = ''
	device = globals.api(globals.gateway.get_device(data['id']))
	if data['action'] == 'on':
		logging.debug('On')
		command = device.light_control.set_state(1)
	elif data['action'] == 'off':
		logging.debug('Off')
		command = device.light_control.set_state(0)
	elif data['action'] == 'dim':
		logging.debug('Dim ' + str(data['option']))
		command = device.light_control.set_dimmer(int(data['option']))
	elif data['action'] == 'kelvin':
		logging.debug('Kelvin ' + str(data['option']))
		command = device.light_control.set_kelvin_color(int(data['option']))
	elif data['action'] == 'color':
		logging.debug('Color ' + str(data['option']))
		r = int(data['option'][0:2], 16)
		g = int(data['option'][2:4], 16)
		b = int(data['option'][4:6], 16)
		logging.debug('Color RGB is ' + str(r)+','+str(g)+','+str(b))
		xycolor=color.rgb_to_xyY(r,g,b)
		command = device.light_control.set_xy_color(xycolor['5709'],xycolor['5710'])
	if command != '':
		globals.api(command)

def observe(api, device):
	def callback(updated_device):
		light = updated_device.light_control.lights[0]
		logging.debug("Received message for: %s" % light)
		globals.JEEDOM_COM.add_changes('devices::'+str(updated_device.id),{'name' : str(updated_device.name),'id':str(updated_device.id),'model':str(updated_device.device_info.model_number),\
		'serial':str(updated_device.device_info.serial),\
		'firm':str(updated_device.device_info.firmware_version),'power':str(updated_device.device_info.power_source_str),\
		'state' : str(light.state),'dimInfo' : str(light.dimmer), 'kelvinInfo' : str(light.kelvin_color) , 'colorInfo' : '#'+str(light.hex_color)});
	
	def err_callback(err):
		logging.debug(err)
	
	def worker():
		api(device.observe(callback, err_callback, duration=0))
	exists = 0
	for thread in threading.enumerate():
		if  thread.name == 'ikea_'+str(device.id):
			exists =1
	if exists == 0:
		threading.Thread(target=worker, name='ikea_'+str(device.id), daemon=True).start()
		logging.debug('Sleeping to start observation task')
		time.sleep(0.1)
	
def thread_follower(name):
	while True:
		try:
			for key in globals.KNOWN_DEVICES.keys():
				exists = 0
				for thread in threading.enumerate():
					if  thread.name == 'ikea_'+key:
						exists =1
				if exists == 0:
					logging.debug('Thread for ' + key + ' doesn\'t exists anymore relaunching')
					observe(globals.api,globals.api(globals.gateway.get_device(key)))
			time.sleep(0.1)
		except Exception as e:
			logging.debug(str(e))


def handler(signum=None, frame=None):
	logging.debug("Signal %i caught, exiting..." % int(signum))
	shutdown()
	
def shutdown():
	logging.debug("Shutdown")
	logging.debug("Removing PID file " + str(globals.pidfile))
	try:
		os.remove(globals.pidfile)
	except:
		pass
	try:
		jeedom_socket.close()
	except:
		pass
	logging.debug("Exit 0")
	sys.stdout.flush()
	os._exit(0)
	
globals.log_level = "error"
globals.socketport = 61025
globals.sockethost = '127.0.0.1'
globals.pidfile = '/tmp/aTVremote.pid'
globals.apikey = ''
globals.callback = ''
globals.cycle = 0.3;

parser = argparse.ArgumentParser(description='aTVremoted Daemon for Jeedom plugin')
parser.add_argument("--device", help="Device", type=str)
parser.add_argument("--loglevel", help="Log Level for the daemon", type=str)
parser.add_argument("--pidfile", help="Value to write", type=str)
parser.add_argument("--callback", help="Value to write", type=str)
parser.add_argument("--apikey", help="Value to write", type=str)
parser.add_argument("--socketport", help="Socket Port", type=str)
parser.add_argument("--sockethost", help="Socket Host", type=str)
parser.add_argument("--cycle", help="Cycle to send event", type=str)
args = parser.parse_args()

if args.device:
	globals.device = args.device
if args.loglevel:
	globals.log_level = args.loglevel
if args.pidfile:
	globals.pidfile = args.pidfile
if args.callback:
	globals.callback = args.callback
if args.apikey:
	globals.apikey = args.apikey
if args.cycle:
	globals.cycle = float(args.cycle)
if args.socketport:
	globals.socketport = args.socketport
if args.sockethost:
	globals.sockethost = args.sockethost

globals.socketport = int(globals.socketport)
globals.cycle = float(globals.cycle)

jeedom_utils.set_log_level(globals.log_level)
logging.info('Start aTVremoted')
logging.info('Log level : '+str(globals.log_level))
logging.info('Socket port : '+str(globals.socketport))
logging.info('Socket host : '+str(globals.sockethost))
logging.info('PID file : '+str(globals.pidfile))
logging.info('Apikey : '+str(globals.apikey))
logging.info('Callback : '+str(globals.callback))
logging.info('Cycle : '+str(globals.cycle))
signal.signal(signal.SIGINT, handler)
signal.signal(signal.SIGTERM, handler)
try:
	jeedom_utils.write_pid(str(globals.pidfile))
	globals.JEEDOM_COM = jeedom_com(apikey = globals.apikey,url = globals.callback,cycle=globals.cycle)
	if not globals.JEEDOM_COM.test():
		logging.error('Network communication issues. Please fix your Jeedom network configuration.')
		shutdown()
	jeedom_socket = jeedom_socket(port=globals.socketport,address=globals.sockethost)
	globals.api = api_factory(globals.gatewayip, globals.gatewaycode)
	globals.gateway = Gateway()
	listen()
except Exception as e:
	logging.error('Fatal error : '+str(e))
	logging.debug(traceback.format_exc())
	shutdown()
