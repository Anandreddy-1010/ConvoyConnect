
/**
 * ConvoyConnect API client
 */

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "/api/v1";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(
      "Could not reach the ConvoyConnect backend. Is it running on http://127.0.0.1:8000?",
      0
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;

    try {
      const body = await response.json();
      if (body?.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // Keep the generic message.
    }

    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return null;

  return response.json();
}

/* Health */
export const healthCheck = () => request("/health");

/* Rides */
export const createRide = (payload) =>
  request("/rides", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const joinRide = (payload) =>
  request("/rides/join", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getRide = (rideId) => request(`/rides/${rideId}`);

/* Riders */
export const addRider = (rideId, payload) =>
  request(`/rides/${rideId}/riders`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getRiders = (rideId) =>
  request(`/rides/${rideId}/riders`);

export const updateRiderStatus = (rideId, riderId, status) =>
  request(`/rides/${rideId}/riders/${riderId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

/* Locations */
export const updateRiderLocation = (rideId, riderId, payload) =>
  request(`/rides/${rideId}/riders/${riderId}/location`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });

export const getGroupLocations = (rideId) =>
  request(`/rides/${rideId}/locations`);

/* Chat */
export const sendChatMessage = (rideId, payload) =>
  request(`/rides/${rideId}/chat`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getChatMessages = (rideId) =>
  request(`/rides/${rideId}/chat`);

/* NLP */
export const predictMessageIntent = (text) =>
  request("/nlp/predict", {
    method: "POST",
    body: JSON.stringify({ text }),
  });

export const getNLPStatus = () => request("/nlp/status");

/* Route Intelligence */
export const getNearbyFacilities = ({
  latitude,
  longitude,
  facility_type = "fuel",
  radius_km = 10,
  limit = 20,
}) => {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    facility_type,
    radius_km: String(radius_km),
    limit: String(limit),
  });

  return request(`/route-intelligence/nearby?${params.toString()}`);
};

/* SOS */
export const createSOS = (rideId, payload) =>
  request(`/sos/${encodeURIComponent(rideId)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getSOSAlerts = (rideId) =>
  request(`/sos/${encodeURIComponent(rideId)}`);

export const resolveSOS = (rideId, alertId) =>
  request(
    `/sos/${encodeURIComponent(rideId)}/${encodeURIComponent(alertId)}/resolve`,
    { method: "PATCH" }
  );

export { ApiError, API_BASE_URL };
export const subscribeToPush = (rideId, riderId, subscription) =>
  request("/push/subscribe", {
    method: "POST",
    body: JSON.stringify({
      ride_id: rideId,
      rider_id: riderId,
      subscription,
    }),
  });
/* Geocoding */
export const searchLocations = (query) => {
  const params = new URLSearchParams({ q: query });
  return request(`/geocoding/search?${params.toString()}`);
};
