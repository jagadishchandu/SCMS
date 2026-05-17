import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, KPI, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import {
  Plus, Trash, PencilSimple, MapPin, Calendar as CalendarIcon,
  Bus, CurrencyInr, Users, Phone,
} from "@phosphor-icons/react";
import { formatDate, currency } from "../../lib/utils";
import toast from "react-hot-toast";

const EMPTY_FORM = {
  title: "",
  destination: "",
  departure_date: "",
  return_date: "",
  cost: 0,
  transport_mode: "Bus",
  itinerary: "",
  description: "",
  max_students: "",
  contact_person: "",
  contact_phone: "",
  permission_slip_url: "",
  status: "open",
};

const STATUS_BADGE = {
  open: "badge-success",
  closed: "badge-neutral",
  cancelled: "badge-danger",
};

export default function TripsPage() {
  const [trips, setTrips] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    const { data } = await api.get("/trips");
    setTrips(data);
  };
  useEffect(() => { load(); }, []);

  const remove = async (id) => {
    if (!window.confirm("Delete this trip? Parents will not see it anymore.")) return;
    try {
      await api.delete(`/trips/${id}`);
      toast.success("Trip deleted");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  if (trips === null) return <div className="skeleton h-40 w-full" />;

  const today = new Date().toISOString().slice(0, 10);
  const upcoming = trips.filter((t) => (t.departure_date || "") >= today && t.status !== "cancelled");
  const totalCost = trips.reduce((sum, t) => sum + (t.cost || 0), 0);

  return (
    <div data-testid="trips-page">
      <PageHeader
        eyebrow="Educational Trips"
        title="Field trips & excursions"
        subtitle="Plan trips, share details with teachers and parents, and keep everyone informed."
        actions={
          <button
            className="btn-primary"
            onClick={() => { setEditing(null); setOpen(true); }}
            data-testid="add-trip-btn"
          >
            <Plus size={16} /> New trip
          </button>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KPI label="Total trips" value={trips.length} accent="primary" testId="kpi-trips-total" />
        <KPI label="Upcoming" value={upcoming.length} accent="success" testId="kpi-trips-upcoming" />
        <KPI
          label="Cancelled"
          value={trips.filter((t) => t.status === "cancelled").length}
          accent="danger"
          testId="kpi-trips-cancelled"
        />
        <KPI
          label="Total cost (announced)"
          value={currency(totalCost)}
          accent="info"
          testId="kpi-trips-cost"
        />
      </div>

      <Section title={`${trips.length} trip${trips.length === 1 ? "" : "s"}`}>
        {trips.length === 0 ? (
          <Empty
            title="No trips yet"
            message="Add your first educational trip — teachers and parents will be notified."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {trips.map((t) => (
              <TripCard
                key={t.id}
                trip={t}
                onEdit={() => { setEditing(t); setOpen(true); }}
                onDelete={() => remove(t.id)}
              />
            ))}
          </div>
        )}
      </Section>

      <TripFormModal
        open={open}
        trip={editing}
        onClose={() => { setOpen(false); setEditing(null); }}
        onSaved={() => { setOpen(false); setEditing(null); load(); }}
      />
    </div>
  );
}

function TripCard({ trip, onEdit, onDelete }) {
  return (
    <div
      className="border border-line rounded-lg p-5 flex flex-col gap-3"
      data-testid={`trip-card-${trip.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-primary-light grid place-items-center shrink-0">
            <Bus size={20} className="text-primary" />
          </div>
          <div className="min-w-0">
            <div className="font-display text-base font-medium truncate" data-testid={`trip-title-${trip.id}`}>
              {trip.title}
            </div>
            <div className="text-xs text-ink-muted flex items-center gap-1 mt-0.5">
              <MapPin size={12} /> {trip.destination}
            </div>
          </div>
        </div>
        <span className={STATUS_BADGE[trip.status] || "badge-neutral"} data-testid={`trip-status-${trip.id}`}>
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
        <div className="text-sm text-ink-soft line-clamp-3">{trip.description}</div>
      ) : null}

      {(trip.contact_person || trip.contact_phone) ? (
        <div className="text-xs text-ink-muted flex items-center gap-1.5">
          <Phone size={12} /> {trip.contact_person} {trip.contact_phone}
        </div>
      ) : null}

      <div className="flex gap-2 pt-1 mt-auto">
        <button
          className="btn-secondary flex-1"
          onClick={onEdit}
          data-testid={`edit-trip-${trip.id}`}
        >
          <PencilSimple size={14} /> Edit
        </button>
        <button
          className="btn-ghost p-2 text-status-danger"
          onClick={onDelete}
          data-testid={`del-trip-${trip.id}`}
        >
          <Trash size={14} />
        </button>
      </div>
    </div>
  );
}

function TripFormModal({ open, trip, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (trip) {
      setForm({
        title: trip.title || "",
        destination: trip.destination || "",
        departure_date: trip.departure_date || "",
        return_date: trip.return_date || "",
        cost: trip.cost ?? 0,
        transport_mode: trip.transport_mode || "Bus",
        itinerary: trip.itinerary || "",
        description: trip.description || "",
        max_students: trip.max_students ?? "",
        contact_person: trip.contact_person || "",
        contact_phone: trip.contact_phone || "",
        permission_slip_url: trip.permission_slip_url || "",
        status: trip.status || "open",
      });
    } else {
      setForm(EMPTY_FORM);
    }
  }, [trip, open]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        ...form,
        cost: Number(form.cost) || 0,
        max_students: form.max_students === "" ? null : Number(form.max_students),
      };
      if (trip) {
        await api.patch(`/trips/${trip.id}`, payload);
        toast.success("Trip updated");
      } else {
        await api.post("/trips", payload);
        toast.success("Trip created");
      }
      onSaved();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={trip ? "Edit trip" : "New educational trip"}
      size="lg"
      testId="trip-form-modal"
    >
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="md:col-span-2">
          <label className="label">Title</label>
          <input
            className="input"
            required
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="e.g. Grade 5 visit to Science Museum"
            data-testid="trip-title"
          />
        </div>

        <div className="md:col-span-2">
          <label className="label">Destination / Location</label>
          <input
            className="input"
            required
            value={form.destination}
            onChange={(e) => setForm({ ...form, destination: e.target.value })}
            placeholder="e.g. Visvesvaraya Industrial Museum, Bengaluru"
            data-testid="trip-destination"
          />
        </div>

        <div>
          <label className="label">Departure date</label>
          <input
            type="date"
            className="input"
            required
            value={form.departure_date}
            onChange={(e) => setForm({ ...form, departure_date: e.target.value })}
            data-testid="trip-departure-date"
          />
        </div>
        <div>
          <label className="label">Return date</label>
          <input
            type="date"
            className="input"
            value={form.return_date}
            onChange={(e) => setForm({ ...form, return_date: e.target.value })}
            data-testid="trip-return-date"
          />
        </div>

        <div>
          <label className="label">Cost per student (₹)</label>
          <input
            type="number"
            min="0"
            className="input"
            value={form.cost}
            onChange={(e) => setForm({ ...form, cost: e.target.value })}
            data-testid="trip-cost"
          />
        </div>
        <div>
          <label className="label">Transport mode</label>
          <select
            className="input"
            value={form.transport_mode}
            onChange={(e) => setForm({ ...form, transport_mode: e.target.value })}
            data-testid="trip-transport"
          >
            {["Bus", "Train", "Flight", "Van", "Walk", "Other"].map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label">Max students</label>
          <input
            type="number"
            min="0"
            className="input"
            value={form.max_students}
            onChange={(e) => setForm({ ...form, max_students: e.target.value })}
            data-testid="trip-max-students"
          />
        </div>
        <div>
          <label className="label">Status</label>
          <select
            className="input"
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value })}
            data-testid="trip-status-select"
          >
            <option value="open">Open</option>
            <option value="closed">Closed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        <div>
          <label className="label">Contact person</label>
          <input
            className="input"
            value={form.contact_person}
            onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
            data-testid="trip-contact-person"
          />
        </div>
        <div>
          <label className="label">Contact phone</label>
          <input
            className="input"
            value={form.contact_phone}
            onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
            data-testid="trip-contact-phone"
          />
        </div>

        <div className="md:col-span-2">
          <label className="label">Itinerary</label>
          <textarea
            className="input"
            rows={3}
            placeholder="Day-by-day plan, departure time, lunch arrangements, etc."
            value={form.itinerary}
            onChange={(e) => setForm({ ...form, itinerary: e.target.value })}
            data-testid="trip-itinerary"
          />
        </div>

        <div className="md:col-span-2">
          <label className="label">Description</label>
          <textarea
            className="input"
            rows={3}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            data-testid="trip-description"
          />
        </div>

        <div className="md:col-span-2">
          <label className="label">Permission slip URL (optional)</label>
          <input
            className="input"
            placeholder="https://…"
            value={form.permission_slip_url}
            onChange={(e) => setForm({ ...form, permission_slip_url: e.target.value })}
            data-testid="trip-permission-url"
          />
        </div>

        <div className="md:col-span-2 flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            type="submit"
            className="btn-primary"
            disabled={busy}
            data-testid="submit-trip-btn"
          >
            {busy ? "Saving…" : trip ? "Save changes" : "Create trip"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
