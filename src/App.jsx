import React, { useState, useMemo, useRef, useEffect } from "react";
import {
  MapPin, Navigation, Phone, MessageSquare, Users, AlertTriangle,
  Radio, Send, X, ChevronRight, ChevronLeft, Flag, Gauge, Clock,
  Fuel, Battery, Signal, Plus, Link2, Copy, Check, ArrowLeft,
  Compass, LocateFixed, Siren, ShieldAlert, PhoneCall, LifeBuoy,
  Bike, Route as RouteIcon, Sparkles, Menu, Home
} from "lucide-react";

/* ======================================================================
   CONVOYCONNECT — NLP-Based Intelligent Group Ride Assistant
   PHASE 1 PROTOTYPE — FRONTEND ONLY, MOCK DATA
   ----------------------------------------------------------------------
   Component map (for future FastAPI / GPS / NLP integration):
     <App>
       <Landing />
       <CreateRide />
       <JoinRide />
       <Dashboard>
          <TopBar /> <RouteLine />
          <MapPanel />        -> GPS_TRACKING_SERVICE (future)
          <RiderList />       -> RIDER_STATE_SERVICE (future)
          <GroupChat />       -> CHAT_SERVICE / websockets (future)
          <AIAssistantPanel />-> NLP_SERVICE (future, currently disabled)
          <SOSPanel />        -> EMERGENCY_SERVICE (future)
          <RiderDetailsDrawer />
       </Dashboard>
   All data below is mocked. Replace MOCK_* constants and the
   simulate* functions with real API calls / websocket subscriptions.
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

/* ------------------------------ MOCK DATA ----------------------------- */
const STATUS_META = {
  onTrack: { label: "On track", cls: "cc-status-onTrack" },
  delayed: { label: "Delayed", cls: "cc-status-delayed" },
  separated: { label: "Separated", cls: "cc-status-separated" },
  stopped: { label: "Stopped", cls: "cc-status-stopped" },
  sos: { label: "SOS", cls: "cc-status-sos" },
};

const MOCK_RIDE = {
  id: "ride_8842",
  name: "PNW Coastal Run",
  inviteCode: "CONVOY-7F2K",
  start: { name: "Seattle, WA" },
  destination: { name: "Astoria, OR" },
  totalDistanceMi: 178,
  coveredDistanceMi: 96,
  createdBy: "You",
};

const MOCK_RIDERS = [
  {
    id: "u1", name: "You", initials: "YOU", isSelf: true, role: "leader",
    status: "onTrack", speedMph: 58, progressPct: 54, distFromGroupMi: 0,
    battery: 82, lastUpdate: "just now", bike: "Triumph Tiger 900",
    phone: "+1 (206) 555-0142", eta: "2:41 PM", pos: { x: 0.54, y: 0 },
  },
  {
    id: "u2", name: "Marcus Bell", initials: "MB", role: "member",
    status: "onTrack", speedMph: 56, progressPct: 55, distFromGroupMi: 0.3,
    battery: 91, lastUpdate: "12s ago", bike: "Harley-Davidson Pan America",
    phone: "+1 (206) 555-0198", eta: "2:39 PM", pos: { x: 0.55, y: -0.035 },
  },
  {
    id: "u3", name: "Priya Nair", initials: "PN", role: "member",
    status: "delayed", speedMph: 41, progressPct: 47, distFromGroupMi: 3.1,
    battery: 64, lastUpdate: "48s ago", bike: "Kawasaki Versys 650",
    phone: "+1 (206) 555-0110", eta: "3:02 PM", pos: { x: 0.47, y: 0.045 },
  },
  {
    id: "u4", name: "Diego Alvarez", initials: "DA", role: "member",
    status: "separated", speedMph: 0, progressPct: 33, distFromGroupMi: 9.8,
    battery: 45, lastUpdate: "4 min ago", bike: "Honda Africa Twin",
    phone: "+1 (206) 555-0187", eta: "—", pos: { x: 0.33, y: 0.08 },
  },
  {
    id: "u5", name: "Sofia Kim", initials: "SK", role: "member",
    status: "stopped", speedMph: 0, progressPct: 52, distFromGroupMi: 1.2,
    battery: 77, lastUpdate: "2 min ago", bike: "Yamaha Ténéré 700",
    phone: "+1 (206) 555-0173", eta: "3:10 PM", pos: { x: 0.52, y: 0.06 },
  },
];

const MOCK_MESSAGES = [
  { id: "m1", riderId: "u2", text: "Fuel stop in 10 miles, gas is getting low on mine.", time: "1:58 PM" },
  { id: "m2", riderId: "u1", text: "Copy that, pulling into the Chevron up ahead.", time: "1:59 PM" },
  { id: "m3", riderId: "system", text: "Priya Nair has fallen 3.1 mi behind the group.", time: "2:03 PM", system: true },
  { id: "m4", riderId: "u3", text: "Sorry, hit a slow tractor on the 2-lane. Catching up.", time: "2:04 PM" },
  { id: "m5", riderId: "system", text: "Diego Alvarez signal lost — last seen 9.8 mi back.", time: "2:07 PM", system: true },
  { id: "m6", riderId: "u5", text: "Pausing for a photo at the overlook, 5 min behind.", time: "2:09 PM" },
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
   Signature element: a persistent "road" motif — dashed asphalt line from
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
          {ride.coveredDistanceMi} / {ride.totalDistanceMi} mi
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
          <div
            className="absolute top-1/2 left-0 h-[3px] -translate-y-1/2 rounded-full"
            style={{ background: "linear-gradient(90deg, var(--cc-teal), var(--cc-amber))", width: `${ride.coveredDistanceMi / ride.totalDistanceMi * 100}%` }}
          />
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
                {r.isSelf ? "•" : r.initials[0]}
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
   Stylized/abstract map (no external tiles — this is a UI prototype).
   Replace with Mapbox/Leaflet + live GPS feed in production.
========================================================================= */
function MapPanel({ riders, selfId, onSelectRider, selectedRiderId }) {
  const self = riders.find((r) => r.id === selfId);
  return (
    <div className="cc-panel rounded-2xl overflow-hidden relative">
      <div className="cc-map-grid relative h-[360px] sm:h-[440px] w-full overflow-hidden">
        {/* faux route path */}
        <svg viewBox="0 0 400 300" className="absolute inset-0 w-full h-full" preserveAspectRatio="none">
          <path d="M 20 250 C 100 240, 140 120, 210 130 S 340 90, 380 40" fill="none" stroke="#2B3440" strokeWidth="4" />
          <path d="M 20 250 C 100 240, 140 120, 210 130 S 340 90, 380 40" fill="none" stroke="#3FD1C6" strokeWidth="2.5" strokeDasharray="1 10" strokeLinecap="round" opacity="0.8" />
        </svg>

        {riders.map((r) => {
          const left = 5 + r.pos.x * 90;
          const top = 78 - r.pos.x * 60 + r.pos.y * 220;
          const isSel = selectedRiderId === r.id;
          return (
            <button
              key={r.id}
              onClick={() => onSelectRider(r)}
              className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center"
              style={{ left: `${left}%`, top: `${Math.min(88, Math.max(6, top))}%` }}
            >
              <div
                className={`rounded-full flex items-center justify-center cc-display font-bold ${r.isSelf ? "cc-dot-pulse" : ""}`}
                style={{
                  width: isSel ? 38 : 30, height: isSel ? 38 : 30,
                  background: initialsColor(r.id), color: "#0b0e12",
                  fontSize: 11, border: isSel ? "3px solid #fff" : "2px solid #12161B",
                  boxShadow: "0 2px 8px rgba(0,0,0,.5)", transition: "all .15s ease",
                }}
              >
                {r.initials}
              </div>
              <span className="mt-1 text-[10px] cc-mono px-1.5 py-0.5 rounded cc-panel-2 whitespace-nowrap">{r.name.split(" ")[0]}</span>
            </button>
          );
        })}

        {/* compass */}
        <div className="absolute top-3 right-3 cc-panel-2 rounded-full p-2">
          <Compass size={16} className="cc-teal" />
        </div>
      </div>

      {/* map controls */}
      <div className="flex items-center justify-between p-3 border-t cc-border cc-panel-2">
        <div className="flex items-center gap-2 text-xs cc-muted cc-mono">
          <LocateFixed size={14} className="cc-teal" /> Live tracking — mock GPS feed
        </div>
        <div className="flex gap-2">
          <button className="cc-btn-ghost rounded-lg px-3 py-1.5 text-xs flex items-center gap-1.5">
            <Navigation size={13} /> Recenter
          </button>
        </div>
      </div>
    </div>
  );
}

/* ============================== RIDER LIST ============================== */
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
              <div className="text-xs cc-muted cc-mono truncate">{r.speedMph} mph · {r.distFromGroupMi} mi from group</div>
            </div>
            <StatusPill status={r.status} small />
          </button>
        ))}
      </div>
    </div>
  );
}

/* ============================== GROUP CHAT =============================== */
function GroupChat({ riders, messages, setMessages }) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef(null);
  const riderMap = useMemo(() => Object.fromEntries(riders.map((r) => [r.id, r])), [riders]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = () => {
    if (!draft.trim()) return;
    setMessages((m) => [...m, { id: `m${Date.now()}`, riderId: "u1", text: draft.trim(), time: "now" }]);
    setDraft("");
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
                <span className="text-[10px] cc-muted cc-mono mb-0.5">{rider?.name} · {m.time}</span>
                <div className={`rounded-2xl px-3 py-2 text-sm ${isSelf ? "cc-bg-amber text-[#191204]" : "cc-panel-2"}`}>{m.text}</div>
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
          placeholder="Message the group…"
          className="flex-1 bg-transparent cc-panel-2 rounded-full px-4 py-2 text-sm outline-none placeholder:cc-muted"
        />
        <button onClick={send} className="cc-btn-primary rounded-full w-9 h-9 flex items-center justify-center shrink-0">
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}

/* ========================= AI ASSISTANT PANEL (prototype) ================ */
function AIAssistantPanel({ compact }) {
  const [query, setQuery] = useState("");
  const [asked, setAsked] = useState([]);

  const ask = () => {
    if (!query.trim()) return;
    setAsked((a) => [...a, query.trim()]);
    setQuery("");
  };

  return (
    <div className="cc-panel rounded-2xl p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={16} className="cc-teal" />
        <span className="text-sm font-semibold cc-display">Ask ConvoyConnect</span>
        <span className="ml-auto text-[9px] cc-mono uppercase tracking-wide px-2 py-0.5 rounded-full cc-status-delayed">AI · Prototype</span>
      </div>
      <p className="text-xs cc-muted mb-3 leading-relaxed">
        NLP query understanding is not yet connected. In production this will parse natural-language
        questions ("who's furthest behind?", "reroute around traffic") via the FastAPI NLP service.
      </p>

      <div className="flex items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="e.g. Who is furthest behind the group?"
          className="flex-1 bg-transparent cc-panel-2 rounded-full px-4 py-2 text-sm outline-none placeholder:cc-muted"
        />
        <button onClick={ask} className="cc-btn-ghost rounded-full px-4 py-2 text-xs shrink-0">Ask</button>
      </div>

      {asked.length > 0 && (
        <div className="mt-3 flex flex-col gap-2">
          {asked.slice(-2).map((q, i) => (
            <div key={i} className="cc-panel-2 rounded-xl p-3 text-xs cc-fade-in">
              <div className="cc-mono cc-muted mb-1">You asked</div>
              <div className="mb-2">{q}</div>
              <div className="cc-muted italic">AI response unavailable — NLP engine not yet integrated in this prototype.</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ================================ SOS PANEL ============================== */
function SOSPanel({ open, onClose, riders }) {
  const [sent, setSent] = useState(null);
  if (!open) return null;
  const nearest = riders.filter((r) => !r.isSelf).sort((a, b) => a.distFromGroupMi - b.distFromGroupMi)[0];

  const trigger = (label) => setSent(label);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4">
      <div className="cc-panel w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl p-5 cc-fade-in">
        <div className="flex items-center gap-2 mb-1">
          <Siren size={18} className="cc-red" />
          <span className="cc-display font-semibold text-lg">Emergency / SOS</span>
          <button onClick={onClose} className="ml-auto cc-muted hover:text-white"><X size={18} /></button>
        </div>
        <p className="text-xs cc-muted mb-4">Coordinate help fast. Your location is shared with the group automatically when SOS is active.</p>

        {sent ? (
          <div className="cc-status-onTrack rounded-xl p-4 text-sm flex items-center gap-2 mb-4">
            <Check size={16} /> {sent} — group has been notified (mock).
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-2.5">
          <button onClick={() => trigger("Location shared")} className="cc-btn-sos rounded-xl p-3.5 flex items-center gap-3 text-left">
            <ShieldAlert size={20} />
            <span className="flex-1 text-sm">
              <span className="block font-bold">Alert entire group</span>
              <span className="block text-[11px] opacity-80">Broadcast SOS + live location to all riders</span>
            </span>
          </button>

          <button onClick={() => trigger(`Called ${nearest?.name}`)} className="cc-btn-ghost rounded-xl p-3.5 flex items-center gap-3 text-left">
            <PhoneCall size={18} className="cc-teal" />
            <span className="flex-1 text-sm">
              <span className="block font-medium">Call nearest rider</span>
              <span className="block text-[11px] cc-muted">{nearest?.name} · {nearest?.distFromGroupMi} mi away</span>
            </span>
          </button>

          <button onClick={() => trigger("Emergency services contacted")} className="cc-btn-ghost rounded-xl p-3.5 flex items-center gap-3 text-left">
            <LifeBuoy size={18} className="cc-red" />
            <span className="flex-1 text-sm">
              <span className="block font-medium">Contact emergency services</span>
              <span className="block text-[11px] cc-muted">Mock action — dials local emergency number</span>
            </span>
          </button>

          <button onClick={() => trigger("Location pin sent")} className="cc-btn-ghost rounded-xl p-3.5 flex items-center gap-3 text-left">
            <MapPin size={18} className="cc-amber" />
            <span className="flex-1 text-sm">
              <span className="block font-medium">Share exact GPS pin</span>
              <span className="block text-[11px] cc-muted">Sends coordinates to chat</span>
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

/* ============================ RIDER DETAILS DRAWER ========================= */
function RiderDetailsDrawer({ rider, onClose }) {
  if (!rider) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <div className="cc-panel w-full sm:w-[360px] h-full p-5 overflow-y-auto cc-scroll cc-fade-in" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="cc-muted hover:text-white mb-4 flex items-center gap-1 text-xs"><ArrowLeft size={14} /> Back</button>

        <div className="flex items-center gap-3 mb-4">
          <Avatar rider={rider} size={56} ring />
          <div>
            <div className="cc-display font-semibold text-lg">{rider.name}{rider.isSelf ? " (you)" : ""}</div>
            <div className="text-xs cc-muted">{rider.bike}</div>
          </div>
        </div>

        <StatusPill status={rider.status} />

        <div className="grid grid-cols-2 gap-2.5 mt-4">
          <Stat icon={<Gauge size={14} className="cc-teal" />} label="Speed" value={`${rider.speedMph} mph`} />
          <Stat icon={<RouteIcon size={14} className="cc-teal" />} label="From group" value={`${rider.distFromGroupMi} mi`} />
          <Stat icon={<Clock size={14} className="cc-teal" />} label="ETA" value={rider.eta} />
          <Stat icon={<Battery size={14} className="cc-teal" />} label="Battery" value={`${rider.battery}%`} />
          <Stat icon={<Signal size={14} className="cc-teal" />} label="Last update" value={rider.lastUpdate} />
          <Stat icon={<Flag size={14} className="cc-teal" />} label="Progress" value={`${rider.progressPct}%`} />
        </div>

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
            <span>Detected as {rider.status === "sos" ? "in emergency" : "separated from group"} based on GPS drift. Automated detection is a placeholder — future NLP/GPS service will refine thresholds.</span>
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
          <div className="text-xs cc-muted cc-mono truncate">{ride.start.name} → {ride.destination.name}</div>
        </div>
      </div>

      <div className="flex items-center gap-4 sm:gap-6 cc-mono text-xs">
        <div className="text-center">
          <div className="cc-muted uppercase text-[9px]">Group Dist.</div>
          <div className="text-sm font-medium">{ride.coveredDistanceMi}/{ride.totalDistanceMi} mi</div>
        </div>
        <div className="text-center">
          <div className="cc-muted uppercase text-[9px]">ETA</div>
          <div className="text-sm font-medium cc-teal">2:41 PM</div>
        </div>
        <button onClick={onOpenSOS} className="cc-btn-sos rounded-xl px-4 py-2 flex items-center gap-2 text-xs shrink-0">
          <Siren size={14} /> SOS
        </button>
      </div>
    </div>
  );
}

/* ================================ DASHBOARD ================================ */
function Dashboard({ ride, riders, messages, setMessages, onBackHome }) {
  const [selectedRider, setSelectedRider] = useState(null);
  const [sosOpen, setSosOpen] = useState(false);
  const [tab, setTab] = useState("map"); // map | riders | chat  (mobile)

  return (
    <div className="max-w-[1400px] mx-auto p-3 sm:p-5 flex flex-col gap-4">
      <TopBar ride={ride} riders={riders} onOpenSOS={() => setSosOpen(true)} onBackHome={onBackHome} />
      <RouteLine ride={ride} riders={riders} onSelectRider={setSelectedRider} />

      {/* mobile tab switcher */}
      <div className="flex sm:hidden cc-panel rounded-xl p-1 gap-1">
        {["map", "riders", "chat"].map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`flex-1 rounded-lg py-2 text-xs capitalize ${tab === t ? "cc-btn-primary" : "cc-muted"}`}>{t}</button>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_320px] gap-4">
        <div className={`flex-col gap-4 ${tab === "map" ? "flex" : "hidden"} sm:flex`}>
          <MapPanel riders={riders} selfId="u1" onSelectRider={setSelectedRider} selectedRiderId={selectedRider?.id} />
          <AIAssistantPanel />
        </div>

        <div className="grid grid-cols-1 gap-4">
          <div className={`${tab === "riders" ? "block" : "hidden"} sm:block h-[280px] sm:h-[300px]`}>
            <RiderList riders={riders} onSelectRider={setSelectedRider} selectedRiderId={selectedRider?.id} />
          </div>
          <div className={`${tab === "chat" ? "block" : "hidden"} sm:block h-[340px] sm:h-[360px]`}>
            <GroupChat riders={riders} messages={messages} setMessages={setMessages} />
          </div>
        </div>
      </div>

      <RiderDetailsDrawer rider={selectedRider} onClose={() => setSelectedRider(null)} />
      <SOSPanel open={sosOpen} onClose={() => setSosOpen(false)} riders={riders} />
    </div>
  );
}

/* ================================ LANDING ================================ */
function Landing({ onCreate, onJoin }) {
  return (
    <div className="min-h-screen flex flex-col">
      <div className="max-w-5xl mx-auto w-full px-5 pt-16 pb-10 flex-1 flex flex-col justify-center">
        <div className="flex items-center gap-2 mb-6 cc-mono text-xs cc-muted uppercase tracking-widest">
          <Bike size={16} className="cc-amber" /> ConvoyConnect · Research Prototype
        </div>
        <h1 className="cc-display text-4xl sm:text-6xl font-semibold leading-[1.05] mb-5 max-w-2xl">
          Keep the whole pack together, <span className="cc-amber">even off the highway.</span>
        </h1>
        <p className="cc-muted max-w-xl text-sm sm:text-base leading-relaxed mb-8">
          ConvoyConnect is an NLP-based group ride assistant for real-time road trip coordination —
          live rider tracking, delay &amp; separation detection, group chat, and SOS coordination
          for motorcycle convoys. This build is the Phase 1 frontend prototype; AI/NLP features are
          mocked and clearly labeled.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 mb-14">
          <button onClick={onCreate} className="cc-btn-primary rounded-xl px-6 py-3.5 flex items-center justify-center gap-2 text-sm">
            <Plus size={16} /> Create a group ride
          </button>
          <button onClick={onJoin} className="cc-btn-ghost rounded-xl px-6 py-3.5 flex items-center justify-center gap-2 text-sm">
            <Link2 size={16} /> Join with a code
          </button>
        </div>

        {/* signature route-line teaser using mock data */}
        <RouteLine ride={MOCK_RIDE} riders={MOCK_RIDERS} compact />

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-8">
          {[
            { icon: <MapPin size={16} className="cc-teal" />, label: "Live map" },
            { icon: <AlertTriangle size={16} className="cc-amber" />, label: "Delay detection" },
            { icon: <MessageSquare size={16} className="cc-teal" />, label: "Group chat" },
            { icon: <Siren size={16} className="cc-red" />, label: "SOS coordination" },
          ].map((f, i) => (
            <div key={i} className="cc-panel rounded-xl p-3 flex items-center gap-2 text-xs">{f.icon}{f.label}</div>
          ))}
        </div>
      </div>

      <div className="text-center text-[11px] cc-muted pb-6 cc-mono">
        Phase 1 — Frontend UI prototype · NLP &amp; AI features not yet implemented
      </div>
    </div>
  );
}

/* ================================ CREATE RIDE ============================== */
function CreateRide({ onBack, onCreated }) {
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [dest, setDest] = useState("");
  const [created, setCreated] = useState(false);
  const [copied, setCopied] = useState(false);
  const code = "CONVOY-7F2K";

  const submit = (e) => {
    e.preventDefault();
    if (!name || !start || !dest) return;
    setCreated(true);
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
              <Field label="Ride name">
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. PNW Coastal Run" className="cc-input" />
              </Field>
              <Field label="Start location">
                <div className="relative"><MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 cc-muted" />
                  <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="Seattle, WA" className="cc-input pl-8" />
                </div>
              </Field>
              <Field label="Destination">
                <div className="relative"><Flag size={14} className="absolute left-3 top-1/2 -translate-y-1/2 cc-muted" />
                  <input value={dest} onChange={(e) => setDest(e.target.value)} placeholder="Astoria, OR" className="cc-input pl-8" />
                </div>
              </Field>
              <button type="submit" className="cc-btn-primary rounded-xl py-3 text-sm mt-2">Create ride</button>
            </form>
          </>
        ) : (
          <div className="cc-fade-in">
            <div className="flex items-center gap-2 mb-1"><Check size={18} className="cc-safety" /><span className="cc-display font-semibold text-xl">Ride created</span></div>
            <p className="cc-muted text-xs mb-5">Share this code or link with your riders.</p>

            <div className="cc-panel-2 rounded-xl p-4 flex items-center justify-between mb-3">
              <span className="cc-mono text-lg tracking-wider cc-amber">{code}</span>
              <button onClick={() => { navigator.clipboard?.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500); }} className="cc-btn-ghost rounded-lg px-3 py-1.5 text-xs flex items-center gap-1.5">
                {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="cc-panel-2 rounded-xl p-3 text-xs cc-mono cc-muted mb-6 break-all">convoyconnect.app/join/{code}</div>

            <button onClick={onCreated} className="cc-btn-primary rounded-xl py-3 text-sm w-full flex items-center justify-center gap-2">
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
  const [code, setCode] = useState("");
  return (
    <div className="min-h-screen flex items-center justify-center p-5">
      <div className="w-full max-w-md cc-panel rounded-2xl p-6 sm:p-7 cc-fade-in">
        <button onClick={onBack} className="cc-muted hover:text-white flex items-center gap-1 text-xs mb-5"><ArrowLeft size={14} /> Back</button>
        <div className="flex items-center gap-2 mb-1"><Link2 size={18} className="cc-teal" /><span className="cc-display font-semibold text-xl">Join a ride</span></div>
        <p className="cc-muted text-xs mb-5">Enter the invite code your ride leader shared with you.</p>

        <Field label="Invite code">
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CONVOY-XXXX" className="cc-input cc-mono tracking-wider" />
        </Field>

        <button
          disabled={!code.trim()}
          onClick={onJoined}
          className="cc-btn-primary rounded-xl py-3 text-sm w-full mt-4 disabled:opacity-40 flex items-center justify-center gap-2"
        >
          Join ride <ChevronRight size={16} />
        </button>

        <div className="mt-6 cc-panel-2 rounded-xl p-3 flex items-center gap-2 text-xs cc-muted">
          <Users size={14} className="cc-teal shrink-0" /> Preview: “PNW Coastal Run” · 5 riders already on route
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
  const [view, setView] = useState("landing"); // landing | create | join | dashboard
  const [messages, setMessages] = useState(MOCK_MESSAGES);
  const riders = MOCK_RIDERS;

  return (
    <div className="cc-root min-h-screen w-full">
      <GlobalStyle />
      <style>{`
        .cc-input{
          width:100%; background:var(--cc-panel-2); border:1px solid var(--cc-line);
          border-radius:0.75rem; padding:0.7rem 0.9rem; font-size:0.875rem; color:var(--cc-text); outline:none;
        }
        .cc-input:focus{border-color:var(--cc-teal);}
      `}</style>

      {view === "landing" && <Landing onCreate={() => setView("create")} onJoin={() => setView("join")} />}
      {view === "create" && <CreateRide onBack={() => setView("landing")} onCreated={() => setView("dashboard")} />}
      {view === "join" && <JoinRide onBack={() => setView("landing")} onJoined={() => setView("dashboard")} />}
      {view === "dashboard" && (
        <Dashboard
          ride={MOCK_RIDE}
          riders={riders}
          messages={messages}
          setMessages={setMessages}
          onBackHome={() => setView("landing")}
        />
      )}
    </div>
  );
}
