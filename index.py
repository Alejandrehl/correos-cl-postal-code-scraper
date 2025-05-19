import sys
import time
import json
import unicodedata
import requests
import re
import json
from playwright.sync_api import sync_playwright, expect

def wait(seconds: float, msg: str = ""):
    if msg:
        print(f"[WAIT] {msg} ({seconds}s)")
    time.sleep(seconds)

def normalize_address_text(text: str) -> str:
    """Normalize input by removing accents, converting to uppercase, and cleaning spaces."""
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = text.upper().strip()
    return " ".join(text.split())

def autocomplete_select(page, selector: str, value: str):
    page.click(selector)
    wait(0.5)
    page.fill(selector, value)
    wait(1.2)
    page.keyboard.press("ArrowDown")
    wait(0.3)
    page.keyboard.press("Enter")
    wait(1)

def ensure_autocomplete_selected(page, selector: str, expected_value: str, label: str, max_retries: int = 2):
    for attempt in range(max_retries):
        autocomplete_select(page, selector, expected_value)
        actual = page.input_value(selector).strip().upper()
        print(f"[DEBUG] Verifying {label}: attempt {attempt + 1} → '{actual}'")
        if expected_value.upper() in actual:
            return True
        print(f"[WARNING] {label.capitalize()} value not correctly applied, retrying...")
    raise Exception(f"Failed to select {label} correctly after {max_retries} attempts.")

def ensure_number_filled(page, selector: str, value: str):
    page.fill(selector, value)
    wait(0.5)
    filled = page.input_value(selector).strip()
    if filled != value.strip():
        raise Exception(f"Number field not filled correctly: expected '{value}', got '{filled}'")
    return True

def get_correos_data():
    url = "https://www.correos.cl/codigo-postal"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise HTTPError for bad status codes

        # Extract cookies
        cookies = response.cookies.get_dict()
        desired_cookies = {
            name: cookies.get(name)
            for name in ['__uzma', '__uzmb', '__uzme', 'JSESSIONID', 'SERVER_ID']
        }

        # Extract Liferay.authToken using regex
        auth_token_match = re.search(r"Liferay\.authToken\s*=\s*'([^']+)'", response.text)
        auth_token = auth_token_match.group(1) if auth_token_match else None

        desired_cookies['Liferay.authToken'] = auth_token

        return desired_cookies

    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}
    except Exception as e:
        return {"error": f"An error occurred: {e}"}

def get_postal_code(commune: str, street: str, number: str) -> dict:
    print(f"[INFO] Lookup started for commune='{commune}', street='{street}', number='{number}'")

    # Normalize inputs
    commune = normalize_address_text(commune)
    street = normalize_address_text(street)
    number = normalize_address_text(number)

    # Get session cookies and Liferay token
    correos_data = get_correos_data()
    if "error" in correos_data:
        return { "error": f"[ERROR] Failed to fetch initial session data: {correos_data['error']}" }

    print(f"[DEBUG] Session data retrieved: {correos_data}")

    # Build Cookie header from available cookies
    cookie_keys = ['__uzma', '__uzmb', '__uzme', 'JSESSIONID', 'SERVER_ID']
    cookie_header = "; ".join([f"{k}={correos_data[k]}" for k in cookie_keys if correos_data.get(k)])

    # Add minimal required static cookies if needed
    cookie_header += "; COOKIE_SUPPORT=true; GUEST_LANGUAGE_ID=es_ES"

    # Prepare payload with dynamic authToken
    auth_token = correos_data.get('Liferay.authToken')
    if not auth_token:
        return { "error": "[ERROR] authToken not found in response" }

    payload = f"_cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9_comuna={commune}&" \
              f"_cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9_calle={street}&" \
              f"_cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9_numero={number}&" \
              f"p_auth={auth_token}"

    url = "https://www.correos.cl/codigo-postal?p_p_id=cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view&p_p_resource_id=COOKIES_RESOURCE_ACTION&p_p_cacheability=cacheLevelPage&_cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9_cmd=CMD_ADD_COOKIE"

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cookie': cookie_header
    }

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15)
        response.raise_for_status()

        data = response.json()
        print(f"[DEBUG] Response JSON: {data}")

        # Try extracting from 'direcciones'
        direcciones = data.get("direcciones", [])
        if isinstance(direcciones, list) and direcciones:
            postal_code = direcciones[0].get("codPostal")
            if postal_code:
                return { "postalCode": postal_code }

        # Fallback: try 'currentDir'
        current_dir_raw = data.get("currentDir")
        if current_dir_raw:
            current_dir = json.loads(current_dir_raw)
            postal_code = current_dir.get("codPostal")
            if postal_code:
                return { "postalCode": postal_code }

        return { "error": data }

    except requests.RequestException as e:
        return { "error": f"Request failed: {str(e)}" }
    except Exception as e:
        return { "error": f"Unexpected error: {str(e)}" }

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(json.dumps({
            "error": "Invalid arguments. Usage: python index.py 'Commune' 'Street' 'Number'"
        }))
        sys.exit(1)

    commune, street, number = sys.argv[1], sys.argv[2], sys.argv[3]
    result = get_postal_code(commune, street, number)
    print(json.dumps(result))
