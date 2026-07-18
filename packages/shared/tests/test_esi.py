import time

import httpx
import pytest
import respx

from gank_shared.esi import ESIClient


@pytest.fixture
def esi():
    client = ESIClient(component="test")
    yield client
    client.close()


@respx.mock
def test_region_id_for_system_is_cached(esi: ESIClient):
    systems_route = respx.get("https://esi.evetech.net/latest/universe/systems/30000142/").mock(
        return_value=httpx.Response(200, json={"constellation_id": 20000020, "name": "Jita"})
    )
    constellations_route = respx.get(
        "https://esi.evetech.net/latest/universe/constellations/20000020/"
    ).mock(return_value=httpx.Response(200, json={"region_id": 10000002}))

    first = esi.region_id_for_system(30000142)
    second = esi.region_id_for_system(30000142)

    assert first == 10000002
    assert second == 10000002
    assert systems_route.call_count == 1
    assert constellations_route.call_count == 1


@respx.mock
def test_system_name_is_cached(esi: ESIClient):
    route = respx.get("https://esi.evetech.net/latest/universe/systems/30000142/").mock(
        return_value=httpx.Response(200, json={"constellation_id": 20000020, "name": "Jita"})
    )

    assert esi.system_name(30000142) == "Jita"
    assert esi.system_name(30000142) == "Jita"
    assert route.call_count == 1


@respx.mock
def test_resolve_names_batches_over_1000_ids(esi: ESIClient):
    call_count = 0

    def responder(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        import json

        requested = json.loads(request.content)
        return httpx.Response(
            200, json=[{"id": i, "name": f"name-{i}", "category": "solar_system"} for i in requested]
        )

    respx.post("https://esi.evetech.net/latest/universe/names/").mock(side_effect=responder)

    ids = list(range(1500))
    result = esi.resolve_names(ids)

    assert call_count == 2
    assert len(result) == 1500
    assert result[0] == "name-0"
    assert result[1499] == "name-1499"


def test_resolve_names_empty_list_makes_no_call(esi: ESIClient):
    assert esi.resolve_names([]) == {}


@respx.mock
def test_resolve_region_by_name_found(esi: ESIClient):
    respx.post("https://esi.evetech.net/latest/universe/ids/").mock(
        return_value=httpx.Response(200, json={"regions": [{"id": 10000002, "name": "The Forge"}]})
    )

    assert esi.resolve_region_by_name("The Forge") == 10000002


@respx.mock
def test_resolve_region_by_name_not_found(esi: ESIClient):
    respx.post("https://esi.evetech.net/latest/universe/ids/").mock(return_value=httpx.Response(200, json={}))

    assert esi.resolve_region_by_name("Not A Real Region") is None


@respx.mock
def test_resolve_location_name_tries_endpoints_until_one_succeeds(esi: ESIClient):
    stargates_route = respx.get("https://esi.evetech.net/latest/universe/stargates/40333261/").mock(
        return_value=httpx.Response(404)
    )
    belts_route = respx.get("https://esi.evetech.net/latest/universe/asteroid_belts/40333261/").mock(
        return_value=httpx.Response(200, json={"name": "Simela VII - Asteroid Belt 2"})
    )
    stations_route = respx.get("https://esi.evetech.net/latest/universe/stations/40333261/")

    name = esi.resolve_location_name(40333261)

    assert name == "Simela VII - Asteroid Belt 2"
    assert stargates_route.call_count == 1
    assert belts_route.call_count == 1
    assert stations_route.call_count == 0  # stopped probing once belts succeeded


@respx.mock
def test_resolve_location_name_is_cached(esi: ESIClient):
    route = respx.get("https://esi.evetech.net/latest/universe/stargates/1/").mock(
        return_value=httpx.Response(200, json={"name": "Some Stargate"})
    )

    assert esi.resolve_location_name(1) == "Some Stargate"
    assert esi.resolve_location_name(1) == "Some Stargate"
    assert route.call_count == 1


@respx.mock
def test_resolve_location_name_falls_back_when_nothing_matches(esi: ESIClient):
    for kind in ["stargates", "asteroid_belts", "stations", "moons", "planets"]:
        respx.get(f"https://esi.evetech.net/latest/universe/{kind}/999/").mock(
            return_value=httpx.Response(404)
        )

    assert esi.resolve_location_name(999) == "location 999"


@respx.mock
def test_resolve_location_name_skips_probing_for_structure_ids(esi: ESIClient):
    # No routes registered -- respx raises on any unmocked request, so this
    # also proves player-structure IDs never get probed over HTTP.
    name = esi.resolve_location_name(1_000_000_000_001)
    assert name == "location 1000000000001"


@respx.mock
def test_420_sets_error_cooldown(esi: ESIClient):
    respx.get("https://esi.evetech.net/latest/universe/systems/1/").mock(
        return_value=httpx.Response(420, headers={"Retry-After": "30"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        esi._get("/universe/systems/1/")

    # cooldown should be set roughly 30s out (allow generous slack for test runtime)
    assert 25 < esi._error_cooldown_until - time.monotonic() <= 30
