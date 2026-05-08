"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, LogOut, X } from "lucide-react";
import api from "@/lib/axios";
import { useAuthStore } from "@/stores/authStore";
import { User, Address } from "@/types";
import AddressCard from "@/components/AddressCard";

interface AddressForm {
  street: string;
  city: string;
  country: string;
}

const EMPTY_FORM: AddressForm = { street: "", city: "", country: "" };

function getInitials(name: string) {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export default function ProfilePage() {
  const router = useRouter();
  const { user: storeUser, clearAuth } = useAuthStore();

  const [user, setUser] = useState<User | null>(storeUser);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<AddressForm>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Partial<AddressForm>>({});
  const [saving, setSaving] = useState(false);

  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [userRes, addrRes] = await Promise.all([
          api.get<User>("/api/v1/users/me"),
          api.get<Address[]>("/api/v1/users/me/addresses"),
        ]);
        setUser(userRes.data);
        setAddresses(addrRes.data);
      } catch {
        setError("Could not load profile.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function handleLogout() {
    clearAuth();
    document.cookie = "isLoggedIn=; path=/; max-age=0";
    router.push("/auth");
  }

  async function handleDeleteAddress(id: string) {
    setDeletingId(id);
    try {
      await api.delete(`/api/v1/users/me/addresses/${id}`);
      setAddresses((prev) => prev.filter((a) => a.id !== id));
    } catch {
      /* silent */
    } finally {
      setDeletingId(null);
    }
  }

  function validateForm(): boolean {
    const errors: Partial<AddressForm> = {};
    if (!form.street.trim()) errors.street = "Required";
    if (!form.city.trim()) errors.city = "Required";
    if (!form.country.trim()) errors.country = "Required";
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSaveAddress() {
    if (!validateForm()) return;
    setSaving(true);
    try {
      const { data } = await api.post<Address>("/api/v1/users/me/addresses", form);
      setAddresses((prev) => [...prev, data]);
      setForm(EMPTY_FORM);
      setFormErrors({});
      setShowForm(false);
    } catch {
      setFormErrors({ street: "Could not save address. Try again." });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="container-page py-20 flex justify-center">
        <span className="spinner w-8 h-8" />
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

  return (
    <div className="container-page py-8 max-w-2xl mx-auto space-y-6">
      {/* ── Profile header ──────────────────────────────────── */}
      <div className="card p-6 flex items-center gap-5">
        {/* Avatar */}
        <div className="w-16 h-16 rounded-full bg-primary flex items-center justify-center flex-none">
          <span className="text-xl font-bold text-white">
            {user ? getInitials(user.name) : "?"}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-bold text-text truncate">{user?.name}</h1>
          <p className="text-sm text-text-secondary truncate">{user?.email}</p>
        </div>
        <button
          onClick={handleLogout}
          className="btn-danger flex-none"
        >
          <LogOut size={15} />
          Logout
        </button>
      </div>

      {/* ── Saved addresses ─────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="heading-section">Saved Addresses</h2>
          {!showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="btn-ghost text-xs px-3 py-1.5"
            >
              <Plus size={14} />
              Add New
            </button>
          )}
        </div>

        {addresses.length === 0 && !showForm && (
          <p className="text-sm text-text-muted py-2">No saved addresses yet.</p>
        )}

        {addresses.map((addr) => (
          <AddressCard
            key={addr.id}
            address={addr}
            onDelete={handleDeleteAddress}
            deleting={deletingId === addr.id}
          />
        ))}

        {/* ── Add address form ─────────────────────────────── */}
        {showForm && (
          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between mb-1">
              <p className="text-sm font-semibold text-text">New Address</p>
              <button
                onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setFormErrors({}); }}
                className="p-1 text-text-muted hover:text-text rounded transition-colors"
              >
                <X size={15} />
              </button>
            </div>

            {(["street", "city", "country"] as (keyof AddressForm)[]).map((field) => (
              <div key={field}>
                <input
                  type="text"
                  placeholder={field.charAt(0).toUpperCase() + field.slice(1)}
                  value={form[field]}
                  onChange={(e) => setForm((f) => ({ ...f, [field]: e.target.value }))}
                  className={["input text-sm", formErrors[field] ? "input-error" : ""].join(" ")}
                />
                {formErrors[field] && (
                  <p className="mt-0.5 text-xs text-danger">{formErrors[field]}</p>
                )}
              </div>
            ))}

            <button
              onClick={handleSaveAddress}
              disabled={saving}
              className="btn-primary w-full"
            >
              {saving ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="spinner w-4 h-4" />
                  Saving…
                </span>
              ) : (
                "Save Address"
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
