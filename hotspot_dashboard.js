// hotspot_dashboard.js
// Establish Socket.IO connection
const socket = io();

// --- DOM elements ---
const statusIndicatorIcon = document.querySelector('#status-indicator i');
const statusIndicatorText = document.querySelector('#status-indicator span');
const cardStatus = document.getElementById('card-hotspot-status');
const cardDevices = document.getElementById('card-device-count');
const cardUpload = document.getElementById('card-upload');
const cardDownload = document.getElementById('card-download');
const consoleOutput = document.getElementById('console-output');
const consoleInput = document.getElementById('console-input');
const sendCommandBtn = document.getElementById('send-command');
const clearConsoleBtn = document.getElementById('clear-console');

// Buttons
const buttons = document.querySelectorAll('button[data-action]');

// --- Chart.js setup ---
const ctx = document.getElementById('bandwidthChart').getContext('2d');
const bandwidthChart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      {
        label: 'Upload (Mbps)',
        data: [],
        fill: false,
        tension: 0.3
      },
      {
        label: 'Download (Mbps)',
        data: [],
        fill: false,
        tension: 0.3
      }
    ]
  },
  options: {
    responsive: true,
    scales: {
      x: { display: true, title: { display: true, text: 'Time' } },
      y: { display: true, title: { display: true, text: 'Mbps' } }
    }
  }
});

// --- Event listeners for action buttons ---
buttons.forEach(btn => {
  btn.addEventListener('click', () => {
    const action = btn.getAttribute('data-action');
    if (action === 'configure-hotspot') {
      // Prompt for SSID and password
      const ssid = prompt('Enter new SSID:', 'MyHotspot');
      const pass = prompt('Enter new Password:', 'password123');
      if (ssid && pass) {
        socket.emit('configure-hotspot', { ssid, pass });
      }
      return;
    }
    socket.emit(action);
  });
});

// --- Console controls ---
clearConsoleBtn.addEventListener('click', () => { consoleOutput.innerHTML = ''; });
sendCommandBtn.addEventListener('click', () => {
  const cmd = consoleInput.value.trim();
  if (!cmd) return;
  socket.emit('console-command', cmd);
  consoleInput.value = '';
});

// Append messages to console
function appendConsole(message) {
  const line = document.createElement('div');
  line.textContent = message;
  consoleOutput.appendChild(line);
  consoleOutput.scrollTop = consoleOutput.scrollHeight;
}

// --- Socket event handlers ---
socket.on('hotspot-status', ({ status }) => {
  cardStatus.textContent = status;
  statusIndicatorText.textContent = status;
  if (status.toLowerCase() === 'running') {
    statusIndicatorIcon.classList.add('text-green-400');
    document.getElementById('status-indicator').classList.add('active');
  } else {
    statusIndicatorIcon.classList.remove('text-green-400');
    statusIndicatorIcon.classList.add('text-gray-600');
    document.getElementById('status-indicator').classList.remove('active');
  }
});

socket.on('device-count', ({ count }) => { cardDevices.textContent = count; });
socket.on('bandwidth-data', ({ timestamps, upload, download }) => {
  bandwidthChart.data.labels = timestamps;
  bandwidthChart.data.datasets[0].data = upload;
  bandwidthChart.data.datasets[1].data = download;
  bandwidthChart.update();
});

socket.on('devices-list', ({ devices }) => {
  appendConsole('--- Connected Devices ---');
  devices.forEach(d => appendConsole(`${d.ip}\t${d.mac}\t${d.hostname}`));
});

socket.on('logs', ({ lines }) => {
  appendConsole('--- Logs ---');
  lines.forEach(l => appendConsole(l));
});

socket.on('console-output', ({ output }) => {
  appendConsole(output);
});

// Initial data fetch
socket.emit('get-hotspot-status');
socket.emit('get-device-count');
socket.emit('get-bandwidth');
