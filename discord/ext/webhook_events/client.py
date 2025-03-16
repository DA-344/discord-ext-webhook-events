"""
The MIT License (MIT)

Copyright (c) 2025-present Developer Anonymous

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, TypeVar

import discord
from discord.ext import commands
from aiohttp.web import Application, AppRunner, route, Request, Response, json_response, TCPSite

if TYPE_CHECKING:
    from .types.events import Event as EventPayload

logger = logging.getLogger(__name__)
T = TypeVar('T', bound=Application, covariant=True)
MISSING = discord.utils.MISSING

__all__ = (
    'Client',
    'AutoShardedClient',
    'Bot',
    'AutoShardedBot',
)


class Client(discord.Client):
    """Represents a :class:`discord.Client` with a webserver attached to it that allows
    receiving webhook events.

    Parameters
    ----------
    intents: :class:`discord.Intents`
        The intents of the client.
    debug: :class:`bool`
        Whether to print debug tracebacks when an error occurs.
    app_cls: Type[:class:`aiohttp.web.Application`]
        The type to instate for the server.
    server_kwargs: Dict[:class:`str`, Any]
        The kwargs to pass to ``app_cls`` constructor.
    http_interactions: :class:`bool`
        WHether HTTP Interactions are enabled. This makes interactions be received via HTTP rather
        than the gateway. If set to ``True``, then you must set the Interactions HTTP Endpoint to
        this server name followed by ``/interactions``. So if ``host`` and ``port`` are ``127.0.0.1``
        and ``8080`` respectively, then you should set it as ``http://127.0.0.1:8080/interactions`` on
        the Developer Portal. Defaults to ``False``.
    connect_to_ws: :class:`bool`
        Whether to connect to the Discord Gateway. Please note that setting this to ``False`` may result
        on caching issues, objects being incomplete, ``get_`` methods returning ``None`` always, or
        inneccessary API calls. Defaults to ``True``.
    **kwargs
        Other parameters passed to :class:`discord.Client`
    """

    def __init__(
        self,
        *,
        intents: discord.Intents,
        debug: bool = False,
        app_cls: type[T] = Application,
        server_kwargs: dict[str, Any] | None = None,
        http_interactions: bool = False,
        connect_to_ws: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(intents=intents, **kwargs)
        self._debug: bool = debug
        self._server = app_cls(**(server_kwargs or {}))

        routes = [
            route('POST', '/', self.__route),
        ]

        if http_interactions:
            routes.append(
                route(
                    'POST', '/interactions', self.__interactions_route
                )
            )

        self._server.add_routes(routes)
        self.__runner: AppRunner = AppRunner(self._server)
        self.__site: TCPSite | None = None
        self.__bot_task: asyncio.Task[None] | None = None
        self.__server_task: asyncio.Task[None] | None = None
        self.connect_to_ws: bool = connect_to_ws

    async def __route(self, request: Request) -> Any:
        data = await request.json()
        type = data.get('type')

        if type == 0:
            return Response(status=204)
        elif type == 1:
            event = data['event']
            self._dispatch_webhook_event(event)
            return Response(status=204)
        else:
            return Response(status=400)

    async def __interactions_route(self, request: Request) -> Response:
        data = await request.json()
        type = data.get('type')

        if type == 1:
            return json_response({'type': 1})
        else:
            # this should work as expected because "data" is the
            # received interaction itself
            self._connection.parse_interaction_create(data)
            return Response(status=204)

    def _dispatch_webhook_event(self, event: EventPayload) -> None:
        if event['type'] == 'APPLICATION_AUTHORIZED':
            data = event['data']
            guild_data = data.get('guild')
            user = discord.User(state=self._connection, data=data['user'])

            if guild_data is None:
                self.dispatch('user_install', user, data['scopes'])
            else:
                guild = self._connection._get_create_guild(guild_data)
                self.dispatch('guild_install', guild, user, data['scopes'])
        elif event['type'] == 'ENTITLEMENT_CREATE':
            data = event['data']
            self._connection.parse_entitlement_create(data)

        # we donnot handle QUEST_USER_ENROLLMENT
        # see https://discord.com/developers/docs/events/webhook-events#quest-user-enrollment
        # for more info

    async def start(
        self,
        token: str,
        *,
        reconnect: bool = True,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        if self.connect_to_ws:
            bot_task = super().start(token, reconnect=reconnect)
        else:
            bot_task = self.login(token)

        await self.__runner.setup()
        self.__site = TCPSite(
            self.__runner,
            host,
            port,
        )
        server_task = self.__site.start()

        self.__bot_task = asyncio.create_task(bot_task)
        self.__server_task = asyncio.create_task(server_task)

        await asyncio.gather(self.__bot_task, self.__server_task)

    def run(
        self,
        token: str,
        *,
        reconnect: bool = True,
        log_handler: logging.Handler | None = MISSING,
        log_formatter: logging.Formatter = MISSING,
        log_level: int = MISSING,
        root_logger: bool = False,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        async def runner():
            async with self:
                await self.start(token, reconnect=reconnect, host=host, port=port)

        if log_handler is not None:
            discord.utils.setup_logging(
                handler=log_handler,
                formatter=log_formatter,
                level=log_level,
                root=root_logger,
            )

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            return

    async def close(self) -> None:
        if self._closing_task:
            return await self._closing_task

        async def _close():
            await self._connection.close()

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            if self._ready is not MISSING:
                self._ready.clear()

            if self.__site is not None:
                await self.__site.stop()

            await self.http.close()

            self.loop = MISSING

        self._closing_task = asyncio.create_task(_close())
        await self._closing_task


class AutoShardedClient(discord.AutoShardedClient):
    """Represents a :class:`discord.AutoShardedClient` with a webserver attached to it that
    allows receiving webhook events.

    Parameters
    ----------
    intents: :class:`discord.Intents`
        The intents of the client.
    debug: :class:`bool`
        Whether to print debug tracebacks when an error occurs.
    app_cls: Type[:class:`aiohttp.web.Application`]
        The type to instate for the server.
    server_kwargs: Dict[:class:`str`, Any]
        The kwargs to pass to ``app_cls`` constructor.
    http_interactions: :class:`bool`
        WHether HTTP Interactions are enabled. This makes interactions be received via HTTP rather
        than the gateway. If set to ``True``, then you must set the Interactions HTTP Endpoint to
        this server name followed by ``/interactions``. So if ``host`` and ``port`` are ``127.0.0.1``
        and ``8080`` respectively, then you should set it as ``http://127.0.0.1:8080/interactions`` on
        the Developer Portal. Defaults to ``False``.
    connect_to_ws: :class:`bool`
        Whether to connect to the Discord Gateway. Please note that setting this to ``False`` may result
        on caching issues, objects being incomplete, ``get_`` methods returning ``None`` always, or
        inneccessary API calls. Defaults to ``True``.
    **kwargs
        Other parameters passed to :class:`discord.AutoShardedClient`
    """

    def __init__(
        self,
        *,
        intents: discord.Intents,
        debug: bool = False,
        app_cls: type[T] = Application,
        server_kwargs: dict[str, Any] | None = None,
        http_interactions: bool = False,
        connect_to_ws: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(intents=intents, **kwargs)
        self._debug: bool = debug
        self._server = app_cls(**(server_kwargs or {}))

        routes = [
            route('POST', '/', self.__route),
        ]

        if http_interactions:
            routes.append(
                route(
                    'POST', '/interactions', self.__interactions_route
                )
            )

        self._server.add_routes(routes)
        self.__runner: AppRunner = AppRunner(self._server)
        self.__site: TCPSite | None = None
        self.__bot_task: asyncio.Task[None] | None = None
        self.__server_task: asyncio.Task[None] | None = None
        self.connect_to_ws: bool = connect_to_ws

    async def __route(self, request: Request) -> Any:
        data = await request.json()
        type = data.get('type')

        if type == 0:
            return Response(status=204)
        elif type == 1:
            event = data['event']
            self._dispatch_webhook_event(event)
            return Response(status=204)
        else:
            return Response(status=400)

    async def __interactions_route(self, request: Request) -> Response:
        data = await request.json()
        type = data.get('type')

        if type == 1:
            return json_response({'type': 1})
        else:
            # this should work as expected because "data" is the
            # received interaction itself
            self._connection.parse_interaction_create(data)
            return Response(status=204)

    def _dispatch_webhook_event(self, event: EventPayload) -> None:
        if event['type'] == 'APPLICATION_AUTHORIZED':
            data = event['data']
            guild_data = data.get('guild')
            user = discord.User(state=self._connection, data=data['user'])

            if guild_data is None:
                self.dispatch('user_install', user, data['scopes'])
            else:
                guild = self._connection._get_create_guild(guild_data)
                self.dispatch('guild_install', guild, user, data['scopes'])
        elif event['type'] == 'ENTITLEMENT_CREATE':
            data = event['data']
            self._connection.parse_entitlement_create(data)

        # we donnot handle QUEST_USER_ENROLLMENT
        # see https://discord.com/developers/docs/events/webhook-events#quest-user-enrollment
        # for more info

    async def start(
        self,
        token: str,
        *,
        reconnect: bool = True,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        if self.connect_to_ws:
            bot_task = super().start(token, reconnect=reconnect)
        else:
            bot_task = self.login(token)

        await self.__runner.setup()
        self.__site = TCPSite(
            self.__runner,
            host,
            port,
        )
        server_task = self.__site.start()

        

        self.__bot_task = asyncio.create_task(bot_task)
        self.__server_task = asyncio.create_task(server_task)

        await asyncio.gather(self.__bot_task, self.__server_task)

    def run(
        self,
        token: str,
        *,
        reconnect: bool = True,
        log_handler: logging.Handler | None = MISSING,
        log_formatter: logging.Formatter = MISSING,
        log_level: int = MISSING,
        root_logger: bool = False,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        async def runner():
            async with self:
                await self.start(token, reconnect=reconnect, host=host, port=port)

        if log_handler is not None:
            discord.utils.setup_logging(
                handler=log_handler,
                formatter=log_formatter,
                level=log_level,
                root=root_logger,
            )

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            return

    async def close(self) -> None:
        if self._closing_task:
            return await self._closing_task

        async def _close():
            await self._connection.close()

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            if self._ready is not MISSING:
                self._ready.clear()

            if self.__site is not None:
                await self.__site.stop()

            await self.http.close()

            self.loop = MISSING

        self._closing_task = asyncio.create_task(_close())
        await self._closing_task


class Bot(commands.Bot):
    """Represents a :class:`discord.ext.commands.Bot` with a webserver attached to it that allows
    receiving webhook events.

    Parameters
    ----------
    *args
        The arguments to pass to :class:`discord.ext.commands.Bot`.
    debug: :class:`bool`
        Whether to print debug tracebacks when an error occurs.
    app_cls: Type[:class:`aiohttp.web.Application`]
        The type to instate for the server.
    server_kwargs: Dict[:class:`str`, Any]
        The kwargs to pass to ``app_cls`` constructor.
    http_interactions: :class:`bool`
        WHether HTTP Interactions are enabled. This makes interactions be received via HTTP rather
        than the gateway. If set to ``True``, then you must set the Interactions HTTP Endpoint to
        this server name followed by ``/interactions``. So if ``host`` and ``port`` are ``127.0.0.1``
        and ``8080`` respectively, then you should set it as ``http://127.0.0.1:8080/interactions`` on
        the Developer Portal. Defaults to ``False``.
    connect_to_ws: :class:`bool`
        Whether to connect to the Discord Gateway. Please note that setting this to ``False`` may result
        on caching issues, objects being incomplete, ``get_`` methods returning ``None`` always, or
        inneccessary API calls. Defaults to ``True``.
    **kwargs
        Other parameters passed to :class:`discord.ext.commands.Bot`.
    """

    def __init__(
        self,
        *args: Any,
        debug: bool = False,
        app_cls: type[T] = Application,
        server_kwargs: dict[str, Any] | None = None,
        http_interactions: bool = False,
        connect_to_ws: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._debug: bool = debug
        self._server = app_cls(**(server_kwargs or {}))

        routes = [
            route('POST', '/', self.__route),
        ]

        if http_interactions:
            routes.append(
                route(
                    'POST', '/interactions', self.__interactions_route
                )
            )

        self._server.add_routes(routes)
        self.__runner: AppRunner = AppRunner(self._server)
        self.__site: TCPSite | None = None
        self.__bot_task: asyncio.Task[None] | None = None
        self.__server_task: asyncio.Task[None] | None = None
        self.connect_to_ws: bool = connect_to_ws

    async def __route(self, request: Request) -> Any:
        data = await request.json()
        type = data.get('type')

        if type == 0:
            return Response(status=204)
        elif type == 1:
            event = data['event']
            self._dispatch_webhook_event(event)
            return Response(status=204)
        else:
            return Response(status=400)

    async def __interactions_route(self, request: Request) -> Response:
        data = await request.json()
        type = data.get('type')

        if type == 1:
            return json_response({'type': 1})
        else:
            # this should work as expected because "data" is the
            # received interaction itself
            self._connection.parse_interaction_create(data)
            return Response(status=204)

    def _dispatch_webhook_event(self, event: EventPayload) -> None:
        if event['type'] == 'APPLICATION_AUTHORIZED':
            data = event['data']
            guild_data = data.get('guild')
            user = discord.User(state=self._connection, data=data['user'])

            if guild_data is None:
                self.dispatch('user_install', user, data['scopes'])
            else:
                guild = self._connection._get_create_guild(guild_data)
                self.dispatch('guild_install', guild, user, data['scopes'])
        elif event['type'] == 'ENTITLEMENT_CREATE':
            data = event['data']
            self._connection.parse_entitlement_create(data)

        # we donnot handle QUEST_USER_ENROLLMENT
        # see https://discord.com/developers/docs/events/webhook-events#quest-user-enrollment
        # for more info

    async def start(
        self,
        token: str,
        *,
        reconnect: bool = True,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        if self.connect_to_ws:
            bot_task = super().start(token, reconnect=reconnect)
        else:
            bot_task = self.login(token)

        await self.__runner.setup()
        self.__site = TCPSite(
            self.__runner,
            host,
            port,
        )
        server_task = self.__site.start()

        

        self.__bot_task = asyncio.create_task(bot_task)
        self.__server_task = asyncio.create_task(server_task)

        await asyncio.gather(self.__bot_task, self.__server_task)

    def run(
        self,
        token: str,
        *,
        reconnect: bool = True,
        log_handler: logging.Handler | None = MISSING,
        log_formatter: logging.Formatter = MISSING,
        log_level: int = MISSING,
        root_logger: bool = False,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        async def runner():
            async with self:
                await self.start(token, reconnect=reconnect, host=host, port=port)

        if log_handler is not None:
            discord.utils.setup_logging(
                handler=log_handler,
                formatter=log_formatter,
                level=log_level,
                root=root_logger,
            )

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            return

    async def close(self) -> None:
        if self._closing_task:
            return await self._closing_task

        async def _close():
            await self._connection.close()

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            if self._ready is not MISSING:
                self._ready.clear()

            if self.__site is not None:
                await self.__site.stop()

            await self.http.close()

            self.loop = MISSING

        self._closing_task = asyncio.create_task(_close())
        await self._closing_task


class AutoShardedBot(commands.AutoShardedBot):
    """Represents a :class:`discord.ext.commands.AutoShardedBot` with a webserver attached to it that allows
    receiving webhook events.

    Parameters
    ----------
    *args
        The arguments to pass to :class:`discord.ext.commands.AutoShardedBot`.
    debug: :class:`bool`
        Whether to print debug tracebacks when an error occurs.
    app_cls: Type[:class:`aiohttp.web.Application`]
        The type to instate for the server.
    server_kwargs: Dict[:class:`str`, Any]
        The kwargs to pass to ``app_cls`` constructor.
    http_interactions: :class:`bool`
        WHether HTTP Interactions are enabled. This makes interactions be received via HTTP rather
        than the gateway. If set to ``True``, then you must set the Interactions HTTP Endpoint to
        this server name followed by ``/interactions``. So if ``host`` and ``port`` are ``127.0.0.1``
        and ``8080`` respectively, then you should set it as ``http://127.0.0.1:8080/interactions`` on
        the Developer Portal. Defaults to ``False``.
    connect_to_ws: :class:`bool`
        Whether to connect to the Discord Gateway. Please note that setting this to ``False`` may result
        on caching issues, objects being incomplete, ``get_`` methods returning ``None`` always, or
        inneccessary API calls. Defaults to ``True``.
    **kwargs
        Other parameters passed to :class:`discord.ext.commands.AutoShardedBot`.
    """

    def __init__(
        self,
        *args: Any,
        debug: bool = False,
        app_cls: type[T] = Application,
        server_kwargs: dict[str, Any] | None = None,
        http_interactions: bool = False,
        connect_to_ws: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._debug: bool = debug
        self._server = app_cls(**(server_kwargs or {}))

        routes = [
            route('POST', '/', self.__route),
        ]

        if http_interactions:
            routes.append(
                route(
                    'POST', '/interactions', self.__interactions_route
                )
            )

        self._server.add_routes(routes)
        self.__runner: AppRunner = AppRunner(self._server)
        self.__site: TCPSite | None = None
        self.__bot_task: asyncio.Task[None] | None = None
        self.__server_task: asyncio.Task[None] | None = None
        self.connect_to_ws: bool = connect_to_ws

    async def __route(self, request: Request) -> Any:
        data = await request.json()
        type = data.get('type')

        if type == 0:
            return Response(status=204)
        elif type == 1:
            event = data['event']
            self._dispatch_webhook_event(event)
            return Response(status=204)
        else:
            return Response(status=400)

    async def __interactions_route(self, request: Request) -> Response:
        data = await request.json()
        type = data.get('type')

        if type == 1:
            return json_response({'type': 1})
        else:
            # this should work as expected because "data" is the
            # received interaction itself
            self._connection.parse_interaction_create(data)
            return Response(status=204)

    def _dispatch_webhook_event(self, event: EventPayload) -> None:
        if event['type'] == 'APPLICATION_AUTHORIZED':
            data = event['data']
            guild_data = data.get('guild')
            user = discord.User(state=self._connection, data=data['user'])

            if guild_data is None:
                self.dispatch('user_install', user, data['scopes'])
            else:
                guild = self._connection._get_create_guild(guild_data)
                self.dispatch('guild_install', guild, user, data['scopes'])
        elif event['type'] == 'ENTITLEMENT_CREATE':
            data = event['data']
            self._connection.parse_entitlement_create(data)

        # we donnot handle QUEST_USER_ENROLLMENT
        # see https://discord.com/developers/docs/events/webhook-events#quest-user-enrollment
        # for more info

    async def start(
        self,
        token: str,
        *,
        reconnect: bool = True,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        if self.connect_to_ws:
            bot_task = super().start(token, reconnect=reconnect)
        else:
            bot_task = self.login(token)

        await self.__runner.setup()
        self.__site = TCPSite(
            self.__runner,
            host,
            port,
        )
        server_task = self.__site.start()

        

        self.__bot_task = asyncio.create_task(bot_task)
        self.__server_task = asyncio.create_task(server_task)

        await asyncio.gather(self.__bot_task, self.__server_task)

    def run(
        self,
        token: str,
        *,
        reconnect: bool = True,
        log_handler: logging.Handler | None = MISSING,
        log_formatter: logging.Formatter = MISSING,
        log_level: int = MISSING,
        root_logger: bool = False,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        async def runner():
            async with self:
                await self.start(token, reconnect=reconnect, host=host, port=port)

        if log_handler is not None:
            discord.utils.setup_logging(
                handler=log_handler,
                formatter=log_formatter,
                level=log_level,
                root=root_logger,
            )

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            return

    async def close(self) -> None:
        if self._closing_task:
            return await self._closing_task

        async def _close():
            await self._connection.close()

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            if self._ready is not MISSING:
                self._ready.clear()

            if self.__site is not None:
                await self.__site.stop()

            await self.http.close()

            self.loop = MISSING

        self._closing_task = asyncio.create_task(_close())
        await self._closing_task
