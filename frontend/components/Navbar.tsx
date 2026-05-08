"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ShoppingCart, LogOut } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { useCartStore } from "@/stores/cartStore";

const NAV_LINKS = [
  { href: "/products", label: "Products" },
  { href: "/orders", label: "Orders" },
  { href: "/profile", label: "Profile" },
];

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const itemCount = useCartStore((s) => s.itemCount);

  if (pathname === "/auth") return null;

  function handleLogout() {
    clearAuth();
    document.cookie = "isLoggedIn=; path=/; max-age=0";
    router.push("/auth");
  }

  return (
    <nav className="navbar sticky top-0 z-50">
      <div className="container-page flex items-center justify-between h-full">
        {/* Logo */}
        <Link
          href="/products"
          className="text-lg font-bold text-primary tracking-tight"
        >
          ShopNow
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={[
                  "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                  active
                    ? "text-primary bg-primary-light"
                    : "text-text-secondary hover:text-text hover:bg-surface-low",
                ].join(" ")}
              >
                {label}
              </Link>
            );
          })}
        </div>

        {/* Right side */}
        <div className="flex items-center gap-2">
          <Link
            href="/cart"
            className="relative p-2 rounded-md text-text-secondary hover:text-text hover:bg-surface-low transition-colors"
            aria-label="Cart"
          >
            <ShoppingCart size={20} />
            {itemCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-primary text-white text-[10px] font-bold px-1">
                {itemCount > 99 ? "99+" : itemCount}
              </span>
            )}
          </Link>

          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium text-text-secondary hover:text-danger hover:bg-danger-bg transition-colors"
          >
            <LogOut size={15} />
            Logout
          </button>
        </div>
      </div>
    </nav>
  );
}
