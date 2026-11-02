"""Calling the author's chosen model: Claude through Anthropic's API, any OpenAI-compatible server (LM Studio,
Ollama, OpenRouter and the like, local or not), or the `claude` command line on this computer.

The model only ever drafts; worldsmith.drafts checks what comes back and queues it for the author's approval.
API keys are kept in the system keyring when there is one, never in the settings file.
"""
import json
import shutil
import subprocess

import anthropic
import httpx
import keyring
from keyring.errors import KeyringError

from worldsmith import settings
from worldsmith.dungeon_format.errors import DomainError, require

PROVIDERS = ('anthropic', 'openai', 'claude-cli')
DEFAULTS = {'anthropic': 'claude-opus-5-5', 'openai': '', 'claude-cli': ''}
KEYRING = 'prosperos-worldsmith'
MAX_TOKENS = 16000
TIMEOUT = 600


def config() -> dict:
    """The model settings as the screen shows them: which provider, model and server, and whether a key is set."""
    saved = settings.load().get('model') or {}
    provider = saved.get('provider') if saved.get('provider') in PROVIDERS else 'anthropic'
    return {'provider': provider, 'model': saved.get('model') or DEFAULTS[provider],
            'base_url': saved.get('base_url') or '', 'has_key': bool(api_key(provider))}


def configure(provider: str, model: str = '', base_url: str = '', key: str | None = None) -> dict:
    require(provider in PROVIDERS, 'Pick Anthropic, an OpenAI-compatible server, or the claude command line.', 422)
    if provider == 'openai':
        require(base_url.startswith(('http://', 'https://')), 'An OpenAI-compatible server needs its address, like '
                'http://127.0.0.1:1234/v1 for LM Studio.', 422)
    if key is not None:
        store_key(provider, key)
    settings.save({'model': {'provider': provider, 'model': model.strip(), 'base_url': base_url.strip().rstrip('/')}})
    return config()


def api_key(provider: str) -> str:
    try:
        return keyring.get_password(KEYRING, provider) or ''
    except KeyringError:
        return ''


def store_key(provider: str, key: str):
    try:
        if key:
            keyring.set_password(KEYRING, provider, key)
        else:
            keyring.delete_password(KEYRING, provider)
    except KeyringError as error:
        if key:
            raise DomainError(f'This computer has no keyring to keep the key in safely ({error}).', 500) from error


def complete(system: str, prompt: str) -> str:
    """One answer from the configured model, as text."""
    chosen = config()
    if chosen['provider'] == 'anthropic':
        return complete_anthropic(chosen, system, prompt)
    if chosen['provider'] == 'openai':
        return complete_openai(chosen, system, prompt)
    return complete_cli(chosen, system, prompt)


def complete_anthropic(chosen: dict, system: str, prompt: str) -> str:
    key = api_key('anthropic')
    client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    try:
        # Server-side fallback: a request one model declines is retried on another rather than failing outright.
        response = client.beta.messages.create(
            model=chosen['model'], max_tokens=MAX_TOKENS, system=system,
            messages=[{'role': 'user', 'content': prompt}], output_config={'effort': 'medium'},
            betas=['server-side-fallback-2026-07-01'], fallbacks='default')
    except anthropic.AuthenticationError as error:
        raise DomainError('Anthropic did not accept the API key. Set it again in Models.', 401) from error
    except anthropic.RateLimitError as error:
        raise DomainError('Anthropic is rate limiting this key; try again in a minute.', 429) from error
    except anthropic.APIStatusError as error:
        raise DomainError(f'Anthropic answered {error.status_code}: {error.message}', 502) from error
    except anthropic.APIConnectionError as error:
        raise DomainError('Could not reach Anthropic. Check the connection.', 502) from error
    if response.stop_reason == 'refusal':
        raise DomainError('The model declined this draft. Try rewording the ask, or another model.', 422)
    return ''.join(block.text for block in response.content if block.type == 'text')


def complete_openai(chosen: dict, system: str, prompt: str) -> str:
    key = api_key('openai')
    headers = {'Authorization': f'Bearer {key}'} if key else {}
    body = {'model': chosen['model'] or 'local-model', 'max_tokens': MAX_TOKENS,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]}
    try:
        response = httpx.post(f"{chosen['base_url']}/chat/completions", json=body, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as error:
        raise DomainError(f"Could not reach the model server at {chosen['base_url']} ({error}).", 502) from error
    require(response.status_code < 400, f'The model server answered {response.status_code}: {response.text[:300]}', 502)
    try:
        return response.json()['choices'][0]['message']['content'] or ''
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise DomainError('The model server sent something that is not a chat answer.', 502) from error


def complete_cli(chosen: dict, system: str, prompt: str) -> str:
    command = shutil.which('claude')
    require(bool(command), 'The claude command line is not installed on this computer.', 409)
    args = [command, '-p', '--output-format', 'json', '--append-system-prompt', system]
    if chosen['model']:
        args += ['--model', chosen['model']]
    try:
        done = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding='utf-8', timeout=TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise DomainError('The claude command line took too long.', 504) from error
    require(done.returncode == 0, f'The claude command line failed: {(done.stderr or done.stdout)[:300]}', 502)
    try:
        return json.loads(done.stdout).get('result', '')
    except ValueError:
        return done.stdout
