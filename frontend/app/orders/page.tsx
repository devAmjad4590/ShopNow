"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ShoppingBag } from "lucide-react";
import api from "@/lib/axios";
import { Order } from "@/types";
import OrderCard from "@/components/OrderCard";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const { data } = await api.get<Order[]>("/api/v1/orders");
        const sorted = [...data].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        );
        setOrders(sorted);
      } catch {
        setError("Could not load orders.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="container-page py-8 max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="heading-page">My Orders</h1>
        <p className="text-sm text-text-secondary mt-1">
          Track and review your purchases
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-20">
          <span className="spinner w-8 h-8" />
        </div>
      )}

      {error && (
        <div className="px-4 py-3 rounded-lg bg-danger-bg border border-danger text-danger-text text-sm">
          {error}
        </div>
      )}

      {!loading && !error && orders.length === 0 && (
        <div className="flex flex-col items-center py-20 gap-3 text-center">
          <ShoppingBag size={48} className="text-border" />
          <h2 className="heading-section text-text-secondary">No orders yet</h2>
          <p className="text-sm text-text-muted">
            Place your first order to see it here
          </p>
          <Link href="/products" className="btn-primary mt-2">
            Start Shopping
          </Link>
        </div>
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="space-y-3">
          {orders.map((order) => (
            <OrderCard key={order.id} order={order} />
          ))}
        </div>
      )}
    </div>
  );
}
