"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Minus, Plus, Trash2, ShoppingBag, Lock } from "lucide-react";
import Link from "next/link";
import api from "@/lib/axios";
import { useCartStore } from "@/stores/cartStore";
import { Cart, CartItem, Address } from "@/types";

interface AddressForm {
  street: string;
  city: string;
  country: string;
}

export default function CartPage() {
  const router = useRouter();
  const setItemCount = useCartStore((s) => s.setItemCount);

  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // per-item quantity update in-flight
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  // place order state
  const [placing, setPlacing] = useState(false);
  const [placeError, setPlaceError] = useState("");
  const [needsAddress, setNeedsAddress] = useState(false);
  const [addressForm, setAddressForm] = useState<AddressForm>({
    street: "",
    city: "",
    country: "",
  });
  const [addressErrors, setAddressErrors] = useState<Partial<AddressForm>>({});

  async function fetchCart() {
    try {
      const { data } = await api.get<Cart>("/api/v1/cart");
      setCart(data);
      const count = data.items.reduce((s, i) => s + i.quantity, 0);
      setItemCount(count);
    } catch {
      setError("Could not load cart.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchCart(); }, []);

  async function updateQuantity(productId: string, quantity: number) {
    setUpdatingId(productId);
    try {
      await api.put(`/api/v1/cart/items/${productId}`, { quantity });
      await fetchCart();
    } catch {
      /* silent — UI stays */
    } finally {
      setUpdatingId(null);
    }
  }

  async function removeItem(productId: string) {
    setUpdatingId(productId);
    try {
      await api.delete(`/api/v1/cart/items/${productId}`);
      await fetchCart();
    } catch {
      /* silent */
    } finally {
      setUpdatingId(null);
    }
  }

  async function clearCart() {
    try {
      await api.delete("/api/v1/cart");
      setCart(null);
      setItemCount(0);
    } catch {
      /* silent */
    }
  }

  function validateAddress(): boolean {
    const errors: Partial<AddressForm> = {};
    if (!addressForm.street.trim()) errors.street = "Required";
    if (!addressForm.city.trim()) errors.city = "Required";
    if (!addressForm.country.trim()) errors.country = "Required";
    setAddressErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handlePlaceOrder() {
    setPlaceError("");
    setPlacing(true);
    try {
      // 1. Fetch addresses
      const { data: addresses } = await api.get<Address[]>("/api/v1/users/me/addresses");

      let addressId: string;

      if (addresses.length > 0) {
        addressId = addresses[0].id;
      } else {
        // Need address from user
        setNeedsAddress(true);
        setPlacing(false);
        return;
      }

      await submitOrder(addressId);
    } catch {
      setPlaceError("Could not reach server. Try again.");
      setPlacing(false);
    }
  }

  async function handleAddressSubmit() {
    if (!validateAddress()) return;
    setPlacing(true);
    setPlaceError("");
    try {
      const { data: newAddress } = await api.post<Address>(
        "/api/v1/users/me/addresses",
        addressForm
      );
      await submitOrder(newAddress.id);
    } catch {
      setPlaceError("Could not save address. Try again.");
      setPlacing(false);
    }
  }

  async function submitOrder(addressId: string) {
    try {
      const { data: order } = await api.post("/api/v1/orders", { addressId });
      setItemCount(0);
      router.push(`/orders/${order.id}`);
    } catch {
      setPlaceError("Could not place order. Try again.");
      setPlacing(false);
    }
  }

  const subtotal = cart?.items.reduce(
    (s, i) => s + i.unitPrice * i.quantity, 0
  ) ?? 0;

  // ── Empty state ───────────────────────────────────────────────
  if (!loading && (!cart || cart.items.length === 0)) {
    return (
      <div className="container-page py-20 flex flex-col items-center gap-4 text-center">
        <ShoppingBag size={48} className="text-border" />
        <h2 className="heading-section text-text-secondary">Your cart is empty</h2>
        <p className="text-sm text-text-muted">Add some products to get started</p>
        <Link href="/products" className="btn-primary mt-2">
          Browse Products
        </Link>
      </div>
    );
  }

  return (
    <div className="container-page py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="heading-page">Shopping Cart</h1>
        {cart && cart.items.length > 0 && (
          <button
            onClick={clearCart}
            className="text-sm text-text-muted hover:text-danger transition-colors"
          >
            Clear cart
          </button>
        )}
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

      {!loading && cart && cart.items.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ── Left: items ──────────────────────────────────── */}
          <div className="lg:col-span-2 space-y-3">
            {cart.items.map((item: CartItem) => (
              <div key={item.productId} className="card p-4 flex gap-4 items-center">
                {/* Placeholder image */}
                <div className="w-16 h-16 rounded-lg bg-surface-low flex-none flex items-center justify-center text-2xl">
                  📦
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-text truncate">
                    {item.productName}
                  </p>
                  <p className="text-xs text-text-secondary mt-0.5">
                    ${item.unitPrice.toFixed(2)} each
                  </p>
                </div>

                {/* Quantity stepper */}
                <div className="flex items-center border border-border rounded-lg overflow-hidden flex-none">
                  <button
                    onClick={() => updateQuantity(item.productId, item.quantity - 1)}
                    disabled={item.quantity <= 1 || updatingId === item.productId}
                    className="px-2.5 py-2 text-text-secondary hover:bg-surface-low disabled:opacity-40 transition-colors"
                  >
                    <Minus size={13} />
                  </button>
                  <span className="px-3 py-2 text-sm font-semibold text-text min-w-[36px] text-center border-x border-border">
                    {updatingId === item.productId ? (
                      <span className="spinner w-3 h-3 inline-block" />
                    ) : (
                      item.quantity
                    )}
                  </span>
                  <button
                    onClick={() => updateQuantity(item.productId, item.quantity + 1)}
                    disabled={updatingId === item.productId}
                    className="px-2.5 py-2 text-text-secondary hover:bg-surface-low disabled:opacity-40 transition-colors"
                  >
                    <Plus size={13} />
                  </button>
                </div>

                {/* Line total */}
                <p className="text-sm font-bold text-text w-16 text-right flex-none">
                  ${(item.unitPrice * item.quantity).toFixed(2)}
                </p>

                {/* Delete */}
                <button
                  onClick={() => removeItem(item.productId)}
                  disabled={updatingId === item.productId}
                  className="p-1.5 text-text-muted hover:text-danger hover:bg-danger-bg rounded-md transition-colors flex-none"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>

          {/* ── Right: order summary ─────────────────────────── */}
          <div className="lg:col-span-1">
            <div className="card p-5 sticky top-24 space-y-4">
              <h2 className="heading-section">Order Summary</h2>

              <div className="space-y-2 text-sm">
                <div className="flex justify-between text-text-secondary">
                  <span>Subtotal</span>
                  <span>${subtotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-text-secondary">
                  <span>Shipping</span>
                  <span className="text-text-muted text-xs">Calculated at checkout</span>
                </div>
              </div>

              <hr className="divider" />

              <div className="flex justify-between font-bold text-text">
                <span>Total</span>
                <span>${subtotal.toFixed(2)}</span>
              </div>

              {/* Address form (shown when no address on file) */}
              {needsAddress && (
                <div className="space-y-3 pt-2 border-t border-border">
                  <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    Delivery Address
                  </p>
                  {(["street", "city", "country"] as (keyof AddressForm)[]).map((field) => (
                    <div key={field}>
                      <input
                        type="text"
                        placeholder={field.charAt(0).toUpperCase() + field.slice(1)}
                        value={addressForm[field]}
                        onChange={(e) =>
                          setAddressForm((f) => ({ ...f, [field]: e.target.value }))
                        }
                        className={["input text-sm", addressErrors[field] ? "input-error" : ""].join(" ")}
                      />
                      {addressErrors[field] && (
                        <p className="mt-0.5 text-xs text-danger">{addressErrors[field]}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {placeError && (
                <p className="text-xs text-danger">{placeError}</p>
              )}

              <button
                onClick={needsAddress ? handleAddressSubmit : handlePlaceOrder}
                disabled={placing}
                className="btn-primary w-full"
              >
                {placing ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="spinner w-4 h-4" />
                    Placing order…
                  </span>
                ) : needsAddress ? (
                  "Save Address & Place Order"
                ) : (
                  "Place Order"
                )}
              </button>

              <div className="flex items-center justify-center gap-1.5 text-xs text-text-muted">
                <Lock size={11} />
                Secure checkout powered by ShopNow
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
