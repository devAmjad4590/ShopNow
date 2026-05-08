"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle, XCircle, Loader2, ArrowLeft } from "lucide-react";
import api from "@/lib/axios";
import { Order } from "@/types";
import SagaTimeline from "@/components/SagaTimeline";

export default function OrderConfirmationPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const [order, setOrder] = useState<Order | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchOrder() {
    try {
      const { data } = await api.get<Order>(`/api/v1/orders/${orderId}`);
      setOrder(data);
      if (data.status !== "PENDING") {
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) setNotFound(true);
      else setError("Could not load order.");
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
  }

  useEffect(() => {
    fetchOrder();
    intervalRef.current = setInterval(fetchOrder, 2000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [orderId]);

  // ── Not found ────────────────────────────────────────────────
  if (notFound) {
    return (
      <div className="container-page py-20 flex flex-col items-center gap-3 text-center">
        <p className="text-text-secondary">Order not found.</p>
        <Link href="/orders" className="text-sm text-primary hover:underline">
          Back to orders
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container-page py-8">
        <div className="px-4 py-3 rounded-lg bg-danger-bg border border-danger text-danger-text text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="container-page py-20 flex justify-center">
        <span className="spinner w-8 h-8" />
      </div>
    );
  }

  // ── Status banner config ─────────────────────────────────────
  const bannerConfig = {
    CONFIRMED: {
      bg: "bg-success-bg border-success",
      icon: <CheckCircle size={28} className="text-success" />,
      title: "Order Confirmed!",
      message: `Your order #${order.id.slice(0, 8).toUpperCase()} is being prepared and will ship soon.`,
    },
    FAILED: {
      bg: "bg-danger-bg border-danger",
      icon: <XCircle size={28} className="text-danger" />,
      title: "Order Failed",
      message: "Payment could not be processed. Your inventory reservation has been released.",
    },
    PENDING: {
      bg: "bg-pending-bg border-border",
      icon: <Loader2 size={28} className="text-pending animate-spin" />,
      title: "Processing your order…",
      message: "We're reserving your items and processing payment. This usually takes a few seconds.",
    },
  }[order.status];

  return (
    <div className="container-page py-8 max-w-2xl mx-auto">
      {/* Back */}
      <Link
        href="/orders"
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text mb-6 transition-colors"
      >
        <ArrowLeft size={14} />
        My Orders
      </Link>

      {/* Status banner */}
      <div className={["card p-5 flex gap-4 items-start border mb-6", bannerConfig.bg].join(" ")}>
        <div className="flex-none mt-0.5">{bannerConfig.icon}</div>
        <div>
          <h1 className="text-lg font-bold text-text">{bannerConfig.title}</h1>
          <p className="text-sm text-text-secondary mt-0.5">{bannerConfig.message}</p>
          <p className="text-xs text-text-muted mt-1 font-mono">
            #{order.id.slice(0, 8).toUpperCase()}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        {/* ── Saga timeline ─────────────────────────────────── */}
        <div className="card p-5">
          <h2 className="heading-section mb-5">Order Progress</h2>
          <SagaTimeline status={order.status} />
        </div>

        {/* ── Order details ──────────────────────────────────── */}
        <div className="card p-5 self-start">
          <h2 className="heading-section mb-4">Order Details</h2>
          <div className="space-y-3">
            {order.items.map((item) => (
              <div key={item.productId} className="flex justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="text-text font-medium leading-snug truncate">
                    {item.productName}
                  </p>
                  <p className="text-xs text-text-secondary">Qty: {item.quantity}</p>
                </div>
                <span className="text-text font-semibold flex-none">
                  ${(item.unitPrice * item.quantity).toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          <hr className="divider my-4" />

          <div className="flex justify-between font-bold text-text">
            <span>Total</span>
            <span>${order.totalAmount.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="mt-6 flex justify-center">
        <Link href="/products" className="btn-primary">
          Continue Shopping
        </Link>
      </div>
    </div>
  );
}
