import voluptuous as vol
from .const import CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD

def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip('/')

def create_data_schema(user_input):
    """Create the data schema for the form."""
    return vol.Schema({
        vol.Required(CONF_URL, default=user_input.get(CONF_URL, "")): str,
        vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
        vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)): str,
    })

def update_existing_entry(hass, existing_entry, user_input):
    """Update an existing config entry."""
    updated_data = existing_entry.data.copy()
    updated_data.update(user_input)
    hass.config_entries.async_update_entry(existing_entry, data=updated_data)

def find_existing_entry(self, serial):
    """Find an existing entry with the same serial number."""
    existing_entries = self._async_current_entries()
    for entry in existing_entries:
        if entry.data.get("serial") == serial:
            return entry
    return None

async def get_translations(hass, language, domain):
    """Get translations for the given language and domain."""
    translations = await hass.helpers.translation.async_get_translations(language, "config")
    def translate(key, default):
        return translations.get(f"component.{domain}.{key}", default)
    return translate
