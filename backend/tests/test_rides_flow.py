from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_full_ride_flow():
    # 1. Create a ride
    create_resp = client.post(
        "/api/v1/rides",
        json={
            "ride_name": "Test Canyon Run",
            "start_location_name": "Denver, CO",
            "destination_location_name": "Moab, UT",
            "leader_name": "Alex Rider",
        },
    )
    assert create_resp.status_code == 201
    ride = create_resp.json()
    ride_id = ride["id"]
    invite_code = ride["invite_code"]
    assert ride["rider_count"] == 1

    # 2. Get ride details
    get_resp = client.get(f"/api/v1/rides/{ride_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Test Canyon Run"

    # 3. A second rider joins via invite code
    join_resp = client.post(
        "/api/v1/rides/join",
        json={"invite_code": invite_code, "rider_name": "Jamie Pillion"},
    )
    assert join_resp.status_code == 201
    joined_rider_id = join_resp.json()["rider"]["id"]
    assert join_resp.json()["ride"]["rider_count"] == 2

    # 4. Add a third rider directly
    add_resp = client.post(
        f"/api/v1/rides/{ride_id}/riders",
        json={"name": "Sam Convoy", "bike_model": "Suzuki V-Strom"},
    )
    assert add_resp.status_code == 201
    third_rider_id = add_resp.json()["id"]

    # 5. List riders
    list_resp = client.get(f"/api/v1/rides/{ride_id}/riders")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 3

    # 6. Update a rider's status
    status_resp = client.patch(
        f"/api/v1/rides/{ride_id}/riders/{joined_rider_id}/status",
        json={"status": "delayed"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "delayed"

    # 7. Submit GPS locations for the leader and a group member
    leader_id = ride["created_by_rider_id"]
    leader_loc_resp = client.put(
        f"/api/v1/rides/{ride_id}/riders/{leader_id}/location",
        json={"latitude": 38.57, "longitude": -109.56, "speed_kmh": 80.47},
    )
    assert leader_loc_resp.status_code == 200

    loc_resp = client.put(
        f"/api/v1/rides/{ride_id}/riders/{third_rider_id}/location",
        json={"latitude": 38.57, "longitude": -109.55, "speed_kmh": 83.69},
    )
    assert loc_resp.status_code == 200
    assert loc_resp.json()["latitude"] == 38.57

    # 8. Get group locations
    group_loc_resp = client.get(f"/api/v1/rides/{ride_id}/locations")
    assert group_loc_resp.status_code == 200
    entries = group_loc_resp.json()["riders"]
    assert len(entries) == 3
    third_entry = next(e for e in entries if e["rider_id"] == third_rider_id)
    assert third_entry["location"]["latitude"] == 38.57
    assert third_entry["distance_from_leader_km"] is not None
    assert 0.86 < third_entry["distance_from_leader_km"] < 0.89

    # 9. Send a chat message
    chat_resp = client.post(
        f"/api/v1/rides/{ride_id}/chat",
        json={"rider_id": third_rider_id, "text": "Pulling over for gas."},
    )
    assert chat_resp.status_code == 201
    assert chat_resp.json()["rider_name"] == "Sam Convoy"

    # 10. List chat messages
    chat_list_resp = client.get(f"/api/v1/rides/{ride_id}/chat")
    assert chat_list_resp.status_code == 200
    assert len(chat_list_resp.json()) == 1


def test_join_with_invalid_code_returns_404():
    response = client.post(
        "/api/v1/rides/join",
        json={"invite_code": "CONVOY-NOPE", "rider_name": "Nobody"},
    )
    assert response.status_code == 404


def test_get_unknown_ride_returns_404():
    response = client.get("/api/v1/rides/ride_does_not_exist")
    assert response.status_code == 404

