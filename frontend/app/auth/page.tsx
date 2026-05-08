"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, ShoppingBag } from "lucide-react";
import api from "@/lib/axios";
import { useAuthStore } from "@/stores/authStore";

type Tab = "login" | "register";

interface FieldErrors {
  name?: string;
  email?: string;
  password?: string;
}

export default function AuthPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  const [tab, setTab] = useState<Tab>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  useEffect(() => {
    const isLoggedIn = document.cookie
      .split("; ")
      .find((r) => r.startsWith("isLoggedIn="))
      ?.split("=")[1];
    if (isLoggedIn === "true") router.replace("/products");
  }, [router]);

  function resetForm() {
    setName("");
    setEmail("");
    setPassword("");
    setFieldErrors({});
    setServerError("");
    setShowPassword(false);
  }

  function switchTab(t: Tab) {
    setTab(t);
    resetForm();
  }

  function validate(): boolean {
    const errors: FieldErrors = {};
    if (tab === "register" && !name.trim()) errors.name = "Full name is required";
    if (!email.trim()) {
      errors.email = "Email is required";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errors.email = "Invalid email address";
    }
    if (!password) {
      errors.password = "Password is required";
    } else if (password.length < 6) {
      errors.password = "Password must be at least 6 characters";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError("");
    if (!validate()) return;

    setLoading(true);
    try {
      const endpoint =
        tab === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const payload =
        tab === "login"
          ? { email, password }
          : { name, email, password };

      const { data } = await api.post(endpoint, payload);
      const { accessToken, user } = data;

      setAuth(accessToken, user);
      document.cookie = "isLoggedIn=true; path=/; max-age=86400; SameSite=Lax";
      router.replace("/products");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message ?? "Something went wrong. Please try again.";
      setServerError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4 py-12">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center mb-3">
            <ShoppingBag size={24} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-text tracking-tight">ShopNow</h1>
          <p className="text-sm text-text-secondary mt-1">
            {tab === "login" ? "Welcome back" : "Create your account"}
          </p>
        </div>

        {/* Card */}
        <div className="card p-8">
          {/* Tab toggle */}
          <div className="flex rounded-lg bg-surface-low p-1 mb-6">
            {(["login", "register"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => switchTab(t)}
                className={[
                  "flex-1 py-2 text-sm font-medium rounded-md transition-all capitalize",
                  tab === t
                    ? "bg-surface text-text shadow-sm"
                    : "text-text-secondary hover:text-text",
                ].join(" ")}
              >
                {t === "login" ? "Login" : "Register"}
              </button>
            ))}
          </div>

          {/* Server error banner */}
          {serverError && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-danger-bg border border-danger text-danger-text text-sm">
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            {/* Full Name — register only */}
            {tab === "register" && (
              <div>
                <label className="label" htmlFor="name">Full Name</label>
                <input
                  id="name"
                  type="text"
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className={["input", fieldErrors.name ? "input-error" : ""].join(" ")}
                  placeholder="John Doe"
                />
                {fieldErrors.name && (
                  <p className="mt-1 text-xs text-danger">{fieldErrors.name}</p>
                )}
              </div>
            )}

            {/* Email */}
            <div>
              <label className="label" htmlFor="email">Email Address</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={["input", fieldErrors.email ? "input-error" : ""].join(" ")}
                placeholder="you@example.com"
              />
              {fieldErrors.email && (
                <p className="mt-1 text-xs text-danger">{fieldErrors.email}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label className="label" htmlFor="password">Password</label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={tab === "login" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={["input pr-10", fieldErrors.password ? "input-error" : ""].join(" ")}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {fieldErrors.password && (
                <p className="mt-1 text-xs text-danger">{fieldErrors.password}</p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full mt-2"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="spinner w-4 h-4" />
                  {tab === "login" ? "Logging in…" : "Creating account…"}
                </span>
              ) : tab === "login" ? (
                "Login"
              ) : (
                "Create Account"
              )}
            </button>
          </form>

          {/* Switch tab hint */}
          <p className="mt-5 text-center text-sm text-text-secondary">
            {tab === "login" ? (
              <>
                No account?{" "}
                <button
                  onClick={() => switchTab("register")}
                  className="text-primary font-medium hover:underline"
                >
                  Register
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={() => switchTab("login")}
                  className="text-primary font-medium hover:underline"
                >
                  Login
                </button>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
