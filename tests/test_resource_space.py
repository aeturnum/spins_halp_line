from spins_halp_line.media.resource_space import RSResource


async def test_search():
    search = await RSResource.for_room("Tip Line Tip 1")
    print(search)
    for resource in search:
        print(resource._data)
    assert False