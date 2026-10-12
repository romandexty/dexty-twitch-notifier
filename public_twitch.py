"""Twitch public-client device sign-in. No client secret or email scope."""
import asyncio
import time
from types import SimpleNamespace
import requests
from connections_ui import atomic_json, read_json

# Set once by the publisher after registering a Public Twitch application.
PUBLIC_CLIENT_ID = 'vmk4bwfqgjt2efezq0g9wkegoasl42'

class SignInRequired(Exception):
    pass

class PublicTwitch:
    def __init__(self, client_id, token_file):
        self.client_id = client_id
        self.token_file = token_file
        self.tokens = read_json(token_file)
        self.validated_at = 0

    def _request(self, method, url, **kwargs):
        try:
            response = requests.request(method, url, timeout=12, **kwargs)
        except requests.RequestException:
            raise RuntimeError('Twitch network request failed. Check your connection.') from None
        if response.status_code == 401:
            raise SignInRequired('Reconnect Twitch in Setup / Language.')
        if response.status_code >= 400:
            raise RuntimeError('Twitch request failed (HTTP %d).' % response.status_code)
        return response.json()

    async def validate(self, allow_refresh=True):
        token = self.tokens.get('access_token')
        if not token:
            raise SignInRequired('Connect Twitch in Setup / Language.')
        try:
            data = await asyncio.to_thread(self._request, 'GET', 'https://id.twitch.tv/oauth2/validate',
                headers={'Authorization': 'OAuth ' + token})
        except SignInRequired:
            if not allow_refresh:
                raise
            await self.refresh()
            return await self.validate(allow_refresh=False)
        if data.get('client_id') != self.client_id or not data.get('user_id'):
            raise SignInRequired('Connect Twitch again using this application.')
        self.validated_at = time.monotonic()

    async def refresh(self):
        refresh = self.tokens.get('refresh_token')
        if not refresh:
            raise SignInRequired('Connect Twitch again.')
        try:
            data = await asyncio.to_thread(self._request, 'POST', 'https://id.twitch.tv/oauth2/token',
                data={'client_id': self.client_id, 'grant_type': 'refresh_token', 'refresh_token': refresh})
        except RuntimeError:
            raise SignInRequired('Twitch session expired. Connect Twitch again.') from None
        self.tokens = data
        atomic_json(self.token_file, data)

    async def _get(self, endpoint, key, logins):
        if time.monotonic() - self.validated_at > 3500:
            await self.validate()
        result = []
        for offset in range(0, len(logins), 100):
            params = [(key, name) for name in logins[offset:offset + 100]]
            if endpoint == 'streams':
                params.append(('first', 100))
            for attempt in range(2):
                try:
                    data = await asyncio.to_thread(self._request, 'GET', 'https://api.twitch.tv/helix/' + endpoint,
                        params=params, headers={'Client-ID': self.client_id,
                        'Authorization': 'Bearer ' + self.tokens['access_token']})
                    break
                except SignInRequired:
                    if attempt:
                        raise
                    await self.refresh()
            result.extend(SimpleNamespace(**item) for item in data.get('data', []))
        return result

    async def get_users(self, logins):
        for item in await self._get('users', 'login', logins):
            yield item

    async def get_streams(self, user_login):
        for item in await self._get('streams', 'user_login', user_login):
            yield item

    async def close(self):
        pass

def begin_sign_in(client_id):
    try:
        response = requests.post('https://id.twitch.tv/oauth2/device',
            data={'client_id': client_id, 'scopes': ''}, timeout=12)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        raise RuntimeError('Could not start Twitch sign-in. Check your connection and Public Client ID.') from None

def poll_sign_in(client_id, device_code):
    try:
        response = requests.post('https://id.twitch.tv/oauth2/token', data={
            'client_id': client_id, 'device_code': device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'}, timeout=12)
        data = response.json()
    except (requests.RequestException, ValueError):
        raise RuntimeError('Could not reach Twitch. Try connecting again.') from None
    if response.ok:
        return data
    message = data.get('message', data.get('error', ''))
    if 'authorization_pending' in message:
        return None
    if 'slow_down' in message:
        return {'slow_down': True}
    raise RuntimeError('Twitch sign-in ended or expired. Try connecting again.')
