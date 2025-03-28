# discord-ext-webhook-events

A simple extension package that allows your client to receive webhook events.

## What is ``discord-ext-webhook-events``?

``discord-ext-webhook-events`` is a [``discord.py``](https://github.com/Rapptz/discord.py) extension that allows
you to easily set up, receive, and handle [Webhook Events](https://discord.com/developers/docs/events/webhook-events)
while mantaining the easy ``discord.py`` event handling.

You can also handle HTTP Interactions with this extension.

## Installation

**Python 3.9 or higher is required.**

> [!NOTE]
> A [Virtual Environment](https://docs.python.org/3/library/venv.html) is recommended to install the library,
> especially on Linux where the system Python is externally managed and restricts which packages you can install on it.

You can get the library directly from GitHub:
```bash
python3 -m pip install -U git+https://github.com/DA-344/discord-ext-webhook-events
```

If you are using Windows, then the following should be used instead:
```bash
py -3 -m pip install -U git+https://github.com/DA-344/discord-ext-webhook-events
```

## Quick Example
```py
import discord
from discord.ext.webhook_events import Client

intents = discord.Intents.default()
intents.members = True
client = Client(intents=intents)

@client.event
async def on_user_install(user: discord.User, scopes: list[str]) -> None:
    await user.send('Thanks for installing the app on your account!')

@client.event
async def on_guild_install(guild: discord.Guild, user: discord.User, scopes: list[str]) -> None:
    await user.send(f'Thanks for installing the app to {guild.name}!')

client.run(
    token='YOUR_BOT_TOKEN',
    host='127.0.0.1',
    port=8000,
)
```

## Event Reference

### `on_user_install(user, scopes)`

Event dispatched when the app is installed in a user account.

**Parameters:**
- ``user`` ([``discord.User``](https://discordpy.readthedocs.io/en/stable/api.html#discord.User)) - The user that installed the app.
- ``scopes`` (List[[``str``](https://docs.python.org/3.13/library/stdtypes.html#str)]) - The scopes that ``user`` authorised.

### `on_guild_install(guild, user, scopes)`

Event dispatched when the app is installed on a guild.

**Parameters:**
- ``guild`` ([``discord.Guild``](https://discordpy.readthedocs.io/en/stable/api.html#discord.Guild)) - The guild the app got installed into.
- ``user`` ([``discord.User``](https://discordpy.readthedocs.io/en/stable/api.html#discord.User)) - The user that installed the app into the ``guild``.
- ``scopes`` (List[[``str``](https://docs.python.org/3.13/library/stdtypes.html#str)]) - The scopes that ``user`` authorised to add the app into ``guild``.

### `on_entitlement_create(entitlement)`

Event dispatched when an entitlement is created.

> [!NOTE]
> Although this event can be received via the Gateway, if you suscribe to it on the Developer Portal, you will receive it here

**Parameters:**
- ``entitlement`` ([``discord.Entitlement``](https://discordpy.readthedocs.io/en/stable/api#discord.Entitlement)) - The entitlement that was created.
