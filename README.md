# PiKVM Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adamoutler&repository=pikvm-homeassistant-integration&category=Integration)

This is a custom integration for Home Assistant to monitor and control PiKVM devices.

## Features

- Monitor CPU temperature
- Monitor fan speed
- Check device throttling status
- Monitor MSD status and storage
- Track additional PiKVM services (IPMI, Janus, VNC, Webterm)

## Installation

### Automagic Installation

Use the Home Assitant My link to add this repository to HACS.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adamoutler&repository=pikvm-homeassistant-integration&category=Integration)

### HACS (Home Assistant Community Store)

1. Ensure that HACS is installed and configured in your Home Assistant setup. If not, follow the instructions [here](https://hacs.xyz/docs/installation/manual).
2. Go to the HACS panel in Home Assistant.
3. Click on the "Integrations" tab.
4. Click on the three dots in the top right corner and select "Custom repositories".
5. Add this repository URL: `https://github.com/adamoutler/pikvm-homeassistant-integration` and select "Integration" as the category.
6. Find "PiKVM Integration" in the list and click "Install".
7. Restart Home Assistant.

### Manual Installation

1. Download the `custom_components` folder from this repository.
2. Copy the `pikvm` folder into your Home Assistant `custom_components` directory.
3. Restart Home Assistant.

## Configuration

### Adding PiKVM Integration via Home Assistant UI

1. Go to the Home Assistant UI.
2. Navigate to **Configuration** -> **Devices & Services**.
3. Click the **Add Integration** button.
4. Search for "PiKVM".
5. Follow the setup wizard to configure your PiKVM device.

### Configuration Options

- **URL**: The URL or IP address of your PiKVM device.
- **Username**: The username to authenticate with your PiKVM device (default: `admin`).
- **Password**: The password to authenticate with your PiKVM device (default: `admin`).
- **2FA Secret**: The secret token used to setup 2FA, if it is enabled (if not, leave blank). It can be obtained running this command: `kvmd-totp show`. Refer to the (PiKVM documentation)[https://docs.pikvm.org/auth/#two-factor-authentication] for setup instructions.

## Usage

Once the PiKVM integration is added and configured, you will have several sensors available in Home Assistant to monitor the status and health of your PiKVM device. These sensors will include CPU temperature, fan speed, MSD status, and more.

## Development

### Setting up the Development Environment

1. **Clone the Repository**: For development purposes, git clone this repository to your `/config` folder.
   ```sh
   git clone https://github.com/yourusername/pikvm-homeassistant /config/pikvm-homeassistant
   ```
2. Open with VSCode: Open the repository with VSCode.
3. Make Your Changes: Make your changes in the repository.
4. Restart Home Assistant: Restart Home Assistant with F1 -> Tasks: Restart HA.
5. View Logs: View logs with F1 -> Tasks: logs.
6.  Enable Debug Logging: For higher detail in logs, enable debug logging in the Home Assistant integration.

### Running Tests

1. (Optional) Create and activate a virtual environment for development.
2. Install the test dependencies with `pip install -r requirements_test.txt` (add `--break-system-packages` when using the provided dev container).
3. Execute the test suite with `pytest` from the repository root.
4. To run a subset, target a path such as `pytest tests/test_config_flow.py`.

## Script for Development

A script is included to automatically link the repository to the correct directory for development. This script will run when you open the workspace.

Script: `.vscode/scripts/link-repository.sh`

``` sh
#!/bin/sh

# Check if /config/custom_components directory exists
if [ ! -d /config/custom_components ]; then
  echo "cannot find custom components directory"
  exit 1
fi

# Check if /config/custom_components/pikvm folder already exists
if [ -d /config/custom_components/pikvm ]; then
  echo "/config/custom_components/pikvm folder already exists"
  exit 1
fi

# Unlink /config/custom_components/pikvm if it's a symbolic link
if [ -L /config/custom_components/pikvm ]; then
  unlink /config/custom_components/pikvm
fi

# Check if custom_components directory exists in the current workspace
if [ ! -d custom_components ]; then
  echo "this must be run from the root of the pikvm workspace"
  exit 1
fi

# Create symbolic link
ln -s "$(pwd)/custom_components/pikvm" /config/custom_components/pikvm
echo "Linking Successful"
```

## Troubleshooting

* Ensure your PiKVM device is accessible from your Home Assistant instance.
* Make sure you have provided the correct URL, username, and password.
* Check the Home Assistant logs for any error messages related to the PiKVM integration.

## Contributing

Contributions are welcome! Please fork this repository and open a pull request with your changes.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
