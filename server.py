# server.py
# Flask-SocketIO backend for Hotspot Dashboard
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import eventlet
import time

# Import your hotspot tool modules
from hotspot_manager import start_hotspot, stop_hotspot, configure_hotspot, get_status
from network_monitor import get_connected_devices, run_bandwidth_monitor
from logs_manager import tail_logs
from console_handler import execute_command

# Use eventlet for async
eventlet.monkey_patch()

app = Flask(__name__, static_folder='.', template_folder='.')
socketio = SocketIO(app, cors_allowed_origins='*')

# Background thread for bandwidth updates
def bandwidth_thread():
    while True:
        data = run_bandwidth_monitor()  # returns dict: {'timestamps':[], 'upload':[], 'download':[]}
        socketio.emit('bandwidth-data', data)
        time.sleep(5)

# Start background thread
socketio.start_background_task(bandwidth_thread)

@app.route('/')
def index():
    return render_template('index.html')

# Connection handler\@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# Hotspot status queries\@socketio.on('get-hotspot-status')
def handle_get_status():
    status = get_status()  # e.g., 'Running' or 'Stopped'
    emit('hotspot-status', {'status': status})

# Start/Stop Hotspot\@socketio.on('start-hotspot')
def handle_start():
    result = start_hotspot()
    status = get_status()
    emit('hotspot-status', {'status': status})
    emit('console-output', {'output': f'Hotspot started: {result}'})

@socketio.on('stop-hotspot')
def handle_stop():
    result = stop_hotspot()
    status = get_status()
    emit('hotspot-status', {'status': status})
    emit('console-output', {'output': f'Hotspot stopped: {result}'})

# Configure Hotspot\@socketio.on('configure-hotspot')
def handle_configure(data):
    ssid = data.get('ssid')
    password = data.get('pass')
    result = configure_hotspot(ssid, password)
    emit('console-output', {'output': f'Configured SSID: {ssid}, Password: {password} -> {result}'})

# Device count and list\@socketio.on('get-device-count')
def handle_device_count():
    devices = get_connected_devices()
    emit('device-count', {'count': len(devices)})
    emit('devices-list', {'devices': devices})

# Console commands\@socketio.on('console-command')
def handle_console(cmd):
    output = execute_command(cmd)
    emit('console-output', {'output': output})

# View logs\@socketio.on('view-logs')
def handle_view_logs():
    lines = tail_logs()  # returns list of last n lines
    emit('logs', {'lines': lines})

# Bandwidth usage request\@socketio.on('get-bandwidth')
def handle_get_bandwidth():
    data = run_bandwidth_monitor()
    emit('bandwidth-data', data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)