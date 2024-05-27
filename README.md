# PiKVM Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This is a custom integration for Home Assistant to monitor and control PiKVM devices.

## Features

- Monitor CPU temperature
- Monitor fan speed
- Check device throttling status
- Monitor MSD status and storage
- Track additional PiKVM services (IPMI, Janus, VNC, Webterm)

## Installation

### HACS (Home Assistant Community Store)

1. Ensure that HACS is installed and configured in your Home Assistant setup. If not, follow the instructions [here](https://hacs.xyz/docs/installation/manual).
2. Go to the HACS panel in Home Assistant.
3. Click on the "Integrations" tab.
4. Click on the three dots in the top right corner and select "Custom repositories".
5. Add this repository URL: `https://github.com/yourusername/pikvm-homeassistant` and select "Integration" as the category.
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

## Usage

Once the PiKVM integration is added and configured, you will have several sensors available in Home Assistant to monitor the status and health of your PiKVM device. These sensors will include CPU temperature, fan speed, MSD status, and more.

## Troubleshooting

- Ensure your PiKVM device is accessible from your Home Assistant instance.
- Make sure you have provided the correct URL, username, and password.
- Check the Home Assistant logs for any error messages related to the PiKVM integration.

## Contributing

Contributions are welcome! Please fork this repository and open a pull request with your changes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
