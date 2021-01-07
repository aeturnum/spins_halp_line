from spins_halp_line.resource_space import RSResource


async def test_search():
    search = await RSResource.for_room("Shipwreck Yard Front")
    print(search)
    for resource in search:
        print(resource._data)