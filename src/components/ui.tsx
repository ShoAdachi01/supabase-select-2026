import type React from 'react';
import { LoaderCircle, X } from 'lucide-react';

export function Mark({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand-mark ${small ? 'small' : ''}`}>
      <span />
      <span />
      <span />
    </span>
  );
}
export function Badge({ children, tone = '' }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Loading() {
  return <LoaderCircle size={16} className="spin" />;
}

export function Stat({
  label,
  value,
  icon,
  foot,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  foot: string;
}) {
  return (
    <div className="stat">
      <div>
        {label}
        {icon}
      </div>
      <strong>{value.toString().padStart(2, '0')}</strong>
      <small>{foot}</small>
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading compact">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Empty({
  icon,
  title,
  text,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon}</span>
      <h2>{title}</h2>
      <p>{text}</p>
      {action}
    </div>
  );
}

export function Modal({
  title,
  eyebrow,
  onClose,
  children,
}: {
  title: string;
  eyebrow: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="close-button" aria-label="Close dialog" onClick={onClose}>
          <X size={20} />
        </button>
        <div className="eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
        {children}
      </section>
    </div>
  );
}
