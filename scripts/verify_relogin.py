import asyncio
import logging
import os
from datetime import date, timedelta

from pycalista_ista import PyCalistaIsta
from pycalista_ista.exception_classes import IstaConnectionError, IstaLoginError

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)


async def run_relogin_test():
    email = os.environ.get("ISTA_EMAIL", "juanherruzo@gmail.com")
    password = os.environ.get("ISTA_PASSWORD")

    if not password:
        print("Error: ISTA_PASSWORD environment variable not set.")
        return

    print("--- Relogin Verification Script ---")
    print(f"Account: {email}")

    async with PyCalistaIsta(email, password) as client:
        print("\n[1] Attempting initial login...")
        # Let's directly get KC HTML to see the doctype
        from pycalista_ista.const import KC_AUTH_URL, KC_CLIENT_ID, KC_REDIRECT_URI, KC_STATE
        params = {
            "client_id": KC_CLIENT_ID,
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": KC_REDIRECT_URI,
            "state": KC_STATE,
            "prompt": "login",
            "max_age": "0",
        }
        res = await client._virtual_api._send_request("GET", KC_AUTH_URL, params=params, relogin=False)
        html = await res.text()
        print("Keycloak doctype snippet:", html[:200])
        
        await client.login()
        print("Initial login successful.")

        # 2. Simulate session expiry by clearing cookies
        print(
            "\n[2] Simulating session expiry by clearing ALL cookies..."
        )
        client._virtual_api.session.cookie_jar.clear()
        print("All cookies cleared.")

        # 3. Request data
        print("\n[3] Attempting to fetch data with 'expired' session...")
        print(
            "Expectation: The library should detect the redirect to Keycloak and re-login automatically."
        )

        try:
            today = date.today()
            start = today - timedelta(days=30)
            end = today

            # This call should trigger a relogin because we cleared the portal cookies
            devices = await client.get_devices_history(start, end)

            print(f"Success! Retrieved {len(devices)} devices after automatic relogin.")
            for sn, device in list(devices.items())[:3]:
                print(f" - Device SN {sn}: {len(device.history)} readings found.")

        except (IstaConnectionError, IstaLoginError) as e:
            print(f"Relogin test failed: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_relogin_test())
