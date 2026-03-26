import asyncio
import logging
import os
from datetime import date, timedelta
from aiohttp import CookieJar
import yarl

from pycalista_ista import PyCalistaIsta
from pycalista_ista.exception_classes import IstaConnectionError, IstaLoginError

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

async def run_test():
    email = os.environ.get("ISTA_EMAIL", "juanherruzo@gmail.com")
    password = os.environ.get("ISTA_PASSWORD")

    async with PyCalistaIsta(email, password) as client:
        print("\n[1] Attempting initial login...")
        await client.login()

        print("\n[2] Simulating stale Keycloak session and expired Ista session...")
        client._virtual_api.session.cookie_jar.clear_domain("oficina.ista.es")
        # Corrupt Keycloak cookies to simulate expiration on server
        for cookie in client._virtual_api.session.cookie_jar:
            if "login.ista.com" in cookie["domain"]:
                print(f"Corrupting cookie {cookie.key}")
                cookie.set(cookie.key, cookie.value + "stale", cookie.value + "stale")

        print("\n[3] Attempting to fetch data with stale Keycloak session...")
        try:
            today = date.today()
            devices = await client.get_devices_history(today - timedelta(days=5), today)
            print(f"Success! Retrieved {len(devices)} devices after automatic relogin.")
        except Exception as e:
            print(f"Relogin test failed: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
