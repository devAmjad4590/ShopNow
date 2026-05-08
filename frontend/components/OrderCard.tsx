import Link from "next/link";
import { CheckCircle, XCircle, Loader2, ChevronRight, Package } from "lucide-react";
import { Order } from "@/types";

interface Props {
  order: Order;
}

const STATUS_CONFIG = {
  CONFIRMED: {
    label: "Confirmed",
    icon: <CheckCircle size={13} />,
    className: "badge-success",
  },
  FAILED: {
    label: "Failed",
    icon: <XCircle size={13} />,
    className: "badge-danger",
  },
  PENDING: {
    label: "Pending",
    icon: <Loader2 size={13} className="animate-spin" />,
    className: "badge-pending",
  },
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function OrderCard({ order }: Props) {
  const cfg = STATUS_CONFIG[order.status];
  const itemCount = order.items.reduce((s, i) => s + i.quantity, 0);

  return (
    <Link href={`/orders/${order.id}`}>
      <div className="card p-4 flex items-center gap-4 hover:bg-surface-low transition-colors cursor-pointer group">
        {/* Icon */}
        <div className="w-10 h-10 rounded-lg bg-primary-light flex items-center justify-center flex-none">
          <Package size={18} className="text-primary" />
        </div>

        {/* Main info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-text font-mono">
              #{order.id.slice(0, 8).toUpperCase()}
            </span>
            <span className={`badge ${cfg.className}`}>
              {cfg.icon}
              {cfg.label}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-text-secondary">
            <span>{formatDate(order.createdAt)}</span>
            <span>·</span>
            <span>{itemCount} {itemCount === 1 ? "item" : "items"}</span>
          </div>
        </div>

        {/* Total + chevron */}
        <div className="flex items-center gap-2 flex-none">
          <span className="text-sm font-bold text-text">
            ${order.totalAmount.toFixed(2)}
          </span>
          <ChevronRight
            size={16}
            className="text-text-muted group-hover:text-primary transition-colors"
          />
        </div>
      </div>
    </Link>
  );
}
