# PiKVM Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration) [![Project Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/adamoutler/pikvm-homeassistant-integration/graphs/commit-activity)

This is a custom integration for Home Assistant to monitor and control your [PiKVM](https://pikvm.org/) devices. It provides detailed sensor information, allowing you to keep an eye on your device's health and status directly from your Home Assistant dashboard.

<p align="center">
  <img src="https://raw.githubusercontent.com/adamoutler/pikvm-homeassistant-integration/main/.github/screenshot.png" alt="PiKVM Integration Screenshot">
</p>

## Prerequisites

Before you begin, please ensure you have the following:

*   **A working PiKVM device**: Your PiKVM must be set up, connected to your network, and accessible from your Home Assistant instance.
*   **User Credentials**: You will need the username and password for your PiKVM. The default is `admin` / `admin`.
*   **2FA/TOTP Secret (if enabled)**: If you have Two-Factor Authentication enabled on your PiKVM, you will need the **base32 secret key**. This is the long string of characters you used to set up 2FA, not the 6-digit code your authenticator app generates.

## Installation

The recommended way to install this integration is through the [Home Assistant Community Store (HACS)](https://hacs.xyz/).

### 1. Add via "My Home Assistant" (Easiest)

Click the button below to add the PiKVM integration repository to your HACS instance:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adamoutler&repository=pikvm-homeassistant-integration&category=Integration)

### 2. Manual HACS Installation

1.  Go to your HACS panel in Home Assistant.
2.  Click on **Integrations**.
3.  Click the three dots in the top right and select **"Custom repositories"**.
4.  Enter the repository URL: `https://github.com/adamoutler/pikvm-homeassistant-integration`
5.  Select the category **"Integration"** and click **"Add"**.
6.  The "PiKVM" integration will now appear in your HACS integrations list. Click **"Install"**.
7.  Restart Home Assistant when prompted.

## Configuration

Once installed, the integration can be configured through the Home Assistant UI.

1.  Navigate to **Settings** > **Devices & Services**.
2.  Your PiKVM may be automatically discovered. If so, click **"Configure"** on the discovered device card.
3.  If not discovered, click the **"+ Add Integration"** button.
4.  Search for **"PiKVM"** and select it.
5.  Follow the setup wizard to enter your PiKVM's details.

### Configuration Options

-   **URL**: The URL or IP address of your PiKVM device (e.g., `192.168.1.123` or `pikvm.local`).
-   **Username**: Your PiKVM username (default: `admin`).
-   **Password**: Your PiKVM password (default: `admin`).
-   **TOTP Generator Key (Not 6-Digit Code)**: If you have 2FA enabled, enter your **base32 secret key** here.
    *   You can get this key by running the following command on your PiKVM: `kvmd-totp show -s`
    *   Leave this field blank if you do not have 2FA enabled.

## Usage: Available Sensors

Once configured, the integration will create a device for your PiKVM with several sensors to monitor its status and health. Key sensors include:

*   **CPU Temperature**: Monitors the temperature of the PiKVM's CPU. Consistently high temperatures may indicate a need for better cooling.
*   **CPU Utilization**: Shows the current CPU load as a percentage.
*   **Memory Utilization**: Tracks the amount of RAM currently in use.
*   **Fan Speed**: Reports the speed of the fan in RPM, if one is connected and configured.
*   **Throttling**: Indicates if the PiKVM is reducing its performance due to high temperature or low voltage.
*   **MSD Enabled**: Shows whether the Mass Storage Device function is currently enabled.
*   **MSD Drive**: Reports the current status or mode of the Mass Storage Drive.
*   **MSD Storage**: Shows the available storage space on the Mass Storage Drive.
*   **Extra Sensors**: The integration will also create sensors for any configured "extras" on your PiKVM, such as IPMI, Janus, VNC, or Webterm services, showing their current status.

## Troubleshooting

If you encounter issues, please check the following common problems and solutions.

| Problem                                    | Solution                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Invalid username or password**           | Double-check that you have entered the correct username and password. The defaults are `admin`/`admin`. If you have changed them on your PiKVM, you must use your new credentials.                                                                                                                                                                                   |
| **"The TOTP secret is not a valid base32 string"** | This error means you have entered your 6-digit one-time code instead of the secret key. Please enter the **base32 secret key** (a long string of characters) that you used to set up 2FA. You can retrieve it by running `kvmd-totp show -s` on your PiKVM.                                                                                                            |
| **Cannot connect to PiKVM device**         | *   **Check Network**: Ensure your PiKVM is on the same network as Home Assistant and is powered on. You can test this by trying to `ping` the PiKVM's IP address from another computer on the network. <br> *   **Check Firewall**: Make sure no firewall rules are blocking communication between Home Assistant and your PiKVM on port 443 (HTTPS).                   |
| **After a PiKVM update, the integration stopped working.** | PiKVM firmware updates can sometimes introduce changes to the API that break compatibility. First, check the integration's [GitHub page](https://github.com/adamoutler/pikvm-homeassistant-integration) to see if a new version is available. If not, please [open an issue](https://github.com/adamoutler/pikvm-homeassistant-integration/issues) to report the problem. |

If your problem is not listed here, please enable debug logging, restart Home Assistant, and then [open an issue](https://github.com/adamoutler/pikvm-homeassistant-integration/issues) with the relevant logs attached.

## Contributing

Contributions are always welcome! Please fork this repository and open a pull request with your changes.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
