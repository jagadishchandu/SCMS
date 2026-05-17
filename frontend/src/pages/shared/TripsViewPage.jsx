import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { useAuth } from "../../contexts/AuthContext";
import {
  Bus, MapPin, Calendar as CalendarIcon, CurrencyInr, Users,
  Phone, Path, ArrowSquareOut,
} from "@phosphor-icons/react";
import { formatDate, currency } from "../../lib/utils";

const STATUS_BADGE = {
  open: "badge-success",
  closed: "badge-neutral",
  cancelled: "badge-danger",
};

export default function TripsViewPage() {
  const { user } = useAuth();
  const [trips, setTrips] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    api.get("/trips").then((r) => setTrips(r.data)).catch(() => setTrips([]));
  }, []);

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
            ? "Field trips and excursions announced by the school. Tap a trip for full details."
            : "Educational trips scheduled by the school admin."
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
        <TripDetailsModal trip={selected} onClose={() => setSelected(null)} />
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

function TripDetailsModal({ trip, onClose }) {
  return (
    <Modal open onClose={onClose} title={trip.title} size="lg" testId={`trip-details-${trip.id}`}>
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-ink-soft">
            <MapPin size={16} />
            <span className="font-medium text-ink">{trip.destination}</span>
          </div>
          <span className={STATUS_BADGE[trip.status] || "badge-neutral"}>
            {trip.status || "open"}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <InfoTile icon={CalendarIcon} label="Departure" value={formatDate(trip.departure_date)} />
          <InfoTile icon={CalendarIcon} label="Return" value={trip.return_date ? formatDate(trip.return_date) : "—"} />
          <InfoTile
            icon={CurrencyInr}
            label="Cost"
            value={trip.cost ? currency(trip.cost) : "Free"}
          />
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
    </Modal>
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
