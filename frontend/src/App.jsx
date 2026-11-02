import React, { useState, useMemo, useRef, useEffect } from "react";
import {
  MapPin, Navigation, Phone, MessageSquare, Users, AlertTriangle,
  Radio, Send, X, ChevronRight, ChevronLeft, Flag, Gauge, Clock,
  Fuel, Battery, Signal, Plus, Link2, Copy, Check, ArrowLeft,
  Compass, LocateFixed, Siren, ShieldAlert, PhoneCall, LifeBuoy,
  Bike, Route as RouteIcon, Sparkles, Menu, Home, Loader2, Share2
} from "lucide-react";
import * as api from "./api.js";
import { registerNotifications, showSOSNotification } from "./notifications.js";
import { MapContainer, TileLayer, Marker, Popup, useMap, Polyline } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const EARTH_RADIUS_KM = 6371.0088;

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (degrees) => degrees * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLon / 2) ** 2;

  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a))));
}

function calculateRoadProgress(routePositions, current) {
  if (!routePositions || routePositions.length < 2 || !current) return null;

  const valid = [current.latitude, current.longitude].every(Number.isFinite);
  if (!valid) return null;

  const segmentLengths = [];
  let totalKm = 0;

  for (let i = 1; i < routePositions.length; i++) {
    const [lat1, lon1] = routePositions[i - 1];
    const [lat2, lon2] = routePositions[i];
    const km = haversineKm(lat1, lon1, lat2, lon2);
    segmentLengths.push(km);
    totalKm += km;
  }

  if (totalKm <= 0) return null;

  let nearest = { distance: Infinity, covered: 0 };
  let covered = 0;

  for (let i = 1; i < routePositions.length; i++) {
    const [lat1, lon1] = routePositions[i - 1];
    const [lat2, lon2] = routePositions[i];

    const meanLat = (lat1 + lat2 + current.latitude) / 3;
    const scaleX = Math.cos(meanLat * Math.PI / 180);

    const ax = lon1 * scaleX;
    const ay = lat1;
    const bx = lon2 * scaleX;
    const by = lat2;
    const px = current.longitude * scaleX;
    const py = current.latitude;

    const dx = bx - ax;
    const dy = by - ay;
    const denominator = dx * dx + dy * dy;
    const t = denominator ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / denominator)) : 0;

    const projectedLat = lat1 + t * (lat2 - lat1);
    const projectedLon = lon1 + t * (lon2 - lon1);
    const distance = haversineKm(
      current.latitude, current.longitude, projectedLat, projectedLon
    );

    if (distance < nearest.distance) {
      nearest = {
        distance,
        covered: covered + segmentLengths[i - 1] * t
      };
    }

    covered += segmentLengths[i - 1];
  }

  if (nearest.distance > 3.2187) return null;

  const travelled = Math.max(0, Math.min(totalKm, nearest.covered));

  return {
    totalKm,
    travelledKm: travelled,
    remainingKm: totalKm - travelled,
    percentage: Math.round((travelled / totalKm) * 100)
  };
}

function calculateProgress(start, destination, current) {
  if (!start || !destination || !current) return null;

  const points = [start, destination, current];
  if (points.some((p) =>
    !Number.isFinite(p.latitude) ||
    !Number.isFinite(p.longitude) ||
    Math.abs(p.latitude) > 90 ||
    Math.abs(p.longitude) > 180
  )) return null;

  const total = haversineKm(
    start.latitude, start.longitude,
    destination.latitude, destination.longitude
  );

  if (total < 0.001) return null;

  const covered = haversineKm(
    start.latitude, start.longitude,
    current.latitude, current.longitude
  );

  return Math.round(Math.max(0, Math.min(100, covered / total * 100)));
}

/* ======================================================================
   CONVOYCONNECT \u2014 NLP-Based Intelligent Group Ride Assistant
   PHASE 2 \u2014 WIRED TO THE REAL FASTAPI BACKEND (see /backend)
   ----------------------------------------------------------------------
   Component map:
     <App>
       <Landing />
       <CreateRide />        -> api.createRide()
       <JoinRide />          -> api.joinRide()
       <Dashboard>           -> api.getRide() / api.getRiders() / api.getChatMessages(),
                                 polled every few seconds (no websockets yet)
          <TopBar /> <RouteLine />
          <MapPanel />        -> positions are a SYNTHETIC layout, not real GPS
                                  (see adaptRider() below) \u2014 real geospatial
                                  positioning is a Phase 3 goal (app/geospatial)
          <RiderList />       -> real rider data from the backend
          <GroupChat />       -> api.sendChatMessage() / api.getChatMessages()
          <AIAssistantPanel />-> still a prototype placeholder; NLP is not
                                  implemented anywhere (frontend or backend)
          <SOSPanel />        -> still local/mock actions; no backend
                                  emergency-coordination endpoint exists yet
          <RiderDetailsDrawer />
       </Dashboard>

   Fields the backend does not yet provide (distance-from-group, battery,
   ETA, ride-progress %) are rendered as "\u2014" rather than invented, and the
   map's rider positions are an evenly-spaced visual placeholder \u2014 see the
   adapter functions below for exactly what is real vs. synthetic.
   ====================================================================== */

/* ---------------------------- DESIGN TOKENS --------------------------- */
const GlobalStyle = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

    .cc-root{
      --cc-bg:#12161B;
      --cc-panel:#1A2027;
      --cc-panel-2:#212933;
      --cc-line:#2B3440;
      --cc-text:#EDF1F4;
      --cc-muted:#8B98A6;
      --cc-amber:#FF9E2C;
      --cc-amber-dim:#8a5b1f;
      --cc-safety:#C4F135;
      --cc-teal:#3FD1C6;
      --cc-red:#FF4D5E;
      --cc-red-dim:#5a1f26;
      font-family:'Inter',sans-serif;
      background:var(--cc-bg);
      color:var(--cc-text);
    }
    .cc-display{font-family:'Space Grotesk',sans-serif;}
    .cc-mono{font-family:'JetBrains Mono',monospace;}

    .cc-panel{background:var(--cc-panel);border:1px solid var(--cc-line);}
    .cc-panel-2{background:var(--cc-panel-2);border:1px solid var(--cc-line);}
    .cc-border{border-color:var(--cc-line);}
    .cc-muted{color:var(--cc-muted);}
    .cc-amber{color:var(--cc-amber);}
    .cc-bg-amber{background:var(--cc-amber);}
    .cc-safety{color:var(--cc-safety);}
    .cc-teal{color:var(--cc-teal);}
    .cc-red{color:var(--cc-red);}

    .cc-btn-primary{
      background:var(--cc-amber); color:#191204; font-weight:600;
      transition:filter .15s ease, transform .1s ease;
    }
    .cc-btn-primary:hover{filter:brightness(1.08);}
    .cc-btn-primary:active{transform:scale(.98);}

    .cc-btn-ghost{
      background:transparent;border:1px solid var(--cc-line);color:var(--cc-text);
      transition:background .15s ease, border-color .15s ease;
    }
    .cc-btn-ghost:hover{background:var(--cc-panel-2); border-color:#3a4552;}

    .cc-btn-sos{
      background:var(--cc-red); color:#2a0206; font-weight:700;
      box-shadow:0 0 0 0 rgba(255,77,94,.55);
      animation:cc-sos-pulse 2.2s infinite;
    }
    @keyframes cc-sos-pulse{
      0%{box-shadow:0 0 0 0 rgba(255,77,94,.45);}
      70%{box-shadow:0 0 0 14px rgba(255,77,94,0);}
      100%{box-shadow:0 0 0 0 rgba(255,77,94,0);}
    }

    .cc-dot-pulse{animation:cc-dot 2s infinite;}
    @keyframes cc-dot{
      0%{box-shadow:0 0 0 0 rgba(63,209,198,.5);}
      70%{box-shadow:0 0 0 10px rgba(63,209,198,0);}
      100%{box-shadow:0 0 0 0 rgba(63,209,198,0);}
    }

    .cc-scroll::-webkit-scrollbar{width:6px;height:6px;}
    .cc-scroll::-webkit-scrollbar-thumb{background:#333e4a;border-radius:4px;}
    .cc-scroll::-webkit-scrollbar-track{background:transparent;}

    .cc-fade-in{animation:cc-fade .25s ease both;}
    @keyframes cc-fade{from{opacity:0; transform:translateY(4px);} to{opacity:1; transform:translateY(0);}}

    .cc-status-onTrack{background:rgba(196,241,53,.12); color:var(--cc-safety); border:1px solid rgba(196,241,53,.3);}
    .cc-status-delayed{background:rgba(255,158,44,.12); color:var(--cc-amber); border:1px solid rgba(255,158,44,.3);}
    .cc-status-separated{background:rgba(255,77,94,.12); color:var(--cc-red); border:1px solid rgba(255,77,94,.3);}
    .cc-status-stopped{background:rgba(139,152,166,.14); color:var(--cc-muted); border:1px solid rgba(139,152,166,.3);}
    .cc-status-sos{background:rgba(255,77,94,.22); color:#ffcdd2; border:1px solid rgba(255,77,94,.6);}

    .cc-map-grid{
      background-image:
        linear-gradient(rgba(63,209,198,.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(63,209,198,.06) 1px, transparent 1px);
      background-size:34px 34px;
      background-color:#0F1319;
    }
  `}</style>
);

/* ------------------------------ STATUS META ----------------------------- */
const STATUS_META = {
  onTrack: { label: "On track", cls: "cc-status-onTrack" },
  delayed: { label: "Delayed", cls: "cc-status-delayed" },
  separated: { label: "Separated", cls: "cc-status-separated" },
  stopped: { label: "Stopped", cls: "cc-status-stopped" },
  sos: { label: "SOS", cls: "cc-status-sos" },
};

/* ------------------------------ ADAPTERS ------------------------------
   Convert backend API shapes (snake_case, Phase 2 schema) into the shape
   this UI was built around (camelCase, some Phase-1-only display fields).
   Anywhere the backend doesn't yet supply a value, we show "\u2014" instead of
   inventing one \u2014 see DISPLAY() below.
========================================================================= */

// Backend rider.status is "on_track" | "delayed" | "separated" | "stopped" | "sos".
// The UI's STATUS_META keys use "onTrack" for that one case; everything
// else already matches.
function apiStatusToUi(status) {
  return status === "on_track" ? "onTrack" : status;
}

function getInitials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// Renders a value for display, or an em dash when the backend hasn't
// provided one yet (no fabricated numbers/times).
function DISPLAY(value, suffix = "") {
  return value === null || value === undefined || value === "" ? "\u2014" : `${value}${suffix}`;
}

function formatRelativeTime(isoString) {
  if (!isoString) return null;
  const then = new Date(isoString).getTime();
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)} min ago`;
  return `${Math.round(diffSec / 3600)} hr ago`;
}

function adaptRide(apiRide) {
  return {
    id: apiRide.id,
    name: apiRide.name,
    inviteCode: apiRide.invite_code,
    start: {
      name: apiRide.start_location_name,
      latitude: apiRide.start_point?.latitude ?? null,
      longitude: apiRide.start_point?.longitude ?? null,
    },
    destination: {
      name: apiRide.destination_location_name,
      latitude: apiRide.destination_point?.latitude ?? null,
      longitude: apiRide.destination_point?.longitude ?? null,
    },
    // Not computed by the backend yet (no geospatial distance service) \u2014
    // rendered as "\u2014" wherever used, rather than invented.
    totalDistanceKm: null,
    coveredDistanceKm: null,
    createdByRiderId: apiRide.created_by_rider_id,
    riderCount: apiRide.rider_count,
  };
}

// NOTE: `pos`/`progressPct` below are a SYNTHETIC, evenly-spaced visual
// layout \u2014 not derived from real GPS/route data. The backend does not
// compute route progress or map coordinates yet (that's the planned
// app/geospatial work in Phase 3). This just keeps the map/route-line
// visuals populated with something, clearly not a live position feed.
function adaptRider(apiRider, index, total, selfRiderId, groupLocation = null, ride = null) {
  const loc = groupLocation?.location
    ? {
        ...groupLocation.location,
        speed_kmh: groupLocation.speed_kmh,
        recorded_at: groupLocation.recorded_at,
      }
    : apiRider.last_location;
  const latitude = loc?.latitude ?? null;
  const longitude = loc?.longitude ?? null;
  const fallbackX = total > 1 ? 0.12 + (index / (total - 1)) * 0.76 : 0.5;
  const calculatedProgress = calculateProgress(
    ride?.start,
    ride?.destination,
    { latitude, longitude }
  );
  const progressPct = calculatedProgress;
  const x = progressPct !== null ? 0.12 + (progressPct / 100) * 0.76 : fallbackX;
  const y = ((index * 37) % 11) / 100 - 0.05; // small deterministic jitter

  return {
    id: apiRider.id,
    name: apiRider.name,
    initials: getInitials(apiRider.name),
    isSelf: apiRider.id === selfRiderId,
    role: apiRider.role,
    status: apiStatusToUi(apiRider.status),
    speedKmh: loc?.speed_kmh ?? null,
    locationRecordedAt: loc?.recorded_at ?? null,
    progressPct,
    distFromGroupKm: (groupLocation?.distance_from_leader_km ?? null),
    battery: null,          // no device/battery integration
    lastUpdate: formatRelativeTime(loc?.recorded_at) || "no location yet",
    bike: apiRider.bike_model || null,
    phone: apiRider.phone || null,
    eta: null,               // not computed by the backend yet
    pos: { x, y },
    latitude,
    longitude,
    hasLocation:
       typeof latitude === "number" &&
       typeof longitude === "number",
  };
}

function adaptMessage(apiMsg) {
  return {
    id: apiMsg.id,
    riderId: apiMsg.rider_id,
    text: apiMsg.text,
    time: new Date(apiMsg.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
    system: apiMsg.message_type === "system",
  };
}

/* ------------------------------ FALLBACK / DEMO DATA ------------------------------
   Used ONLY when the backend can't be reached (see Dashboard below). Shaped
   exactly like real API responses so the same adapters can process them.
   Dashboard always shows a visible "Demo mode" banner when this is in use \u2014
   it is never presented as if it were live backend data.
========================================================================= */
const FALLBACK_RIDE = {
  id: "demo_ride",
  name: "PNW Coastal Run (offline demo)",
  invite_code: "CONVOY-DEMO",
  status: "active",
  start_location_name: "Seattle, WA",
  destination_location_name: "Astoria, OR",
  created_by_rider_id: "demo_u1",
  created_at: new Date().toISOString(),
  rider_count: 5,
};

const FALLBACK_RIDERS = [
  { id: "demo_u1", ride_id: "demo_ride", name: "You", role: "leader", status: "on_track", phone: null, bike_model: "Triumph Tiger 900", joined_at: new Date().toISOString(), last_location: { speed_kmh: 93.34, recorded_at: new Date().toISOString() } },
  { id: "demo_u2", ride_id: "demo_ride", name: "Marcus Bell", role: "member", status: "on_track", phone: null, bike_model: "Harley-Davidson Pan America", joined_at: new Date().toISOString(), last_location: { speed_kmh: 90.12, recorded_at: new Date().toISOString() } },
  { id: "demo_u3", ride_id: "demo_ride", name: "Priya Nair", role: "member", status: "delayed", phone: null, bike_model: "Kawasaki Versys 650", joined_at: new Date().toISOString(), last_location: { speed_kmh: 65.98, recorded_at: new Date().toISOString() } },
  { id: "demo_u4", ride_id: "demo_ride", name: "Diego Alvarez", role: "member", status: "separated", phone: null, bike_model: "Honda Africa Twin", joined_at: new Date().toISOString(), last_location: null },
  { id: "demo_u5", ride_id: "demo_ride", name: "Sofia Kim", role: "member", status: "stopped", phone: null, bike_model: "Yamaha T\u00E9n\u00E9r\u00E9 700", joined_at: new Date().toISOString(), last_location: null },
];

const FALLBACK_MESSAGES = [
  { id: "demo_m1", ride_id: "demo_ride", rider_id: "demo_u2", rider_name: "Marcus Bell", text: "Fuel stop in 16 km, gas is getting low on mine.", message_type: "text", created_at: new Date().toISOString() },
  { id: "demo_m2", ride_id: "demo_ride", rider_id: "demo_u1", rider_name: "You", text: "Copy that, pulling into the Chevron up ahead.", message_type: "text", created_at: new Date().toISOString() },
  { id: "demo_m3", ride_id: "demo_ride", rider_id: null, rider_name: null, text: "Priya Nair has fallen behind the group.", message_type: "system", created_at: new Date().toISOString() },
];

/* ------------------------------ UTILITIES ------------------------------ */
function initialsColor(id) {
  const palette = ["#FF9E2C", "#3FD1C6", "#C4F135", "#9C8CFF", "#FF7A9E", "#5AC8FA"];
  const idx = id.charCodeAt(id.length - 1) % palette.length;
  return palette[idx];
}

function StatusPill({ status, small }) {
  const meta = STATUS_META[status] || STATUS_META.onTrack;
  return (
    <span className={`cc-mono inline-flex items-center gap-1 rounded-full ${meta.cls} ${small ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs"} uppercase tracking-wide`}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: "currentColor" }} />
      {meta.label}
    </span>
  );
}

function Avatar({ rider, size = 36, ring }) {
  const color = initialsColor(rider.id);
  return (
    <div
      className="rounded-full flex items-center justify-center cc-display font-semibold shrink-0"
      style={{
        width: size, height: size, background: `${color}22`, color,
        border: `1.5px solid ${ring ? color : "transparent"}`,
        fontSize: size * 0.34,
      }}
    >
      {rider.initials}
    </div>
  );
}

/* ============================== ROUTE LINE =============================
   Signature element: a persistent "road" motif \u2014 dashed asphalt line from
   start to destination with rider markers placed by ride progress %.
   Doubles as the visual metaphor for "separated / delayed" detection.
========================================================================= */
function RouteLine({ ride, riders, compact, onSelectRider }) {
  return (
    <div className="cc-panel rounded-2xl p-4 sm:p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 cc-muted text-xs cc-mono uppercase tracking-wider">
          <RouteIcon size={14} className="cc-teal" /> Group Route
        </div>
        <div className="cc-mono text-xs cc-muted">
          {DISPLAY(ride.coveredDistanceKm)} / {DISPLAY(ride.totalDistanceKm, ride.totalDistanceKm ? " km" : "")}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex flex-col items-center shrink-0">
          <Flag size={14} className="cc-amber" />
          <span className="text-[10px] cc-mono cc-muted mt-1 max-w-[64px] text-center leading-tight">{ride.start.name}</span>
        </div>

        <div className="relative flex-1 h-14">
          {/* asphalt line */}
          <div className="absolute top-1/2 left-0 right-0 h-[3px] -translate-y-1/2 rounded-full" style={{ background: "var(--cc-line)" }} />
          {ride.totalDistanceKm ? (
            <div
              className="absolute top-1/2 left-0 h-[3px] -translate-y-1/2 rounded-full"
              style={{ background: "linear-gradient(90deg, var(--cc-teal), var(--cc-amber))", width: `${ride.coveredDistanceKm / ride.totalDistanceKm * 100}%` }}
            />
          ) : null}
          {/* dashed center */}
          <div
            className="absolute top-1/2 left-0 right-0 -translate-y-1/2"
            style={{
              height: 1, backgroundImage: "repeating-linear-gradient(90deg,#0009 0 6px, transparent 6px 12px)",
            }}
          />
          {riders.map((r) => (
            <button
              key={r.id}
              onClick={() => onSelectRider && onSelectRider(r)}
              className="absolute top-1/2 group"
              style={{ left: `${r.progressPct}%`, transform: "translate(-50%,-50%)" }}
              title={r.name}
            >
              <div
                className={`rounded-full flex items-center justify-center text-[9px] cc-display font-bold ${r.isSelf ? "cc-dot-pulse" : ""}`}
                style={{
                  width: compact ? 18 : 24, height: compact ? 18 : 24,
                  background: initialsColor(r.id),
                  color: "#0b0e12",
                  border: r.status === "sos" || r.status === "separated" ? "2px solid var(--cc-red)" : "2px solid #12161B",
                  boxShadow: "0 1px 4px rgba(0,0,0,.4)",
                }}
              >
                {r.isSelf ? "\u2022" : r.initials[0]}
              </div>
            </button>
          ))}
        </div>

        <div className="flex flex-col items-center shrink-0">
          <MapPin size={14} className="cc-teal" />
          <span className="text-[10px] cc-mono cc-muted mt-1 max-w-[64px] text-center leading-tight">{ride.destination.name}</span>
        </div>
      </div>
    </div>
  );
}

/* ================================ MAP PANEL =============================
   Stylized/abstract map (no external tiles \u2014 this is a UI prototype).
   Replace with Mapbox/Leaflet + live GPS feed in production.
========================================================================= */
function MapPanel({
  riders,
  groupLocations,
  startPoint,
  destinationPoint,
  followLocation,
  onEta,
  selfId,
  onSelectRider,
  selectedRiderId,
}) {
  const INDIA_CENTER = [20.5937, 78.9629];
  const [roadProgress, setRoadProgress] = useState(null);

  const locationByRider = Object.fromEntries(
    groupLocations.map((entry) => [
      entry.rider_id,
      entry.location,
    ])
  );

const locatedRiders = riders
  .map((rider) => {
       const location = locationByRider[rider.id];
      if (
        !location ||
        typeof location.latitude !== "number" ||
        typeof location.longitude !== "number" ||
        !Number.isFinite(location.latitude) ||
        !Number.isFinite(location.longitude) ||
        Math.abs(location.latitude) > 90 ||
        Math.abs(location.longitude) > 180
      ) {
        return null;
      }

      return {
        ...rider,
        latitude: location.latitude,
        longitude: location.longitude,
        speedKmh: location.speed_kmh ?? rider.speedKmh,
        locationRecordedAt: location.recorded_at ?? rider.locationRecordedAt,
      };
    })
    .filter(Boolean);

  const selfLocation = locatedRiders.find(
    (rider) => rider.id === selfId
  );

  const center = selfLocation
    ? [selfLocation.latitude, selfLocation.longitude]
    : locatedRiders.length > 0
      ? [
          locatedRiders[0].latitude,
          locatedRiders[0].longitude,
        ]
      : INDIA_CENTER;

  return (
    <div className="cc-panel rounded-2xl overflow-hidden relative">
      <div className="relative h-[360px] sm:h-[440px] w-full">
        <MapContainer
          center={center}
          zoom={locatedRiders.length ? 13 : 5}
          scrollWheelZoom
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <RoadRoute
  startPoint={startPoint}
  destinationPoint={destinationPoint}
  selfLocation={selfLocation}
  onProgress={setRoadProgress}
  onEta={onEta}
/>

          {locatedRiders.map((rider) => {
            if (
              rider.id === selfId &&
              selfLocation &&
              startPoint &&
              haversineKm(
                selfLocation.latitude,
                selfLocation.longitude,
                startPoint.latitude,
                startPoint.longitude
              ) <= 0.0805
            ) return null;

            const isSelected = selectedRiderId === rider.id;

            const icon = L.divIcon({
              className: "",
              html: `
                <div style="
                  width: 34px;
                  height: 34px;
                  border-radius: 50%;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  background: ${initialsColor(rider.id)};
                  color: #0b0e12;
                  border: ${isSelected ? "3px solid white" : "2px solid #12161B"};
                  box-shadow: 0 2px 8px rgba(0,0,0,.5);
                  font-weight: bold;
                  font-size: 11px;
                ">${rider.initials}</div>
              `,
              iconSize: [34, 34],
              iconAnchor: [17, 17],
            });

            return (
              <Marker
                key={rider.id}
                position={[rider.latitude, rider.longitude]}
                icon={icon}
                eventHandlers={{
                  click: () => onSelectRider(rider),
                }}
              >
                <Popup>
                  <strong>{rider.name}</strong>
                  {rider.isSelf && " (you)"}
                  <br />
                  Status: {rider.status}
                  <br />
                  {rider.speedKmh != null
                    ? `Speed: ${(rider.speedKmh).toFixed(1)} km/h`
                    : "Speed unavailable"}
                </Popup>
              </Marker>
            );
          })}

          <MapRecenter center={center} follow={followLocation} />
        </MapContainer>
      </div>

      <div className="p-4 border-t cc-border">
        <div className="flex items-center justify-between mb-2">
          <div className="font-semibold text-sm flex items-center gap-2">
            <RouteIcon size={16} className="cc-teal" />
            Journey Progress
          </div>
          <span className="cc-teal font-bold text-lg">
            {roadProgress ? `${roadProgress.percentage}%` : "--"}
          </span>
        </div>

        <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--cc-line)" }}>
          <div
            className="h-full rounded-full"
            style={{
              width: `${roadProgress?.percentage ?? 0}%`,
              background: "var(--cc-teal)",
              transition: "width 0.5s ease"
            }}
          />
        </div>

        <div className="grid grid-cols-3 gap-2 mt-3 text-center">
          <div>
            <div className="text-xs cc-muted">Travelled</div>
            <div className="text-sm font-semibold">
              {roadProgress ? `${roadProgress.travelledKm.toFixed(1)} km` : "--"}
            </div>
          </div>
          <div>
            <div className="text-xs cc-muted">Remaining</div>
            <div className="text-sm font-semibold">
              {roadProgress ? `${roadProgress.remainingKm.toFixed(1)} km` : "--"}
            </div>
          </div>
          <div>
            <div className="text-xs cc-muted">Total route</div>
            <div className="text-sm font-semibold">
              {roadProgress ? `${roadProgress.totalKm.toFixed(1)} km` : "--"}
            </div>
          </div>
        </div>

        {!roadProgress && (
          <p className="text-xs cc-muted mt-3 text-center">
            Waiting for a valid GPS position near the route.
          </p>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 p-3 border-t cc-border cc-panel-2">
        <div className="flex items-center gap-2 text-xs cc-muted cc-mono">
          <LocateFixed size={14} className="cc-teal" />
          {locatedRiders.length} rider(s) with GPS coordinates
        </div>

        <button
          type="button"
          className="cc-btn-ghost rounded-lg px-3 py-1.5 text-xs flex items-center gap-1.5"
          onClick={() => {
            if (selfLocation) {
              onSelectRider(selfLocation);
            }
          }}
          disabled={!selfLocation}
          title={
            selfLocation
              ? "Select your location"
              : "Your GPS location is not available"
          }
        >
          <Navigation size={13} />
          Select me
        </button>
      </div>
    </div>
  );
} 
function MapRecenter({ center, follow = false }) {
  const map = useMap();

  useEffect(() => {
    if (center && Number.isFinite(center[0]) && Number.isFinite(center[1])) {
      if (follow) {
        map.panTo(center, { animate: true, duration: 0.8 });
      } else {
        map.setView(center, map.getZoom());
      }
    }
  }, [map, center, follow]);

  return null;
}
function RoadRoute({ startPoint, destinationPoint, selfLocation, onProgress, onEta }) {
  const map = useMap();
  const [routePositions, setRoutePositions] = useState([]);
  const fittedRouteRef = useRef(false);
  const [routeDurationSeconds, setRouteDurationSeconds] = useState(null);

  useEffect(() => {
    if (!routePositions.length || !selfLocation) {
      onProgress(null);
      return;
    }

    const progress = calculateRoadProgress(routePositions, {
      latitude: selfLocation.latitude,
      longitude: selfLocation.longitude,
    });

    onProgress(progress);

    const gpsAge = selfLocation.locationRecordedAt ? Date.now() - new Date(selfLocation.locationRecordedAt).getTime() : Infinity;
    const gpsFresh = gpsAge >= 0 && gpsAge <= 120000;
    if (progress && gpsFresh) {
      const speedKmh = Number(selfLocation.speedKmh);
      const remainingSeconds = Number.isFinite(speedKmh) && speedKmh > 5
        ? (progress.remainingKm / speedKmh) * 3600
        : routeDurationSeconds !== null
          ? routeDurationSeconds * (1 - progress.percentage / 100)
          : null;
      if (remainingSeconds === null) { onEta(null); return; }

      const arrivalTime = new Date(Date.now() + remainingSeconds * 1000);

      onEta({
        remainingSeconds,
        arrivalTime: arrivalTime.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit"
        })
      });
    } else {
      onEta(null);
    }
  }, [
    routePositions,
    routeDurationSeconds,
    selfLocation?.latitude,
    selfLocation?.longitude,
    onProgress,
    onEta,
  ]);

  useEffect(() => {
    let cancelled = false;

    const loadRoute = async () => {
      if (
        !startPoint ||
        !destinationPoint ||
        !Number.isFinite(Number(startPoint.latitude)) ||
        !Number.isFinite(Number(startPoint.longitude)) ||
        !Number.isFinite(Number(destinationPoint.latitude)) ||
        !Number.isFinite(Number(destinationPoint.longitude))
      ) {
        setRoutePositions([]);
        return;
      }

      try {
        const url =
          `https://router.project-osrm.org/route/v1/driving/` +
          `${startPoint.longitude},${startPoint.latitude};` +
          `${destinationPoint.longitude},${destinationPoint.latitude}` +
          `?overview=full&geometries=geojson`;

        const response = await fetch(url);
        if (!response.ok) throw new Error("Route request failed");

        const data = await response.json();
        const coordinates = data.routes?.[0]?.geometry?.coordinates;
        const duration = data.routes?.[0]?.duration;

        if (!cancelled) {
          setRouteDurationSeconds(
            Number.isFinite(duration) ? duration : null
          );
        }

        if (!cancelled && data.code === "Ok" && coordinates?.length) {
          setRoutePositions(
            coordinates.map(([longitude, latitude]) => [latitude, longitude])
          );
        } else if (!cancelled) {
          setRoutePositions([]);
        }
      } catch (error) {
        if (!cancelled) {
          setRoutePositions([]);
          console.error("Road route loading failed:", error);
        }
      }
    };

    loadRoute();

    return () => {
      cancelled = true;
    };
  }, [startPoint, destinationPoint]);

  useEffect(() => {
    if (routePositions.length > 1 && !fittedRouteRef.current) {
      const bounds = L.latLngBounds(routePositions);

      if (bounds.isValid()) {
        map.fitBounds(bounds, {
          padding: [35, 35],
          maxZoom: 14,
        });
        fittedRouteRef.current = true;
      }
    }
  }, [map, routePositions]);

  if (!routePositions.length) return null;

  const selfAtStart = selfLocation && startPoint &&
    haversineKm(
      selfLocation.latitude,
      selfLocation.longitude,
      startPoint.latitude,
      startPoint.longitude
    ) <= 0.0805;

  const startIcon = L.divIcon({
    className: "",
    html: `<div style="width:20px;height:20px;background:#22c55e;border:3px solid white;border-radius:50%;box-shadow:0 2px 8px #000"></div>${selfAtStart ? '<span style="background:#22c55e;color:#07120a;padding:2px 5px;border-radius:4px;font-size:10px;font-weight:bold;white-space:nowrap">START / YOU</span>' : ""}`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });

  const destinationIcon = L.divIcon({
    className: "",
    html: '<div style="width:22px;height:22px;background:#ef4444;border:3px solid white;border-radius:50%;box-shadow:0 2px 8px #000"></div>',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });

  return (
    <>
      <Polyline
        positions={routePositions}
        pathOptions={{
          color: "#3FD1C6",
          weight: 5,
          opacity: 0.9,
        }}
      />
      <Marker position={routePositions[0]} icon={startIcon}>
        <Popup>Starting location</Popup>
      </Marker>
      <Marker
        position={routePositions[routePositions.length - 1]}
        icon={destinationIcon}
      >
        <Popup>Destination</Popup>
      </Marker>
    </>
  );
}
/*============================== RIDER LIST ============================== */
function RiderList({ riders, onSelectRider, selectedRiderId }) {
  return (
    <div className="cc-panel rounded-2xl p-4 sm:p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold cc-display">
          <Users size={16} className="cc-amber" /> Riders <span className="cc-muted font-normal">({riders.length})</span>
        </div>
      </div>
      <div className="flex flex-col gap-2 overflow-y-auto cc-scroll pr-1">
        {riders.map((r) => (
          <button
            key={r.id}
            onClick={() => onSelectRider(r)}
            className={`flex items-center gap-3 p-2.5 rounded-xl text-left transition-colors ${selectedRiderId === r.id ? "cc-panel-2" : "hover:bg-white/[0.03]"}`}
          >
            <Avatar rider={r} ring={r.status === "sos" || r.status === "separated"} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium truncate">{r.name}{r.isSelf ? " (you)" : ""}</span>
                {r.role === "leader" && <span className="text-[9px] cc-amber cc-mono uppercase border border-current rounded px-1">Lead</span>}
              </div>
              <div className="text-xs cc-muted cc-mono truncate">{DISPLAY(r.speedKmh != null ? r.speedKmh : null, r.speedKmh != null ? " km/h" : "")} &#183; {DISPLAY(r.distFromGroupKm, r.distFromGroupKm != null ? " km from group" : "")}</div>
            </div>
            <StatusPill status={r.status} small />
          </button>
        ))}
      </div>
    </div>
  );
}

/* ============================== GROUP CHAT =============================== */
function GroupChat({ riders, messages, onSend, intentPredictions }) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);
  const riderMap = useMemo(() => Object.fromEntries(riders.map((r) => [r.id, r])), [riders]);

  useEffect(() => {
  const chat = bottomRef.current?.parentElement;
  if (!chat) return;

  const isNearBottom =
    chat.scrollHeight - chat.scrollTop - chat.clientHeight < 100;

  if (isNearBottom) {
     chat.scrollTo({
     top: chat.scrollHeight,
     behavior: "smooth",
});
  }
}, [messages]);

  const send = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    setSending(true);
    try {
      await onSend(text);
    } catch {
      // onSend already surfaces errors via the parent's error state;
      // put the draft back so the rider doesn't lose their message.
      setDraft(text);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="cc-panel rounded-2xl flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 p-4 border-b cc-border">
        <MessageSquare size={16} className="cc-teal" />
        <span className="text-sm font-semibold cc-display">Group Chat</span>
        <span className="ml-auto text-[10px] cc-mono cc-muted uppercase">{riders.length} online</span>
      </div>

      <div className="flex-1 overflow-y-auto cc-scroll p-4 flex flex-col gap-3">
        {messages.map((m) => {
          if (m.system) {
            return (
              <div key={m.id} className="flex items-center justify-center">
                <span className="text-[11px] cc-mono cc-muted cc-status-delayed px-3 py-1 rounded-full">{m.text}</span>
              </div>
            );
          }
          const rider = riderMap[m.riderId];
          const isSelf = rider?.isSelf;
          return (
            <div key={m.id} className={`flex gap-2 ${isSelf ? "flex-row-reverse" : ""}`}>
              {rider && <Avatar rider={rider} size={28} />}
              <div className={`max-w-[75%] ${isSelf ? "items-end" : "items-start"} flex flex-col`}>
                <span className="text-[10px] cc-muted cc-mono mb-0.5">{rider?.name} &#183; {m.time}</span>
                <div className={`rounded-2xl px-3 py-2 text-sm ${isSelf ? "cc-bg-amber text-[#191204]" : "cc-panel-2"}`}>{m.text}</div>
                {intentPredictions[m.id] && (
                   <span className="text-[10px] cc-muted cc-mono mt-1">
                     AI suggestion: {intentPredictions[m.id]}
                   </span>
                )}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <div className="p-3 border-t cc-border flex items-center gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Message the group&#8230;"
          className="flex-1 bg-transparent cc-panel-2 rounded-full px-4 py-2 text-sm outline-none placeholder:cc-muted"
        />
        <button onClick={send} disabled={sending} className="cc-btn-primary rounded-full w-9 h-9 flex items-center justify-center shrink-0 disabled:opacity-50">
          {sending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
        </button>
      </div>
    </div>
  );
}

/* ========================= AI ASSISTANT PANEL ============================== */
function AIAssistantPanel({ riders = [], ride = null, nearbyFacilities = [] }) {
  const [query, setQuery] = useState("");
  const [asked, setAsked] = useState([]);
  const [asking, setAsking] = useState(false);

  function buildAnswer(intent) {
    const delayed = riders.filter(r => r.status === "delayed");
    const separated = riders.filter(r => r.status === "separated");
    const stopped = riders.filter(r => r.status === "stopped");
    const emergencies = riders.filter(r => r.status === "sos");

    const facilities = (keywords) => {
      const matches = nearbyFacilities.filter(f =>
        keywords.some(k =>
          `${f.category || ""} ${f.name || ""}`.toLowerCase().includes(k)
        )
      );

      return matches.length
        ? matches.slice(0, 3).map(f => `${f.name} (${f.distance_km} km away)`).join("; ")
        : "No matching facilities loaded. Search in Nearby Riding Facilities first.";
    };

    switch (intent) {
      case "REFUELING":
        return "Nearby fuel options: " + facilities(["fuel", "petrol"]);

      case "FOOD_BREAK":
        return "Nearby food options: " + facilities(["food", "restaurant"]);

      case "REST_BREAK":
        return "Nearby accommodation options: " + facilities(["stay", "hotel", "accommodation"]);

      case "VEHICLE_PROBLEM":
        return "Move to a safe place and inspect the motorcycle. Repair options: " + facilities(["repair", "service", "mechanic"]);

      case "TRAFFIC_DELAY":
        return delayed.length
          ? `Riders marked delayed: ${delayed.map(r => r.name).join(", ")}. Live traffic data is not connected.`
          : "No riders are currently marked delayed. Live traffic monitoring is not connected.";

      case "FALLING_BEHIND": {
        const located = riders.filter(
          r => r.hasLocation && Number.isFinite(r.progressPct)
        );

        if (located.length < 2) {
          return "At least two riders with valid GPS locations are required to compare progress.";
        }

        let maximumSeparationKm = 0;

        for (let i = 0; i < located.length; i++) {
          for (let j = i + 1; j < located.length; j++) {
            const distance = haversineKm(
              located[i].latitude, located[i].longitude,
              located[j].latitude, located[j].longitude
            );
            maximumSeparationKm = Math.max(maximumSeparationKm, distance);
          }
        }

        if (maximumSeparationKm < 0.05) {
          return "Riders' GPS positions are within 50 metres of each other. Their individual progress cannot be reliably distinguished. Test with riders at different physical locations.";
        }

        const start = ride?.start;
        const allNearStart = start &&
          Number.isFinite(start.latitude) &&
          Number.isFinite(start.longitude) &&
          located.every(r =>
            haversineKm(
              start.latitude, start.longitude,
              r.latitude, r.longitude
            ) < 0.1
          );

        if (allNearStart) {
          return "The ride appears stationary: all reporting riders are within 100 metres of the starting point. No rider is identified as falling behind.";
        }

        const sorted = [...located].sort(
          (a, b) => a.progressPct - b.progressPct
        );

        if (sorted[sorted.length - 1].progressPct - sorted[0].progressPct < 2) {
          return "Riders have nearly identical estimated progress. There is not enough difference to identify anyone as falling behind.";
        }

        return `${sorted[0].name} has the lowest estimated straight-line progress (${sorted[0].progressPct.toFixed(1)}%). This is an approximate GPS-based comparison, not a verified road-route position.`;
      }

      case "LOST":
        return separated.length
          ? `Riders marked separated: ${separated.map(r => r.name).join(", ")}. Check their last reported locations and contact them.`
          : "No riders are currently marked separated.";

      case "REGROUP_REQUEST": {
        const attention = [...delayed, ...separated, ...stopped];
        return attention.length
          ? `Riders to check before regrouping: ${attention.map(r => `${r.name} (${r.status})`).join(", ")}. No regroup message has been sent.`
          : "No riders are currently marked delayed, separated or stopped.";
      }

      case "DESTINATION_CHANGE":
        return "A destination-change request was detected. Ask the ride leader to update the destination. No automatic change was made.";

      case "EMERGENCY":
        return emergencies.length
          ? `Riders marked SOS: ${emergencies.map(r => r.name).join(", ")}. Check the SOS panel immediately.`
          : "No rider is currently marked SOS in the available data. Use the SOS panel if someone needs emergency assistance.";

      case "STATUS_UPDATE":
        return `Ride: ${ride?.name || "Current ride"}. Total riders: ${riders.length}. On track: ${riders.filter(r => r.status === "onTrack").length}. Delayed: ${delayed.length}. Separated: ${separated.length}. Stopped: ${stopped.length}. SOS: ${emergencies.length}.`;

      case "GENERAL":
      default:
        return `Your convoy has ${riders.length} riders. Ask about rider status, fuel, food, delays, regrouping or emergencies.`;
    }
  }

  async function ask() {
    const text = query.trim();
    if (!text || asking) return;

    setAsking(true);
    setQuery("");

    try {
      const result = await api.predictMessageIntent(text);

      if (!result.parse_succeeded || !result.predicted_intent) {
        setAsked(previous => [...previous, {
          question: text,
          intent: "Unclassified",
          answer: "I couldn't reliably understand that request. Please rephrase it."
        }]);
        return;
      }

      const intent = result.predicted_intent;

      setAsked(previous => [...previous, {
        question: text,
        intent,
        answer: buildAnswer(intent)
      }]);
    } catch (error) {
      setAsked(previous => [...previous, {
        question: text,
        intent: "Unavailable",
        answer: error.message || "Could not connect to the NLP service."
      }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="cc-panel rounded-2xl p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={16} className="cc-teal" />
        <span className="text-sm font-semibold cc-display">Ask ConvoyConnect</span>
        <span className="ml-auto text-[9px] cc-mono uppercase tracking-wide px-2 py-0.5 rounded-full cc-status-delayed">
          AI &middot; NLP
        </span>
      </div>

      <p className="text-xs cc-muted mb-3 leading-relaxed">
        Ask natural-language questions about your convoy, riders, fuel stops and emergencies.
      </p>

      <div className="flex items-center gap-2">
        <input
          value={query}
          maxLength={500}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && ask()}
          placeholder="e.g. Who is furthest behind?"
          className="flex-1 min-w-0 bg-transparent cc-panel-2 rounded-full px-4 py-2 text-sm outline-none placeholder:cc-muted"
          disabled={asking}
        />
        <button
          type="button"
          onClick={ask}
          disabled={asking || !query.trim()}
          className="cc-btn-ghost rounded-full px-4 py-2 text-xs shrink-0 disabled:opacity-50"
        >
          {asking ? "Thinking..." : "Ask"}
        </button>
      </div>

      {asked.length > 0 && (
        <div className="mt-3 flex flex-col gap-2">
          {asked.slice(-3).map((item, i) => (
            <div key={`${item.question}-${i}`} className="cc-panel-2 rounded-xl p-3 text-xs cc-fade-in">
              <div className="cc-mono cc-muted mb-1">You asked</div>
              <div className="mb-2">{item.question}</div>
              <div className="cc-mono cc-teal mb-1">Intent: {item.intent}</div>
              <div className="leading-relaxed">{item.answer}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ================================ SOS PANEL ============================== */

function SOSPanel({
  open,
  onClose,
  riders,
  rideId,
  selfRiderId,
  latestPosition,
}) {
  const [sent, setSent] = useState(null);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [emergencyContactsOpen, setEmergencyContactsOpen] = useState(false);
  const nearest = riders.find((r) => !r.isSelf);

  useEffect(() => {
    if (!open || !rideId) return;

    let cancelled = false;

    async function loadAlerts() {
      try {
        const data = await api.getSOSAlerts(rideId);
        if (!cancelled) setAlerts(data);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }

    loadAlerts();
    const interval = setInterval(loadAlerts, 5000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [open, rideId]);

  if (!open) return null;

  async function sendSOS() {
    if (!rideId || !selfRiderId) {
      setError("Ride or rider ID is missing. Please re-enter the ride.");
      return;
    }

    setSending(true);
    setError(null);
    setSent(null);

    try {
      const payload = {
        rider_id: selfRiderId,
        message: "Emergency! I need help.",
      };

      if (
        latestPosition &&
        Number.isFinite(latestPosition.latitude) &&
        Number.isFinite(latestPosition.longitude)
      ) {
        payload.latitude = latestPosition.latitude;
        payload.longitude = latestPosition.longitude;
      }

      await api.createSOS(rideId, payload);
      setSent("SOS alert created successfully");
      setAlerts(await api.getSOSAlerts(rideId));
    } catch (err) {
      setError(err.message || "Could not send SOS alert.");
    } finally {
      setSending(false);
    }
  }

  async function resolveAlert(alertId) {
    setError(null);

    try {
      await api.resolveSOS(rideId, alertId);
      setAlerts(await api.getSOSAlerts(rideId));
    } catch (err) {
      setError(err.message || "Could not resolve SOS alert.");
    }
  }

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-3 sm:p-4">
      <div className="cc-panel w-full max-w-md max-h-[90vh] overflow-y-auto rounded-2xl p-5 cc-fade-in">
        <div className="flex items-center gap-2 mb-1">
          <Siren size={18} className="cc-red" />
          <span className="cc-display font-semibold text-lg">
            Emergency / SOS
          </span>
          <button
            onClick={onClose}
            className="ml-auto cc-muted hover:text-white"
          >
            <X size={18} />
          </button>
        </div>

        <p className="text-xs cc-muted mb-4">
          Send an SOS alert to your ride group. Location is included only when
          actual coordinates are available.
        </p>

        {sent && (
          <div className="cc-status-onTrack rounded-xl p-4 text-sm mb-4">
            <Check size={16} className="inline mr-2" />
            {sent}
          </div>
        )}

        {error && (
          <div className="rounded-xl p-3 mb-4 text-sm cc-status-separated">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-2.5">
          <button
            onClick={sendSOS}
            disabled={sending}
            className="cc-btn-sos rounded-xl p-3.5 flex items-center gap-3 text-left disabled:opacity-60"
          >
            <ShieldAlert size={20} />
            <span className="flex-1 text-sm">
              <span className="block font-bold">
                {sending ? "Sending SOS..." : "Alert entire group"}
              </span>
              <span className="block text-[11px] opacity-80">
                Create an emergency alert for riders in this group
              </span>
            </span>
          </button>

          <button
            onClick={() => {
              if (nearest?.phone) {
                window.location.href = `tel:${nearest.phone}`;
              } else {
                setError("No phone number is available for another rider.");
              }
            }}
            className="cc-btn-ghost rounded-xl p-3.5 flex items-center gap-3 text-left"
          >
            <PhoneCall size={18} className="cc-teal" />
            <span className="flex-1 text-sm">
              <span className="block font-medium">Call nearest rider</span>
              <span className="block text-[11px] cc-muted">
                {nearest?.name || "No other riders yet"}
              </span>
            </span>
          </button>
<div className="cc-panel-2 rounded-xl p-3">
  <button
    onClick={() => setEmergencyContactsOpen(!emergencyContactsOpen)}
    className="w-full flex items-center justify-between text-left"
  >
    <span className="flex items-center gap-2">
      <LifeBuoy size={18} className="cc-red" />
      <span className="font-semibold text-sm">Emergency Contacts</span>
    </span>
    <span>{emergencyContactsOpen ? "\u25B2" : "\u25BC"}</span>
  </button>

  {emergencyContactsOpen && (
    <div className="grid grid-cols-2 gap-2 mt-3">
      {[
        { name: "Emergency", number: "112", icon: "\u{1F6A8}" },
        { name: "Police", number: "100", icon: "\u{1F46E}" },
        { name: "Fire", number: "101", icon: "\u{1F525}" },
        { name: "Ambulance", number: "102", icon: "\u{1F691}" },
        { name: "Women Helpline", number: "181", icon: "\u{1F469}" },
      ].map((contact) => (
        <button
          key={contact.number}
          onClick={() => {
            window.location.href = `tel:${contact.number}`;
          }}
          className="cc-btn-ghost rounded-lg p-3 text-left"
        >
          <span className="block text-lg">{contact.icon}</span>
          <span className="block text-xs font-medium">{contact.name}</span>
          <span className="block text-xs cc-muted">{contact.number}</span>
        </button>
      ))}
    </div>
  )}
</div>
</div>

        <div className="mt-5">
          <h3 className="font-semibold text-sm mb-2">
            Active group SOS alerts ({alerts.length})
          </h3>

          {alerts.length === 0 ? (
            <p className="text-xs cc-muted">
              No active SOS alerts for this ride.
            </p>
          ) : (
            <div className="space-y-2">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="cc-panel-2 rounded-xl p-3 text-sm"
                >
                  <div className="font-semibold">{alert.rider_name}</div>
                  <p className="text-xs cc-muted mt-1">{alert.message}</p>

                  {alert.latitude != null && alert.longitude != null && (
                    <a
                      className="text-xs underline mt-2 inline-block"
                      href={`https://www.google.com/maps?q=${alert.latitude},${alert.longitude}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open reported coordinates in Maps
                    </a>
                  )}

                  <div className="text-[10px] cc-muted mt-2">
                    {new Date(alert.created_at).toLocaleString()}
                  </div>

                  {alert.rider_id === selfRiderId && (
                    <button
                      onClick={() => resolveAlert(alert.id)}
                      className="cc-btn-ghost rounded-lg px-3 py-1.5 mt-2 text-xs"
                    >
                      Mark resolved
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============================ RIDER DETAILS DRAWER ========================= */
function RiderDetailsDrawer({ rider, eta, onClose }) {
  if (!rider) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <div className="cc-panel w-full sm:w-[360px] h-full p-5 overflow-y-auto cc-scroll cc-fade-in" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="cc-muted hover:text-white mb-4 flex items-center gap-1 text-xs"><ArrowLeft size={14} /> Back</button>

        <div className="flex items-center gap-3 mb-4">
          <Avatar rider={rider} size={56} ring />
          <div>
            <div className="cc-display font-semibold text-lg">{rider.name}{rider.isSelf ? " (you)" : ""}</div>
            <div className="text-xs cc-muted">{rider.bike || "\u2014"}</div>
          </div>
        </div>

        <StatusPill status={rider.status} />

        <div className="grid grid-cols-2 gap-2.5 mt-4">
          <Stat icon={<Gauge size={14} className="cc-teal" />} label="Speed" value={DISPLAY(rider.speedKmh != null ? rider.speedKmh : null, rider.speedKmh != null ? " km/h" : "")} />
          <Stat icon={<RouteIcon size={14} className="cc-teal" />} label="From group" value={DISPLAY(rider.distFromGroupKm, rider.distFromGroupKm != null ? " km" : "")} />
          <Stat icon={<Clock size={14} className="cc-teal" />} label="ETA" value={eta ? `${Math.ceil(eta.remainingSeconds / 60)} min · ${eta.arrivalTime}` : "—"} />
          <Stat icon={<Battery size={14} className="cc-teal" />} label="Battery" value={DISPLAY(rider.battery, rider.battery != null ? "%" : "")} />
          <Stat icon={<Signal size={14} className="cc-teal" />} label="Last update" value={rider.lastUpdate} />
          <Stat icon={<Flag size={14} className="cc-teal" />} label="Progress" value={DISPLAY(rider.progressPct, "%")} />
        </div>
        <p className="text-[10px] cc-muted mt-2 leading-relaxed">
          Speed/last-update come from this rider's most recent GPS submission, if any.
          ETA is estimated from the road route and your latest GPS position. Battery and distance-from-group are not currently available.
        </p>

        {!rider.isSelf && (
          <div className="grid grid-cols-2 gap-2.5 mt-5">
            <button className="cc-btn-primary rounded-xl py-2.5 flex items-center justify-center gap-2 text-sm">
              <Phone size={15} /> Call
            </button>
            <button className="cc-btn-ghost rounded-xl py-2.5 flex items-center justify-center gap-2 text-sm">
              <Navigation size={15} /> Navigate to
            </button>
          </div>
        )}

        {(rider.status === "separated" || rider.status === "sos") && (
          <div className="cc-status-separated rounded-xl p-3 mt-4 text-xs flex gap-2 items-start">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>Detected as {rider.status === "sos" ? "in emergency" : "separated from group"} based on GPS drift. Automated detection is a placeholder \u2014 future NLP/GPS service will refine thresholds.</span>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ icon, label, value }) {
  return (
    <div className="cc-panel-2 rounded-xl p-2.5">
      <div className="flex items-center gap-1.5 text-[10px] cc-muted cc-mono uppercase mb-1">{icon}{label}</div>
      <div className="cc-mono font-medium text-sm">{value}</div>
    </div>
  );
}

/* ================================ TOP BAR ================================ */
function TopBar({ ride, riders, onOpenSOS, onBackHome }) {
  const delayedOrWorse = riders.filter((r) => ["delayed", "separated", "sos"].includes(r.status)).length;
  return (
    <div className="cc-panel rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center gap-3">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <button onClick={onBackHome} className="cc-btn-ghost rounded-lg p-2 shrink-0"><Home size={16} /></button>
        <div className="min-w-0">
          <div className="cc-display font-semibold text-base truncate flex items-center gap-2">
            {ride.name}
            {delayedOrWorse > 0 && <span className="text-[9px] cc-mono cc-status-delayed rounded-full px-2 py-0.5 uppercase">{delayedOrWorse} need attention</span>}
          </div>
          <div className="text-xs cc-muted cc-mono truncate">{ride.start.name} &#8594; {ride.destination.name}</div>
        </div>
      </div>

      <div className="flex items-center gap-4 sm:gap-6 cc-mono text-xs">
        <div className="text-center">
          <div className="cc-muted uppercase text-[9px]">Group Dist.</div>
          <div className="text-sm font-medium">{DISPLAY(ride.coveredDistanceKm)}/{DISPLAY(ride.totalDistanceKm, ride.totalDistanceKm ? " km" : "")}</div>
        </div>
        <div className="text-center">
          <div className="cc-muted uppercase text-[9px]">ETA</div>
          <div className="text-sm font-medium cc-teal">&#8212;</div>
        </div>
        <button onClick={onOpenSOS} className="cc-btn-sos rounded-xl px-4 py-2 flex items-center gap-2 text-xs shrink-0">
          <Siren size={14} /> SOS
        </button>
      </div>
    </div>
  );
}

/* ================================ LOCATION SHARE TOGGLE (Phase 3.6) ========
   Opt-in browser Geolocation sharing. Uses the browser's Geolocation API,
   sends to the EXISTING PUT .../riders/{riderId}/location endpoint (no
   backend changes). Sends the most recent known position every 10s via
   a separate interval, decoupled from watchPosition's own firing rate
   (which can be much more frequent than every 10s on some devices).
========================================================================= */
function LocationShareToggle({ enabled, onToggle, error }) {
  return (
    <div className="cc-panel rounded-xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2 text-xs">
        <LocateFixed size={14} className={enabled ? "cc-teal" : "cc-muted"} />
        <span className="cc-mono">
          {enabled ? "Sharing your location every 10s" : "Location sharing is off"}
        </span>
      </div>
      <button
        onClick={() => onToggle(!enabled)}
        className={enabled ? "cc-btn-primary rounded-full px-4 py-1.5 text-xs" : "cc-btn-ghost rounded-full px-4 py-1.5 text-xs"}
      >
        {enabled ? "End Ride" : "Start Ride"}
      </button>
      {error && <span className="cc-red text-[11px] cc-mono">{error}</span>}
    </div>
  );
}

/* ================================ DASHBOARD ================================
   Fetches ride/riders/chat from the real backend on mount, then polls
   every few seconds so other riders' updates eventually show up (there
   are no websockets yet \u2014 see the header comment at the top of this file).
========================================================================= */

function WeatherCard({ location }) {
  const [weather, setWeather] = useState(null);
  const [weatherError, setWeatherError] = useState("");
  const [loadingWeather, setLoadingWeather] = useState(false);
  const [lastChecked, setLastChecked] = useState(null);

  const latitude = location?.latitude;
  const longitude = location?.longitude;

  useEffect(() => {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      setWeather(null);
      return;
    }

    let cancelled = false;

    const loadWeather = async () => {
      setLoadingWeather(true);
      try {
        const url = `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current=temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m,weather_code&timezone=auto`;

        const response = await fetch(url);
        if (!response.ok) throw new Error("Weather service unavailable");

        const data = await response.json();
        if (!cancelled) {
          setWeather(data.current);
          setLastChecked(new Date());
          setWeatherError("");
        }
      } catch (err) {
        if (!cancelled) setWeatherError(err.message);
      } finally {
        if (!cancelled) setLoadingWeather(false);
      }
    };

    loadWeather();
    const timer = setInterval(loadWeather, 15 * 60 * 1000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [latitude, longitude]);

  const weatherDescription = (code) => {
    if (code === 0) return "Clear sky";
    if ([1, 2, 3].includes(code)) return "Partly cloudy";
    if ([45, 48].includes(code)) return "Foggy";
    if ([51, 53, 55, 61, 63, 65, 80, 81, 82].includes(code)) return "Rain";
    if ([71, 73, 75, 77, 85, 86].includes(code)) return "Snow";
    if ([95, 96, 99].includes(code)) return "Thunderstorm";
    return "Conditions unavailable";
  };

  return (
    <div className="cc-panel rounded-2xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-semibold text-sm">Live Weather</h3>
          <p className="text-xs cc-muted mt-1">Weather near your GPS location</p>
        </div>
        <span className="text-2xl">🌤️</span>
      </div>

      {loadingWeather && !weather && (
        <p className="cc-muted text-xs">Loading weather...</p>
      )}

      {weatherError && (
        <p className="cc-red text-xs">{weatherError}</p>
      )}

      {!Number.isFinite(latitude) && (
        <p className="cc-muted text-xs">
          Start GPS sharing to view local weather.
        </p>
      )}

      {weather && (
        <>
          <div className="text-3xl font-semibold cc-display">
            {weather.temperature_2m}°C
          </div>
          <p className="text-sm cc-muted mt-1">
            {weatherDescription(weather.weather_code)}
          </p>

          <div className="grid grid-cols-3 gap-3 mt-4">
            <div>
              <div className="text-xs cc-muted">Humidity</div>
              <div className="text-sm font-semibold">
                {weather.relative_humidity_2m}%
              </div>
            </div>
            <div>
              <div className="text-xs cc-muted">Rain</div>
              <div className="text-sm font-semibold">
                {weather.precipitation} mm
              </div>
            </div>
            <div>
              <div className="text-xs cc-muted">Wind</div>
              <div className="text-sm font-semibold">
                {weather.wind_speed_10m} km/h
              </div>
            </div>
          </div>
          <div className="text-[10px] cc-muted mt-3 space-y-1">
            <p>Last checked: {lastChecked ? lastChecked.toLocaleString([], { dateStyle: "long", timeStyle: "short" }) : "Waiting..."}</p>
            <p>Next refresh: {lastChecked ? new Date(lastChecked.getTime() + 15 * 60 * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Pending"}</p>
            <p>Weather source: Open-Meteo</p>
          </div>
        </>
      )}
    </div>
  );
}

function Dashboard({ rideId, selfRiderId, onBackHome }) {
  const [ride, setRide] = useState(null);
  const [riders, setRiders] = useState([]);
  const [messages, setMessages] = useState([]);
  const [groupLocations, setGroupLocations] = useState([]);
  const [routeEta, setRouteEta] = useState(null);
  const [intentPredictions, setIntentPredictions] = useState({});
  const [rideAlerts, setRideAlerts] = useState([]);
  const [nearbyFacilities, setNearbyFacilities] = useState([]);
  const [facilityType, setFacilityType] = useState("fuel");
  const [facilityLoading, setFacilityLoading] = useState(false);
  const [facilityError, setFacilityError] = useState(null);
  const [facilitySearchDone, setFacilitySearchDone] = useState(false);
  const processedAlertIds = useRef(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [demoMode, setDemoMode] = useState(false);
  const [selectedRider, setSelectedRider] = useState(null);
  const [sosOpen, setSosOpen] = useState(false);
  const [tab, setTab] = useState("map"); // map | riders | chat  (mobile)

  // ---- Phase 3.6: opt-in browser GPS sharing state ----
  const [locationSharing, setLocationSharing] = useState(false);
  const [locationError, setLocationError] = useState(null);
  const watchIdRef = useRef(null);
  const latestPositionRef = useRef(null);
  const sendIntervalRef = useRef(null);

// Check for incoming SOS alerts every 5 seconds
useEffect(() => {
  if (!rideId) return;

  let cancelled = false;

  async function checkSOSAlerts() {
    try {
      const alerts = await api.getSOSAlerts(rideId);

      if (cancelled || !Array.isArray(alerts)) return;

      for (const alert of alerts) {
        if (knownSOSIdsRef.current.has(alert.id)) continue;

        knownSOSIdsRef.current.add(alert.id);

        // Don't alarm the rider who sent the SOS
        if (alert.rider_id === selfRiderId) continue;

        setIncomingSOS(alert);

        // Play an alarm sound when browser audio is available
        try {
          if (!alarmAudioRef.current) {
            alarmAudioRef.current = new Audio(
              "https://actions.google.com/sounds/v1/alarms/alarm_clock.ogg"
            );
            alarmAudioRef.current.loop = true;
          }

          alarmAudioRef.current.currentTime = 0;
          await alarmAudioRef.current.play();
        } catch {
          // Browser may block audio until the user interacts with the page.
        }

        // Display the first newly detected alert
        break;
      }
    } catch (err) {
      console.error("SOS monitoring failed:", err.message);
    }
  }

  checkSOSAlerts();
  const interval = setInterval(checkSOSAlerts, 5000);

  return () => {
    cancelled = true;
    clearInterval(interval);
  };
}, [rideId, selfRiderId]);


  // Automatic SOS alert monitoring
  const [incomingSOS, setIncomingSOS] = useState(null);
  const knownSOSIdsRef = useRef(new Set());
  const alarmAudioRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function load(isFirstLoad) {
      try {
        const [rideRes, ridersRes, chatRes, locationsRes] = await Promise.all([
  api.getRide(rideId),
  api.getRiders(rideId),
  api.getChatMessages(rideId),
  api.getGroupLocations(rideId),
]);
        if (cancelled) return;
        const adaptedRide = adaptRide(rideRes);
        setRide(adaptedRide);
        setGroupLocations(locationsRes.riders || []);
        const groupLocationByRider = new Map(
          (locationsRes.riders || []).map((entry) => [entry.rider_id, entry])
        );
        setRiders(ridersRes.map((r, i) =>
          adaptRider(r, i, ridersRes.length, selfRiderId, groupLocationByRider.get(r.id), adaptedRide)
        ));
        setMessages(chatRes.map(adaptMessage));
        setError(null);
        setDemoMode(false);
      } catch (err) {
        if (cancelled) return;
        if (isFirstLoad) {
          setRide(adaptRide(FALLBACK_RIDE));
          setRiders(FALLBACK_RIDERS.map((r, i) => adaptRider(r, i, FALLBACK_RIDERS.length, FALLBACK_RIDERS[0].id)));
          setMessages(FALLBACK_MESSAGES.map(adaptMessage));
          setDemoMode(true);
        }
        setError(err.message || "Could not reach the ConvoyConnect backend.");
      } finally {
        if (!cancelled && isFirstLoad) setLoading(false);
      }
    }

    load(true);
    const interval = setInterval(() => load(false), 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rideId, selfRiderId]);

  // ---- Phase 3.6: start/stop GPS watch + throttled 10s sends ----
  useEffect(() => {
    if (!locationSharing) {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
      if (sendIntervalRef.current !== null) {
        clearInterval(sendIntervalRef.current);
        sendIntervalRef.current = null;
      }
      return;
    }

    if (!("geolocation" in navigator)) {
      setLocationError("Geolocation is not supported by this browser.");
      setLocationSharing(false);
      return;
    }

    setLocationError(null);
    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        latestPositionRef.current = pos;
      },
      (err) => {
        setLocationError(err.message || "Could not get your location.");
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
    );

    const sendLatest = async () => {
      const pos = latestPositionRef.current;
      if (!pos || demoMode) return;
      const payload = {
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
      };
      const speedMps = pos.coords.speed; // meters/second, or null if unavailable
      if (typeof speedMps === "number" && !Number.isNaN(speedMps)) {
        payload.speed_kmh = Math.max(0, speedMps * 3.6); // m/s -> km/h
      }
      if (typeof pos.coords.heading === "number" && !Number.isNaN(pos.coords.heading)) {
        payload.heading_deg = pos.coords.heading;
      }
      try {
        await api.updateRiderLocation(rideId, selfRiderId, payload);
      } catch (err) {
        setLocationError(err.message || "Failed to send location to the backend.");
      }
    };

    sendIntervalRef.current = setInterval(sendLatest, 10000);

    return () => {
  if (watchIdRef.current !== null) {
    navigator.geolocation.clearWatch(watchIdRef.current);
    watchIdRef.current = null;
  }

  if (sendIntervalRef.current !== null) {
    clearInterval(sendIntervalRef.current);
    sendIntervalRef.current = null;
  }

  latestPositionRef.current = null;
};
  }, [locationSharing, rideId, selfRiderId, demoMode]);
    // Phase 4.0: Search nearby facilities using the latest available GPS position.
  const searchNearbyFacilities = async () => {
    const latestLocation = latestPositionRef.current?.coords;

    const savedLocation = groupLocations.find(
      (rider) => rider.rider_id === selfRiderId && rider.location
    )?.location;

    const latitude = latestLocation?.latitude ?? savedLocation?.latitude;
    const longitude = latestLocation?.longitude ?? savedLocation?.longitude;

    if (latitude == null || longitude == null) {
      setFacilityError(
        "Location unavailable. Enable GPS sharing or submit a location first."
      );
      setNearbyFacilities([]);
      return;
    }
    setFacilitySearchDone(true);
    setFacilityLoading(true);
    setFacilityError(null);

    try {
      const response = await api.getNearbyFacilities({
        latitude,
        longitude,
        facility_type: facilityType,
        radius_km: 15,
        limit: 20,
      });

      setNearbyFacilities(response.results || []);
    } catch (err) {
      setFacilityError("Nearby facilities are temporarily unavailable. Please try again.");
      setNearbyFacilities([]);
    } finally {
      setFacilityLoading(false);
    }
  };
  const handleSend = async (text) => {
  if (demoMode) {
    setMessages((m) => [
      ...m,
      {
        id: `local_${Date.now()}`,
        riderId: selfRiderId,
        text,
        time: "now",
        system: false,
      },
    ]);
    return;
  }

  // Send the chat message and capture its unique ID.
  const sentMessage = await api.sendChatMessage(rideId, {
    rider_id: selfRiderId,
    text,
  });

 // Refresh the chat normally.
  const chatRes = await api.getChatMessages(rideId);
  const updatedMessages = chatRes.map(adaptMessage);
  setMessages(updatedMessages); 
 // NLP prediction is disabled because the backend NLP service is off.
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 cc-muted text-sm cc-mono">
        <Loader2 size={20} className="animate-spin cc-teal" /> Loading ride\u2026
      </div>
    );
  }
  
  async function enablePushNotifications() {
  try {
    const { subscription } = await registerNotifications();

    await api.subscribeToPush(
      rideId,
      selfRiderId,
      subscription.toJSON()
    );

    alert("SOS notifications enabled successfully!");
  } catch (error) {
    console.error("Notification setup failed:", error);
    alert(error.message || "Could not enable notifications.");
  }
}
  return (
    <div className="max-w-[1400px] mx-auto p-3 sm:p-5 flex flex-col gap-4">
       {rideAlerts.length > 0 && (
  <div className="cc-panel rounded-2xl p-4">
    <div className="flex items-center gap-2 mb-3">
      <AlertTriangle size={18} className="cc-amber" />
      <h3 className="font-semibold text-sm">
        Ride assistance alerts
      </h3>
      <span className="cc-muted text-xs">
        ({rideAlerts.length})
      </span>
    </div>

    <div className="flex flex-col gap-2">
      {rideAlerts.map((alert) => (
        <div
          key={alert.id}
          className="cc-panel-2 rounded-xl p-3"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">
                {alert.title}
              </div>
              <p className="text-xs cc-muted mt-1">
                {alert.message}
              </p>
              <span className="text-[10px] cc-mono cc-muted mt-2 block">
                {alert.createdAt} &#183; AI suggestion &#8212; verify before acting
              </span>
            </div>

            <button
              type="button"
              className="cc-btn-ghost rounded-lg px-2 py-1 text-xs"
              onClick={() =>
                setRideAlerts((previous) =>
                  previous.filter((item) => item.id !== alert.id)
                )
              }
              aria-label={`Dismiss ${alert.title}`}
            >
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  </div>
)}

      {demoMode && (
        <div className="cc-status-delayed rounded-xl px-4 py-2.5 text-xs flex items-center gap-2 cc-fade-in">
          <AlertTriangle size={14} className="shrink-0" />
          <span>
            <strong>Demo mode</strong> \u2014 couldn't reach the backend ({error}). Showing local sample data;
            nothing here is being saved. Start the backend (<code className="cc-mono">uvicorn app.main:app --reload</code>) and refresh to go live.
          </span>
        </div>
      )}
      {!demoMode && error && (
        <div className="cc-status-separated rounded-xl px-4 py-2.5 text-xs flex items-center gap-2 cc-fade-in">
          <AlertTriangle size={14} className="shrink-0" /> {error}
        </div>
      )}

      <TopBar ride={ride} riders={riders} onOpenSOS={() => setSosOpen(true)} onBackHome={onBackHome} />
      <RouteLine
  ride={ride}
  riders={riders}
  onSelectRider={setSelectedRider}
/>
      {/* Phase 3.6: opt-in browser GPS sharing toggle */}
      <LocationShareToggle enabled={locationSharing} onToggle={setLocationSharing} error={locationError} />

      {/* mobile tab switcher */}
      <div className="flex sm:hidden cc-panel rounded-xl p-1 gap-1">
        {["map", "riders", "chat"].map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`flex-1 rounded-lg py-2 text-xs capitalize ${tab === t ? "cc-btn-primary" : "cc-muted"}`}>{t}</button>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_320px] gap-4">
        <div className={`flex-col gap-4 ${tab === "map" ? "flex" : "hidden"} sm:flex`}>
        <MapPanel
  riders={riders}
  groupLocations={groupLocations}
  startPoint={ride?.start}
  destinationPoint={ride?.destination}
  followLocation={locationSharing}
  onEta={setRouteEta}
  selfId={selfRiderId}
  onSelectRider={setSelectedRider}
  selectedRiderId={selectedRider?.id}
/>
          <WeatherCard
            location={groupLocations.find(
              (rider) => rider.rider_id === selfRiderId && rider.location
            )?.location}
          />
                     {/* Phase 4.0: Nearby riding facilities */}
          <div className="cc-panel rounded-2xl p-4">
            <div className="flex items-center justify-between gap-3 mb-3">
              <div>
                <h3 className="font-semibold text-sm">
                  Nearby Riding Facilities
                </h3>
                <p className="text-xs cc-muted mt-1">
                  Discover services near your available GPS location.
                </p>
              </div>
              <MapPin size={18} className="cc-teal shrink-0" />
            </div>

            <div className="flex flex-wrap gap-2 mb-3">
              {[
                ["fuel", "Petrol Pumps"],
                ["restaurant", "Food"],
                ["repair", "Bike Repair"],
                ["medical", "Medical"],
                ["accommodation", "Rooms / Stays"],
              ].map(([type, label]) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setFacilityType(type)}
                  className={`rounded-lg px-3 py-2 text-xs ${
                    facilityType === type
                      ? "cc-btn-primary"
                      : "cc-btn-ghost"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={searchNearbyFacilities}
              disabled={facilityLoading}
              className="cc-btn-primary rounded-lg px-4 py-2 text-sm disabled:opacity-50"
            >
              {facilityLoading ? "Searching..." : "Find Nearby Facilities"}
            </button>

            {facilityError && (
              <p className="cc-red text-xs mt-3">{facilityError}</p>
            )}

            {!facilityError && nearbyFacilities.length === 0 &&
  !facilityLoading && !facilitySearchDone && (
    <p className="cc-muted text-xs mt-3">
      Select a facility type and search to see nearby results.
    </p>
)}

{!facilityError && nearbyFacilities.length === 0 &&
  !facilityLoading && facilitySearchDone && (
    <p className="cc-muted text-xs mt-3">
      No matching facilities were found nearby. Try another category
      or location.
    </p>
)}

            <div className="flex flex-col gap-2 mt-3">
              {nearbyFacilities.map((facility) => (
                <div
                  key={facility.id}
                  className="cc-panel-2 rounded-xl p-3"
                >
                  <div className="text-sm font-semibold">
                    {facility.name}
                  </div>
                  <div className="text-xs cc-muted mt-1">
                    {facility.category} &#183; {facility.distance_km} km away
                  </div>

                  {facility.opening_hours && (
                    <div className="text-xs cc-muted mt-1">
                      Hours: {facility.opening_hours}
                    </div>
                  )}

                  {facility.phone && (
                    <div className="text-xs cc-muted mt-1">
                      Phone: {facility.phone}
                    </div>
                  )}

                  <a
                    href={`https://www.google.com/maps/dir/?api=1&destination=${facility.latitude},${facility.longitude}&travelmode=driving`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="cc-teal text-xs mt-2 inline-block"
                  >
                    Get Directions on Google Maps &#8599;
                  </a>
                </div>
              ))}
            </div>

            {nearbyFacilities.length > 0 && (
              <p className="cc-muted text-[10px] opacity-70 mt-3">
                Distances are straight-line estimates. Verify facility details
                before relying on them.
              </p>
            )}
          </div>
          <AIAssistantPanel
            riders={riders}
            ride={ride}
            nearbyFacilities={nearbyFacilities}
            rideAlerts={rideAlerts}
          />
        </div>

        <div className="grid grid-cols-1 gap-4">
          <div className={`${tab === "riders" ? "block" : "hidden"} sm:block h-[280px] sm:h-[300px]`}>
            <RiderList riders={riders} onSelectRider={setSelectedRider} selectedRiderId={selectedRider?.id} />
          </div>
          <div className={`${tab === "chat" ? "block" : "hidden"} sm:block h-[340px] sm:h-[360px]`}>
            <GroupChat riders={riders} messages={messages} onSend={handleSend} intentPredictions={intentPredictions} />
          </div>
        </div>
      </div>

      <RiderDetailsDrawer rider={selectedRider} eta={selectedRider?.isSelf ? routeEta : null} onClose={() => setSelectedRider(null)} />
      <SOSPanel
  open={sosOpen}
  onClose={() => setSosOpen(false)}
  riders={riders}
  rideId={rideId}
  selfRiderId={selfRiderId}
  latestPosition={latestPositionRef.current}
/>
<button
  type="button"
  onClick={enablePushNotifications}
  className="cc-btn-primary rounded-xl px-4 py-2"
>
  Enable SOS Notifications
</button>

{incomingSOS && (
  <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/70 p-4">
    <div className="cc-panel w-full max-w-md rounded-2xl border border-red-500 p-5">
      <div className="flex items-center gap-3 mb-3">
        <Siren size={28} className="cc-red" />
        <h2 className="cc-display text-xl font-bold">
          EMERGENCY SOS ALERT
        </h2>
      </div>

      <p className="text-sm mb-2">
        <strong>{incomingSOS.rider_name}</strong> needs help!
      </p>

      <p className="text-sm cc-muted mb-4">
        {incomingSOS.message}
      </p>

      {incomingSOS.latitude != null &&
        incomingSOS.longitude != null && (
          <a
            href={`https://www.google.com/maps?q=${incomingSOS.latitude},${incomingSOS.longitude}`}
            target="_blank"
            rel="noreferrer"
            className="underline text-sm block mb-4"
          >
            View reported location
          </a>
        )}

      <button
        className="cc-btn-primary w-full rounded-xl p-3"
        onClick={() => {
          if (alarmAudioRef.current) {
            alarmAudioRef.current.pause();
            alarmAudioRef.current.currentTime = 0;
          }
          setIncomingSOS(null);
        }}
      >
        Acknowledge / Stop Alarm
      </button>
    </div>
  </div>
)}

    </div>
  );
}

/* ================================ LANDING ================================ */
function Landing({ onCreate, onJoin, onResume }) {
  return (
    <div className="min-h-screen bg-[#080b0e] text-white overflow-hidden">

      {/* HERO BACKGROUND */}
      <section
        className="relative min-h-[min(90vh,760px)] flex flex-col justify-center"
        style={{
          backgroundImage:
            "linear-gradient(90deg, rgba(5,9,13,.97) 0%, rgba(5,9,13,.82) 48%, rgba(5,9,13,.30) 100%), linear-gradient(0deg, #080b0e 0%, transparent 45%), url('https://images.unsplash.com/photo-1558981806-ec527fa84c39?auto=format&fit=crop&w=2000&q=85')",
          backgroundSize: "cover",
          backgroundPosition: "center"
        }}
      >

        {/* NAVBAR */}
        <nav className="absolute top-0 left-0 w-full px-4 sm:px-6 md:px-12 py-4 sm:py-6 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <Bike size={27} className="text-orange-500" />
            <span className="text-xl font-bold tracking-wider">
              CONVOY<span className="text-orange-500">CONNECT</span>
            </span>
          </div>

          <span className="hidden sm:block text-xs tracking-[3px] text-gray-300">
            RIDE TOGETHER. EXPLORE FURTHER.
          </span>
        </nav>

        {/* HERO CONTENT */}
        <div className="relative z-10 max-w-7xl mx-auto w-full px-4 sm:px-6 md:px-12 pt-24 sm:pt-28 pb-12 sm:pb-16">

          <div className="max-w-2xl">

            <div className="inline-flex items-center gap-2 border border-orange-500/40 bg-black/40 rounded-full px-4 py-2 mb-7">
              <span className="w-2 h-2 rounded-full bg-orange-500"></span>
              <span className="text-orange-400 text-xs tracking-[2px] uppercase">
                Smart Motorcycle Convoy Platform
              </span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-7xl font-extrabold leading-[1.05] tracking-tight">
              RIDE
              <span className="text-orange-500"> TOGETHER.</span>
              <br />
              EXPLORE
              <br />
              FURTHER.
            </h1>

            <p className="text-gray-300 text-base sm:text-lg leading-relaxed mt-5 sm:mt-7 max-w-xl">
              Every road becomes an adventure when you ride together.
              Stay connected with live location tracking, group communication
              and emergency assistance.
            </p>

            {/* ACTION BUTTONS */}
            <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3 sm:gap-4 mt-7 sm:mt-9">

              <button
                onClick={onCreate}
                className="bg-orange-500 hover:bg-orange-600 text-black font-bold rounded-lg px-5 sm:px-7 py-3 sm:py-4 flex items-center justify-center gap-2 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg active:scale-95"
              >
                <Plus size={19} />
                CREATE A RIDE
              </button>

              <button
                onClick={onJoin}
                className="border border-white/40 hover:border-orange-500 hover:text-orange-400 rounded-lg px-5 sm:px-7 py-3 sm:py-4 flex items-center justify-center gap-2 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg active:scale-95"
              >
                <Link2 size={19} />
                JOIN A CONVOY
              </button>

              {onResume && (
                <button
                  onClick={onResume}
                  className="border border-white/40 hover:border-orange-500 rounded-lg px-5 sm:px-6 py-3 sm:py-4 flex items-center justify-center gap-2 transition-all duration-300 hover:-translate-y-1 hover:border-orange-500 active:scale-95"
                >
                  <ChevronRight size={19} />
                  RESUME RIDE
                </button>
              )}

            </div>

            <div className="flex flex-wrap gap-5 sm:gap-8 mt-8 sm:mt-12 text-sm text-gray-300">
              <div>
                <MapPin className="text-orange-500 mb-2" size={21} />
                Live GPS
              </div>
              <div>
                <MessageSquare className="text-orange-500 mb-2" size={21} />
                Group Chat
              </div>
              <div>
                <AlertTriangle className="text-orange-500 mb-2" size={21} />
                Route Alerts
              </div>
              <div>
                <Siren className="text-orange-500 mb-2" size={21} />
                SOS Support
              </div>
            </div>

          </div>
        </div>

        <div className="absolute bottom-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-orange-500/70 to-transparent"></div>
      </section>

      {/* FEATURES */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 md:px-12 py-10 sm:py-14">

        <div className="mb-8">
          <p className="text-orange-500 text-xs tracking-[3px] uppercase mb-2">
            Built for every journey
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold">
            YOUR CONVOY. YOUR ADVENTURE.
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">

          {[
            {
              icon: <MapPin size={25} />,
              title: "Live Tracking",
              description: "Keep track of riders and their locations."
            },
            {
              icon: <AlertTriangle size={25} />,
              title: "Route Intelligence",
              description: "Stay informed about delays and route conditions."
            },
            {
              icon: <MessageSquare size={25} />,
              title: "Group Communication",
              description: "Stay connected with your riding group."
            },
            {
              icon: <Siren size={25} />,
              title: "Emergency SOS",
              description: "Send emergency alerts to your convoy."
            }
          ].map((feature, index) => (
            <div
              key={index}
              className="bg-[#111820] border border-white/10 hover:border-orange-500/60 rounded-xl p-5 sm:p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl"
            >
              <div className="text-orange-500 mb-5">
                {feature.icon}
              </div>

              <h3 className="font-bold text-lg mb-2">
                {feature.title}
              </h3>

              <p className="text-gray-400 text-sm leading-relaxed">
                {feature.description}
              </p>
            </div>
          ))}

        </div>
      </section>

      {/* ROUTE PREVIEW */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 md:px-12 pb-10 sm:pb-14">
        <div className="bg-[#111820] border border-white/10 rounded-xl p-5 sm:p-7">
          <h2 className="text-xl font-bold mb-5">
            <span className="text-orange-500">YOUR JOURNEY</span> STARTS HERE
          </h2>

          <RouteLine
            ride={adaptRide(FALLBACK_RIDE)}
            riders={FALLBACK_RIDERS.map((r, i) =>
              adaptRider(r, i, FALLBACK_RIDERS.length, "demo_u1")
            )}
            compact
          />
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-white/10 py-6 text-center text-xs text-gray-500">
        CONVOYCONNECT Â· RIDE TOGETHER. EXPLORE FURTHER.
      </footer>

    </div>
  );
}

/* ================================ CREATE RIDE ============================== */
function CreateRide({ onBack, onCreated }) {
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [dest, setDest] = useState("");
  const [startResults, setStartResults] = useState([]);
  const [destResults, setDestResults] = useState([]);
  const [startPoint, setStartPoint] = useState(null);
  const [destPoint, setDestPoint] = useState(null);
  const [searchingStart, setSearchingStart] = useState(false);
  const [searchingDest, setSearchingDest] = useState(false);
  const [leaderName, setLeaderName] = useState("");
  const [leaderPhone, setLeaderPhone] = useState("");
  const [created, setCreated] = useState(false);
  const [copied, setCopied] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [rideResult, setRideResult] = useState(null); // { id, invite_code, created_by_rider_id }
  const searchLocation = async (query, type) => {
  if (!query.trim()) return;

  const setSearching = type === "start" ? setSearchingStart : setSearchingDest;
  const setResults = type === "start" ? setStartResults : setDestResults;
  const setPoint = type === "start" ? setStartPoint : setDestPoint;

  setSearching(true);
  setResults([]);
  setPoint(null);
  setError(null);

  try {
    const data = await api.searchLocations(query);
    setResults(data.results || []);

    if (!data.results?.length) {
      setError(`No matching location found for "${query}".`);
    }
  } catch (err) {
    setError(err.message || "Location search failed.");
  } finally {
    setSearching(false);
  }
};

  const submit = async (e) => {
  e.preventDefault();

  if (
    !name.trim() ||
    !start.trim() ||
    !dest.trim() ||
    !leaderName.trim() ||
    !leaderPhone.trim() ||
    submitting
  ) return;

  if (!startPoint || !destPoint) {
    setError("Please search and select both locations before creating the ride.");
    return;
  }

  setSubmitting(true);
  setError(null);

  try {
    const ride = await api.createRide({
      ride_name: name.trim(),
      start_location_name: start.trim(),
      destination_location_name: dest.trim(),
      start_point: {
        latitude: startPoint.latitude,
        longitude: startPoint.longitude,
      },
      destination_point: {
        latitude: destPoint.latitude,
        longitude: destPoint.longitude,
      },
      leader_name: leaderName.trim(),
      leader_phone: leaderPhone.trim(),
    });

    setRideResult(ride);
    setCreated(true);
  } catch (err) {
    setError(err.message || "Could not create the ride. Is the backend running?");
  } finally {
    setSubmitting(false);
  }
};
  return (
    <div className="min-h-screen flex items-center justify-center p-5">
      <div className="w-full max-w-md cc-panel rounded-2xl p-6 sm:p-7 cc-fade-in">
        <button onClick={onBack} className="cc-muted hover:text-white flex items-center gap-1 text-xs mb-5"><ArrowLeft size={14} /> Back</button>

        {!created ? (
          <>
            <div className="flex items-center gap-2 mb-1"><Plus size={18} className="cc-amber" /><span className="cc-display font-semibold text-xl">Create a ride</span></div>
            <p className="cc-muted text-xs mb-5">Set your route, then invite riders with a link or code.</p>

            <form onSubmit={submit} className="flex flex-col gap-4">
              <Field label="Your name">
                <input value={leaderName} onChange={(e) => setLeaderName(e.target.value)} placeholder="e.g. Alex Rider" className="cc-input" />
              </Field>
              <Field label="Phone number">
  <input
    type="tel"
    value={leaderPhone}
    onChange={(e) => setLeaderPhone(e.target.value)}
    placeholder="Enter your phone number"
    className="cc-input"
  />
</Field>
              <Field label="Ride name">
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. PNW Coastal Run" className="cc-input" />
              </Field>
              <Field label="Start location">
  <div className="flex gap-2">
    <div className="relative flex-1">
      <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 cc-muted" />
      <input
        value={start}
        onChange={(e) => {
          setStart(e.target.value);
          setStartPoint(null);
          setStartResults([]);
        }}
        placeholder="Enter starting location"
        className="cc-input pl-8"
      />
    </div>
    <button
      type="button"
      onClick={() => searchLocation(start, "start")}
      disabled={searchingStart}
      className="cc-btn-ghost rounded-lg px-3 text-xs"
    >
      {searchingStart ? "Searching..." : "Search"}
    </button>
    <button
      type="button"
      onClick={() => {
        if (!navigator.geolocation) {
          setError("Geolocation is not supported by this browser.");
          return;
        }

        setSearchingStart(true);
        setError(null);

        navigator.geolocation.getCurrentPosition(
          (position) => {
            setStart("Current location");
            setStartPoint({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
            });
            setStartResults([]);
            setSearchingStart(false);
          },
          (err) => {
            setError("Could not access your location: " + err.message);
            setSearchingStart(false);
          },
          { enableHighAccuracy: true, timeout: 15000 }
        );
      }}
      disabled={searchingStart}
      className="cc-btn-ghost rounded-lg px-3 text-xs"
    >
      My Location
    </button>
  </div>

  {startPoint && (
    <p className="text-xs mt-2 cc-safety">{"\u2713 Start location selected"}</p>
  )}

  {startResults.map((item, index) => (
    <button
      type="button"
      key={index}
      onClick={() => {
        setStartPoint({
          latitude: item.latitude,
          longitude: item.longitude,
        });
        setStartResults([]);
      }}
      className="block w-full text-left text-xs p-2 mt-1 cc-panel-2 rounded-lg"
    >
      {item.display_name}
    </button>
  ))}
</Field>
<Field label="Destination">
  <div className="flex gap-2">
    <div className="relative flex-1">
      <Flag size={14} className="absolute left-3 top-1/2 -translate-y-1/2 cc-muted" />
      <input
        value={dest}
        onChange={(e) => {
          setDest(e.target.value);
          setDestPoint(null);
          setDestResults([]);
        }}
        placeholder="Enter destination"
        className="cc-input pl-8"
      />
    </div>
    <button
      type="button"
      onClick={() => searchLocation(dest, "dest")}
      disabled={searchingDest}
      className="cc-btn-ghost rounded-lg px-3 text-xs"
    >
      {searchingDest ? "Searching..." : "Search"}
    </button>
  </div>

  {destPoint && (
    <p className="text-xs mt-2 cc-safety">Destination selected</p>
  )}

  {destResults.map((item, index) => (
    <button
      type="button"
      key={index}
      onClick={() => {
        setDestPoint({
          latitude: item.latitude,
          longitude: item.longitude,
        });
        setDestResults([]);
      }}
      className="block w-full text-left text-xs p-2 mt-1 cc-panel-2 rounded-lg"
    >
      {item.display_name}
    </button>
  ))}
</Field>
              {error && (
                <div className="cc-status-separated rounded-xl p-3 text-xs flex items-start gap-2 cc-fade-in">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {error}
                </div>
              )}

              <button type="submit" disabled={submitting} className="cc-btn-primary rounded-xl py-3 text-sm mt-2 flex items-center justify-center gap-2 disabled:opacity-60">
                {submitting ? <Loader2 size={15} className="animate-spin" /> : null}
                {submitting ? "Creating\u2026" : "Create ride"}
              </button>
            </form>
          </>
        ) : (
          <div className="cc-fade-in">
            <div className="flex items-center gap-2 mb-1"><Check size={18} className="cc-safety" /><span className="cc-display font-semibold text-xl">Ride created</span></div>
            <p className="cc-muted text-xs mb-5">Share this code or link with your riders.</p>

            <div className="cc-panel-2 rounded-xl p-4 flex items-center justify-between mb-3">
              <span className="cc-mono text-lg tracking-wider cc-amber">{rideResult.invite_code}</span>
              <button onClick={() => { navigator.clipboard?.writeText(rideResult.invite_code); setCopied(true); setTimeout(() => setCopied(false), 1500); }} className="cc-btn-ghost rounded-lg px-3 py-1.5 text-xs flex items-center gap-1.5">
                {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="cc-panel-2 rounded-xl p-3 mb-6">
              <div className="flex items-center gap-2">
                <Link2 size={15} className="cc-amber shrink-0" />
                <a
                  href={`${window.location.origin}/join/${encodeURIComponent(rideResult.invite_code)}`}
                  className="text-xs cc-mono cc-muted break-all flex-1 min-w-0 hover:underline"
                >
                  {`${window.location.host}/join/${rideResult.invite_code}`}
                </a>
                <button
                  type="button"
                  title="Copy joining link"
                  aria-label="Copy joining link"
                  onClick={async () => {
                    const url = `${window.location.origin}/join/${encodeURIComponent(rideResult.invite_code)}`;
                    try {
                      await navigator.clipboard.writeText(url);
                      setLinkCopied(true);
                      setTimeout(() => setLinkCopied(false), 1500);
                    } catch {
                      setError("Could not copy the joining link.");
                    }
                  }}
                  className="cc-btn-ghost rounded-lg p-2 shrink-0"
                >
                  {linkCopied ? <Check size={15} /> : <Copy size={15} />}
                </button>
                <button
                  type="button"
                  title="Share joining link"
                  aria-label="Share joining link"
                  onClick={async () => {
                    const url = `${window.location.origin}/join/${encodeURIComponent(rideResult.invite_code)}`;
                    try {
                      if (navigator.share) {
                        await navigator.share({
                          title: "Join my ConvoyConnect ride",
                          text: `Join my convoy using this link:`,
                          url
                        });
                      } else {
                        await navigator.clipboard.writeText(url);
                        setLinkCopied(true);
                        setTimeout(() => setLinkCopied(false), 1500);
                      }
                    } catch (err) {
                      if (err.name !== "AbortError") {
                        setError("Could not share the joining link.");
                      }
                    }
                  }}
                  className="cc-btn-ghost rounded-lg p-2 shrink-0"
                >
                  <Share2 size={15} />
                </button>
              </div>
            </div>

            <button
              onClick={() => onCreated(rideResult.id, rideResult.created_by_rider_id)}
              className="cc-btn-primary rounded-xl py-3 text-sm w-full flex items-center justify-center gap-2"
            >
              Enter ride dashboard <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ================================ JOIN RIDE ============================== */

function JoinRide({ onBack, onJoined }) {
  const [code, setCode] = useState(() => decodeURIComponent(window.location.pathname.split("/").filter(Boolean)[1] || "").toUpperCase());
  const [riderName, setRiderName] = useState("");
  const [riderPhone, setRiderPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!code.trim() || !riderName.trim() || !riderPhone.trim() || submitting) return;

    setSubmitting(true);
    setError(null);

    try {
      const result = await api.joinRide({
        invite_code: code.trim(),
        rider_name: riderName.trim(),
        rider_phone: riderPhone.trim(),
      });
      onJoined(result.ride.id, result.rider.id);
    } catch (err) {
      setError(err.message || "Could not join that ride. Check the invite code and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-5">
      <div className="w-full max-w-md cc-panel rounded-2xl p-6 sm:p-7 cc-fade-in">
        <button onClick={onBack} className="cc-muted hover:text-white flex items-center gap-1 text-xs mb-5"><ArrowLeft size={14} /> Back</button>
        <div className="flex items-center gap-2 mb-1"><Link2 size={18} className="cc-teal" /><span className="cc-display font-semibold text-xl">Join a ride</span></div>
        <p className="cc-muted text-xs mb-5">Enter the invite code your ride leader shared with you.</p>

        <form onSubmit={submit} className="flex flex-col gap-4">
          <Field label="Your name">
            <input value={riderName} onChange={(e) => setRiderName(e.target.value)} placeholder="e.g. Priya Nair" className="cc-input" />
          </Field>

          <Field label="Phone number">
            <input
              type="tel"
              value={riderPhone}
              onChange={(e) => setRiderPhone(e.target.value)}
              placeholder="Enter your phone number"
              className="cc-input"
            />
          </Field>

          <Field label="Invite code">
            <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CONVOY-XXXX" className="cc-input cc-mono tracking-wider" />
          </Field>

          {error && (
            <div className="cc-status-separated rounded-xl p-3 text-xs flex items-start gap-2 cc-fade-in">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}

          <button
            type="submit"
            disabled={!code.trim() || !riderName.trim() || !riderPhone.trim() || submitting}
            className="cc-btn-primary rounded-xl py-3 text-sm w-full disabled:opacity-40 flex items-center justify-center gap-2"
          >
            {submitting ? <Loader2 size={15} className="animate-spin" /> : null}
            {submitting ? "Joining\u2026" : "Join ride"} {!submitting && <ChevronRight size={16} />}
          </button>
        </form>

        <div className="mt-6 cc-panel-2 rounded-xl p-3 flex items-center gap-2 text-xs cc-muted">
          <Users size={14} className="cc-teal shrink-0" /> Ask your ride leader for the invite code shown after they create the ride.
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] cc-muted cc-mono uppercase tracking-wide">{label}</span>
      {children}
    </label>
  );
}

/* ================================== APP =================================== */
export default function App() {
  const [view, setView] = useState(() => window.location.pathname.match(/^\/join\/([^/]+)\/?$/i) ? "join" : "landing"); // landing | create | join | dashboard
  const [rideId, setRideId] = useState(() => localStorage.getItem("cc_rideId") || null);
  const [selfRiderId, setSelfRiderId] = useState(() => localStorage.getItem("cc_riderId") || null);

  const enterDashboard = (newRideId, newRiderId) => {
    localStorage.setItem("cc_rideId", newRideId);
    localStorage.setItem("cc_riderId", newRiderId);
    setRideId(newRideId);
    setSelfRiderId(newRiderId);
    setView("dashboard");
  };

  const hasSavedRide = Boolean(rideId && selfRiderId);

  return (
    <div className="cc-root min-h-screen w-full">
      <GlobalStyle />
      <style>{`
        .cc-input{
          width:100%; background:var(--cc-panel-2); border:1px solid var(--cc-line);
          border-radius:0.75rem; padding:0.7rem 0.9rem; font-size:0.875rem; color:var(--cc-text); outline:none;
        }
        .cc-input:focus{border-color:var(--cc-teal);}
        .cc-input.pl-8{padding-left:2rem;}
      `}</style>

      {view === "landing" && (
        <Landing
          onCreate={() => setView("create")}
          onJoin={() => setView("join")}
          onResume={hasSavedRide ? () => setView("dashboard") : null}
        />
      )}
      {view === "create" && <CreateRide onBack={() => setView("landing")} onCreated={enterDashboard} />}
      {view === "join" && <JoinRide onBack={() => setView("landing")} onJoined={enterDashboard} />}
      {view === "dashboard" && rideId && selfRiderId && (
        <Dashboard rideId={rideId} selfRiderId={selfRiderId} onBackHome={() => setView("landing")} />
      )}
    </div>
  );
}






























