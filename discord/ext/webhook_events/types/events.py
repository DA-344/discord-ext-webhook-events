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

from typing import Literal, TypedDict, Union
from typing_extensions import NotRequired

from discord.types.guild import Guild
from discord.types.sku import Entitlement
from discord.types.snowflake import Snowflake
from discord.types.user import User

WebhookEventType = Literal[0, 1]


class WebhookEvent(TypedDict):
    version: int
    application_id: Snowflake
    type: WebhookEventType
    event: NotRequired[Event]


class ApplicationAuthorisedEvent(TypedDict):
    type: Literal['APPLICATION_AUTHORIZED']
    timestamp: str
    data: ApplicationAuthorisedEventData


class EntitlementCreateEvent(TypedDict):
    type: Literal['ENTITLEMENT_CREATE']
    timestamp: str
    data: Entitlement


class ApplicationAuthorisedEventData(TypedDict):
    integration_type: NotRequired[Literal[0, 1]]
    user: User
    scopes: list[str]
    guild: NotRequired[Guild]

Event = Union[ApplicationAuthorisedEvent, EntitlementCreateEvent]
