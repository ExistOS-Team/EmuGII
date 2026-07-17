import os

import pytest
import pytest_asyncio

from framework.machine import with_machine


@pytest_asyncio.fixture
async def machine():
    async with with_machine() as m:
        yield m


def pytest_collection_modifyitems(config, items):
    flt = os.environ.get("EMUGII_QTEST_FILTER")
    if not flt:
        return
    kept = []
    for item in items:
        desc = item.obj.__doc__ or ""
        name = item.name
        if flt in desc or flt in name:
            kept.append(item)
    if not kept:
        raise pytest.UsageError(f"No qtest contract matched filter: {flt}")
    items[:] = kept
