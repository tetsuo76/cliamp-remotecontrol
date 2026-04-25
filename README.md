# cliamp-remotecontrol v1.1
A basic web UI/remote control for the [cliamp](https://github.com/bjarneo/cliamp) music player

![scrobbling in cliamp](https://github.com/tetsuo76/cliamp-remotecontrol/blob/main/screenshot.jpg?raw=true)

## Instructions:

- Just run the python app `python cliamp-remotecontrol.py` (tested with Python v3.10.10 on cliamp v1.37.3).

- Then access the web UI at `http://locahost:9000` (or your LAN IP if you are accessing it using a different device.

## Requirements
- Python 3.10+ recommended
- cliamp installed and running
- A working cliamp Unix socket at ~/.config/cliamp/cliamp.sock

## Requiremtns (for Listen feature)
- ffmpeg installed
- pactl installed
- PulseAudio or PipeWire with monitor sources enabled
- A modern web browser

## Notes
- The remote control UI works as long as cliamp is running and reachable.
- The Listen feature additionally requires that the active cliamp output device has a matching monitor source, such as:
  - alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo.monitor
  - alsa_output.pci-0000_00_1f.3.analog-stereo.monitor
- You can change the default port in `cliamp-remotecontrol.py` or enable debugging messages by setting `DEBUG = True`.