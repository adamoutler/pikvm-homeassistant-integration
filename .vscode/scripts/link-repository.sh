#!/bin/sh

set -e
# Function to reload Home Assistant
reload_home_assistant() {
  echo "Reloading Home Assistant..."
  # Assuming you have the Home Assistant CLI (hass-cli) installed
  ha core restart
}

# Check if /config/custom_components directory exists
if [ ! -d /config/custom_components ]; then
  echo "Cannot find custom components directory"
  exit 1
fi

# Unlink /config/custom_components/pikvm if it's a symbolic link
if [ -L /config/custom_components/pikvm_ha ]; then
  unlink /config/custom_components/pikvm_ha
fi

# Check if /config/custom_components/pikvm folder already exists
if [ -d /config/custom_components/pikvm_ha ]; then
  echo "/config/custom_components/pikvm_ha folder already exists"
  exit 1
fi

# Check if custom_components directory exists in the current workspace
if [ ! -d custom_components ]; then
  echo "This must be run from the root of the pikvm workspace"
  exit 1
fi

# Create symbolic link
ln -s "$(pwd)/custom_components/pikvm_ha" /config/custom_components/pikvm_ha
echo "Linking Successful"

# Reload Home Assistant
#reload_home_assistant
echo "Press F1->Tasks:-> Restart Home Assistant if changes have not taken effect."
