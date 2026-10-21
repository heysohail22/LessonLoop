import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.genai import errors

from lessonloop.gemini import GeminiModel, GenerationError


def adapter(call):
    model = object.__new__(GeminiModel)
    model.model = 'test-model'
    model.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=call)))
    return model


def test_generation_uses_json_schema_not_legacy_schema():
    call = AsyncMock(return_value=SimpleNamespace(text='{}'))
    assert asyncio.run(adapter(call).complete(system='instructions', user='brief')) == '{}'
    config = call.call_args.kwargs['config']
    assert config.response_schema is None
    assert config.response_json_schema['additionalProperties'] is False
    assert 'worked_example' in config.response_json_schema['required']


@pytest.mark.parametrize('code,expected', [(400, 'rejected'), (403, 'denied'), (404, 'not found'), (429, 'quota')])
def test_errors_are_actionable_and_do_not_expose_provider_details(code, expected):
    call = AsyncMock(side_effect=errors.ClientError(code, {'error': {'message': 'private-provider-detail'}}))
    with pytest.raises(GenerationError) as caught:
        asyncio.run(adapter(call).complete(system='instructions', user='brief'))
    assert expected in str(caught.value)
    assert 'private-provider-detail' not in str(caught.value)
