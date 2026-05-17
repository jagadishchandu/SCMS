import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { useAuth } from "../../contexts/AuthContext";
import {
  Bus, MapPin, Calendar as CalendarIcon, CurrencyInr, Users,
  Phone, Path, ArrowSquareOut, CheckCircle, XCircle, ListChecks,
} from "@phosphor-icons/react";
import { formatDate, currency } from "../../lib/utils";
import toast from "react-hot-toast";

const STATUS_BADGE = {
  open: "badge-success",
  closed: "badge-neutral",
  cancelled: "badge-danger",
};

export default function TripsViewPage() {
  const { user } = useAuth();
  const [trips, setTrips] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = () => api.get("/trips").then((r) => setTrips(r.data)).catch(() => setTrips([]));
  useEffect(() => { load(); }, []);

  if (trips === null) return <div className="skeleton h-40 w-full" />;

  const today = new Date().toISOString().slice(0, 10);
  const upcoming = trips
    .filter((t) => (t.departure_date || "") >= today && t.status !== "cancelled")
    .sort((a, b) => (a.departure_date || "").localeCompare(b.departure_date || ""));
  const past = trips
    .filter((t) => (t.departure_date || "") < today || t.status === "cancelled")
    .sort((a, b) => (b.departure_date || "").localeCompare(a.departure_date || ""));

  const isParent = user?.role === "parent";

  return (
    <div data-testid="trips-view-page">
      <PageHeader
        eyebrow="Educational Trips"
        title={isParent ? "Upcoming school trips" : "School trips"}
        subtitle={
          isParent
            ? "Tap a trip and confirm whether your child will be coming along."
            : "Educational trips scheduled by the school admin. View who has RSVP'd."
        }
      />

      <Section title={`Upcoming (${upcoming.length})`}>
        {upcoming.length === 0 ? (
          <Empty title="No upcoming trips" message="When the school announces a trip, it will appear here." />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {upcoming.map((t) => (
              <TripCard key={t.id} trip={t} onOpen={() => setSelected(t)} />
            ))}
          </div>
        )}
      </Section>

      {past.length > 0 && (
        <div className="mt-6">
          <Section title={`Past & cancelled (${past.length})`}>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {past.map((t) => (
                <TripCard key={t.id} trip={t} onOpen={() => setSelected(t)} dim />
              ))}
            </div>
          </Section>
        </div>
      )}

      {selected && (
        <TripDetailsModal
          trip={selected}
          role={user.role}
          onClose={() => setSelected(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

function TripCard({ trip, onOpen, dim }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`text-left border border-line rounded-lg p-5 flex flex-col gap-3 transition hover:shadow-sm hover:border-primary/40 ${
        dim ? "opacity-70" : ""
      }`}
      data-testid={`trip-card-${trip.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-primary-light grid place-items-center shrink-0">
            <Bus size={20} className="text-primary" />
          </div>
          <div className="min-w-0">
            <div className="font-display text-base font-medium truncate">
              {trip.title}
            </div>
            <div className="text-xs text-ink-muted flex items-center gap-1 mt-0.5">
              <MapPin size={12} /> {trip.destination}
            </div>
          </div>
        </div>
        <span className={STATUS_BADGE[trip.status] || "badge-neutral"}>
          {trip.status || "open"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex items-center gap-1.5 text-ink-soft">
          <CalendarIcon size={14} />
          <span>{formatDate(trip.departure_date)}</span>
        </div>
        <div className="flex items-center gap-1.5 text-ink-soft">
          <CurrencyInr size={14} />
          <span>{trip.cost ? currency(trip.cost) : "Free"}</span>
        </div>
        {trip.transport_mode ? (
          <div className="flex items-center gap-1.5 text-ink-soft">
            <Bus size={14} />
            <span>{trip.transport_mode}</span>
          </div>
        ) : null}
        {trip.max_students ? (
          <div className="flex items-center gap-1.5 text-ink-soft">
            <Users size={14} />
            <span>Max {trip.max_students}</span>
          </div>
        ) : null}
      </div>

      {trip.description ? (
        <div className="text-sm text-ink-soft line-clamp-2">{trip.description}</div>
      ) : null}
    </button>
  );
}

function TripDetailsModal({ trip, role, onClose, onChanged }) {
  const [tab, setTab] = useState(role === "parent" ? "details" : "details");

  return (
    <Modal open onClose={onClose} title={trip.title} size="lg" testId={`trip-details-${trip.id}`}>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-ink-soft">
            <MapPin size={16} />
            <span className="font-medium text-ink">{trip.destination}</span>
          </div>
          <span className={STATUS_BADGE[trip.status] || "badge-neutral"}>
            {trip.status || "open"}
          </span>
        </div>

        <div className="flex gap-1 border-b border-line -mx-5 px-5">
          <TabBtn active={tab === "details"} onClick={() => setTab("details")} testId={`tab-details-${trip.id}`}>
            Details
          </TabBtn>
          {role === "parent" ? (
            <TabBtn active={tab === "rsvp"} onClick={() => setTab("rsvp")} testId={`tab-rsvp-${trip.id}`}>
              <CheckCircle size={14} /> Confirm attendance
            </TabBtn>
          ) : (
            <TabBtn active={tab === "rsvp"} onClick={() => setTab("rsvp")} testId={`tab-rsvp-${trip.id}`}>
              <ListChecks size={14} /> RSVPs
            </TabBtn>
          )}
        </div>

        {tab === "details" ? (
          <DetailsTab trip={trip} />
        ) : role === "parent" ? (
          <ParentRSVPTab trip={trip} onChanged={onChanged} />
        ) : (
          <RosterTab trip={trip} />
        )}
      </div>
    </Modal>
  );
}

function TabBtn({ active, onClick, children, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`px-3 py-2 text-sm flex items-center gap-1.5 border-b-2 -mb-px transition ${
        active ? "border-primary text-primary font-medium" : "border-transparent text-ink-muted hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function DetailsTab({ trip }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <InfoTile icon={CalendarIcon} label="Departure" value={formatDate(trip.departure_date)} />
        <InfoTile icon={CalendarIcon} label="Return" value={trip.return_date ? formatDate(trip.return_date) : "—"} />
        <InfoTile icon={CurrencyInr} label="Cost" value={trip.cost ? currency(trip.cost) : "Free"} />
        <InfoTile icon={Bus} label="Transport" value={trip.transport_mode || "—"} />
      </div>

      {trip.max_students ? (
        <div className="flex items-center gap-2 text-sm text-ink-soft">
          <Users size={16} />
          <span>Maximum {trip.max_students} students</span>
        </div>
      ) : null}

      {trip.description ? (
        <div>
          <div className="overline mb-2">About</div>
          <p className="text-sm text-ink-soft whitespace-pre-wrap">{trip.description}</p>
        </div>
      ) : null}

      {trip.itinerary ? (
        <div>
          <div className="overline mb-2 flex items-center gap-1.5"><Path size={14} /> Itinerary</div>
          <p className="text-sm text-ink-soft whitespace-pre-wrap">{trip.itinerary}</p>
        </div>
      ) : null}

      {(trip.contact_person || trip.contact_phone) ? (
        <div>
          <div className="overline mb-2">Contact</div>
          <div className="flex items-center gap-2 text-sm">
            <Phone size={14} className="text-ink-muted" />
            <span>{trip.contact_person}</span>
            {trip.contact_phone ? (
              <a
                href={`tel:${trip.contact_phone}`}
                className="text-primary underline"
                data-testid={`trip-call-${trip.id}`}
              >
                {trip.contact_phone}
              </a>
            ) : null}
          </div>
        </div>
      ) : null}

      {trip.permission_slip_url ? (
        <a
          href={trip.permission_slip_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-secondary w-fit"
          data-testid={`trip-permission-link-${trip.id}`}
        >
          <ArrowSquareOut size={14} /> Permission slip
        </a>
      ) : null}
    </div>
  );
}

function ParentRSVPTab({ trip, onChanged }) {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(null);
  const [notes, setNotes] = useState({});

  const load = () => api.get(`/trips/${trip.id}/my-rsvps`).then((r) => {
    setRows(r.data);
    const n = {};
    r.data.forEach((x) => { if (x.note) n[x.student_id] = x.note; });
    setNotes(n);
  });
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [trip.id]);

  const submit = async (student_id, status) => {
    setBusy(`${student_id}-${status}`);
    try {
      await api.post(`/trips/${trip.id}/rsvp`, {
        student_id, status, note: notes[student_id] || null,
      });
      toast.success(status === "confirmed" ? "Marked as attending" : "Marked as not attending");
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(null);
    }
  };

  if (rows === null) return <div className="skeleton h-20 w-full" />;
  if (rows.length === 0) {
    return (
      <Empty
        title="No eligible children"
        message="This trip is not open to any of your children's classes."
      />
    );
  }
  if (trip.status === "cancelled") {
    return <Empty title="Trip cancelled" message="RSVP is not available for cancelled trips." />;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-soft">
        Please confirm whether each child will be coming on this trip. You can change your answer
        until the school closes RSVPs.
      </p>
      {rows.map((r) => (
        <div
          key={r.student_id}
          className="border border-line rounded-lg p-4"
          data-testid={`rsvp-child-${r.student_uid}`}
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <div className="font-medium">{r.student_name}</div>
              <div className="text-xs text-ink-muted">{r.student_uid}</div>
            </div>
            <RSVPStatusBadge status={r.status} />
          </div>

          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
            <textarea
              className="input md:col-span-3 text-sm"
              rows={2}
              placeholder="Add an optional note (e.g. dietary requirement)"
              value={notes[r.student_id] || ""}
              onChange={(e) => setNotes({ ...notes, [r.student_id]: e.target.value })}
              data-testid={`rsvp-note-${r.student_uid}`}
            />
            <button
              className="btn-primary md:col-span-1"
              disabled={busy === `${r.student_id}-confirmed`}
              onClick={() => submit(r.student_id, "confirmed")}
              data-testid={`rsvp-confirm-${r.student_uid}`}
            >
              <CheckCircle size={14} /> Yes, attending
            </button>
            <button
              className="btn-secondary md:col-span-1"
              disabled={busy === `${r.student_id}-declined`}
              onClick={() => submit(r.student_id, "declined")}
              data-testid={`rsvp-decline-${r.student_uid}`}
            >
              <XCircle size={14} /> No, can't make it
            </button>
            {r.updated_at ? (
              <div className="text-[11px] text-ink-muted md:col-span-1 self-center md:text-right">
                Last updated {new Date(r.updated_at).toLocaleString()}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function RosterTab({ trip }) {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    api.get(`/trips/${trip.id}/rsvps`).then((r) => setData(r.data));
  }, [trip.id]);

  if (!data) return <div className="skeleton h-20 w-full" />;
  const { summary, rows } = data;

  const filtered = filter === "all" ? rows : rows.filter((r) => r.status === filter);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3" data-testid={`rsvp-summary-${trip.id}`}>
        <Counter label="Confirmed" value={summary.confirmed} tone="success" />
        <Counter label="Declined" value={summary.declined} tone="danger" />
        <Counter label="Pending" value={summary.pending} tone="warning" />
        <Counter label="Eligible" value={summary.total_eligible} tone="info" />
      </div>

      <div className="flex flex-wrap gap-2">
        {[
          { v: "all", label: `All (${rows.length})` },
          { v: "confirmed", label: `Confirmed (${summary.confirmed})` },
          { v: "declined", label: `Declined (${summary.declined})` },
          { v: "pending", label: `Pending (${summary.pending})` },
        ].map((b) => (
          <button
            key={b.v}
            className={`text-xs px-3 py-1.5 rounded-full border transition ${
              filter === b.v
                ? "border-primary text-primary bg-primary-light"
                : "border-line text-ink-soft hover:bg-bg-subtle"
            }`}
            onClick={() => setFilter(b.v)}
            data-testid={`rsvp-filter-${b.v}`}
          >
            {b.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <Empty title="No students in this view" />
      ) : (
        <div className="border border-line rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-bg-subtle text-ink-muted">
              <tr className="text-left">
                <th className="px-3 py-2">Student</th>
                <th className="px-3 py-2">Parent</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 hidden md:table-cell">Note</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filtered.map((r) => (
                <tr key={r.student_id} data-testid={`rsvp-row-${r.student_uid}`}>
                  <td className="px-3 py-2">
                    <div className="font-medium">{r.student_name}</div>
                    <div className="text-[11px] text-ink-muted">{r.student_uid} · Section {r.section}</div>
                  </td>
                  <td className="px-3 py-2 text-ink-soft">
                    <div>{r.parent_name || "—"}</div>
                    {r.parent_phone ? <div className="text-[11px] text-ink-muted">{r.parent_phone}</div> : null}
                  </td>
                  <td className="px-3 py-2"><RSVPStatusBadge status={r.status} /></td>
                  <td className="px-3 py-2 text-ink-soft hidden md:table-cell">{r.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RSVPStatusBadge({ status }) {
  const map = {
    confirmed: { cls: "badge-success", label: "Attending" },
    declined: { cls: "badge-danger", label: "Not attending" },
    pending: { cls: "badge-neutral", label: "Awaiting reply" },
  };
  const m = map[status] || map.pending;
  return <span className={m.cls} data-testid={`rsvp-status-${status}`}>{m.label}</span>;
}

function Counter({ label, value, tone }) {
  const toneMap = {
    success: "text-status-success",
    danger: "text-status-danger",
    warning: "text-status-warning",
    info: "text-status-info",
  };
  return (
    <div className="border border-line rounded-lg p-3 text-center">
      <div className={`font-display text-2xl font-medium ${toneMap[tone] || ""}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-widest text-ink-muted mt-1">{label}</div>
    </div>
  );
}

function InfoTile({ icon: Icon, label, value }) {
  return (
    <div className="border border-line rounded-lg p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-ink-muted mb-1">
        <Icon size={12} /> {label}
      </div>
      <div className="font-display text-sm font-medium">{value}</div>
    </div>
  );
}
