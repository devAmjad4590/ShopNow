"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import api from "@/lib/axios";
import { useAuthStore } from "@/stores/authStore";
import { Product, Category } from "@/types";
import ProductCard from "@/components/ProductCard";
import ProductModal from "@/components/ProductModal";

export default function ProductsPage() {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);

  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [activeCategoryId, setActiveCategoryId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [catRes, prodRes] = await Promise.all([
          api.get("/api/v1/categories"),
          api.get("/api/v1/products"),
        ]);
        setCategories(catRes.data);
        setProducts(prodRes.data);
      } catch {
        setError("Could not load products. Please try again.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function handleProductClick(product: Product) {
    const isLoggedIn = document.cookie
      .split("; ")
      .find((r) => r.startsWith("isLoggedIn="))
      ?.split("=")[1];

    if (!accessToken && isLoggedIn !== "true") {
      router.push("/auth");
      return;
    }
    setSelectedProduct(product);
  }

  const filtered = products.filter((p) => {
    const matchCategory = activeCategoryId ? p.categoryId === activeCategoryId : true;
    const matchSearch = search
      ? p.name.toLowerCase().includes(search.toLowerCase()) ||
        p.description?.toLowerCase().includes(search.toLowerCase())
      : true;
    return matchCategory && matchSearch;
  });

  return (
    <div className="container-page py-8">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="heading-page">Explore Products</h1>
        <p className="text-sm text-text-secondary mt-1">
          {products.length} items available
        </p>
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
        />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search products…"
          className="input pl-9"
        />
      </div>

      {/* Category pills */}
      <div className="flex gap-2 overflow-x-auto pb-2 mb-6 scrollbar-none">
        <button
          onClick={() => setActiveCategoryId(null)}
          className={[
            "flex-none px-4 py-1.5 rounded-full text-sm font-medium border transition-colors whitespace-nowrap",
            activeCategoryId === null
              ? "bg-primary text-white border-primary"
              : "bg-surface text-text-secondary border-border hover:border-primary hover:text-primary",
          ].join(" ")}
        >
          All
        </button>
        {categories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategoryId(cat.id)}
            className={[
              "flex-none px-4 py-1.5 rounded-full text-sm font-medium border transition-colors whitespace-nowrap",
              activeCategoryId === cat.id
                ? "bg-primary text-white border-primary"
                : "bg-surface text-text-secondary border-border hover:border-primary hover:text-primary",
            ].join(" ")}
          >
            {cat.name}
          </button>
        ))}
      </div>

      {/* States */}
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

      {!loading && !error && filtered.length === 0 && (
        <div className="flex flex-col items-center py-20 text-text-secondary gap-2">
          <span className="text-4xl">🔍</span>
          <p className="text-sm">No products found</p>
          {(search || activeCategoryId) && (
            <button
              onClick={() => { setSearch(""); setActiveCategoryId(null); }}
              className="text-sm text-primary hover:underline mt-1"
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {/* Product grid */}
      {!loading && !error && filtered.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {filtered.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              onClick={handleProductClick}
            />
          ))}
        </div>
      )}

      {/* Modal */}
      {selectedProduct && (
        <ProductModal
          product={selectedProduct}
          onClose={() => setSelectedProduct(null)}
        />
      )}
    </div>
  );
}
