"use client";

import { useEffect, useRef, useState } from "react";
import { X, Minus, Plus, ShoppingCart } from "lucide-react";
import { Product } from "@/types";
import api from "@/lib/axios";
import { useCartStore } from "@/stores/cartStore";

interface Props {
  product: Product;
  onClose: () => void;
}

export default function ProductModal({ product, onClose }: Props) {
  const [quantity, setQuantity] = useState(1);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [error, setError] = useState("");
  const setItemCount = useCartStore((s) => s.setItemCount);
  const overlayRef = useRef<HTMLDivElement>(null);

  const maxStock = product.stock ?? 99;

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === overlayRef.current) onClose();
  }

  async function handleAddToCart() {
    setError("");
    setAdding(true);
    try {
      await api.post("/api/v1/cart/items", {
        productId: product.id,
        quantity,
      });
      const { data } = await api.get("/api/v1/cart");
      setItemCount(
        (data.items as { quantity: number }[]).reduce((s, i) => s + i.quantity, 0)
      );
      setAdded(true);
      setTimeout(onClose, 800);
    } catch {
      setError("Could not add to cart. Please try again.");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
    >
      <div className="card w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h2 className="heading-section">{product.name}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-text-muted hover:text-text hover:bg-surface-low transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Image */}
        <div className="w-full h-56 bg-surface-low flex items-center justify-center">
          {product.imageUrl ? (
            <img
              src={product.imageUrl}
              alt={product.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="text-4xl text-border">📦</div>
          )}
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* Price + stock */}
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold text-text">
              ${product.price.toFixed(2)}
            </span>
            {product.stock !== undefined && (
              <span
                className={[
                  "badge",
                  product.stock > 0 ? "badge-success" : "badge-danger",
                ].join(" ")}
              >
                {product.stock > 0 ? `${product.stock} in stock` : "Out of stock"}
              </span>
            )}
          </div>

          {/* Description */}
          {product.description && (
            <p className="text-sm text-text-secondary leading-relaxed">
              {product.description}
            </p>
          )}

          {/* Quantity stepper */}
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-text">Quantity</span>
            <div className="flex items-center border border-border rounded-lg overflow-hidden">
              <button
                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                disabled={quantity <= 1}
                className="px-3 py-2 text-text-secondary hover:bg-surface-low disabled:opacity-40 transition-colors"
              >
                <Minus size={14} />
              </button>
              <span className="px-4 py-2 text-sm font-semibold text-text min-w-[40px] text-center border-x border-border">
                {quantity}
              </span>
              <button
                onClick={() => setQuantity((q) => Math.min(maxStock, q + 1))}
                disabled={quantity >= maxStock}
                className="px-3 py-2 text-text-secondary hover:bg-surface-low disabled:opacity-40 transition-colors"
              >
                <Plus size={14} />
              </button>
            </div>
          </div>

          {error && (
            <p className="text-sm text-danger">{error}</p>
          )}

          {/* CTA */}
          <button
            onClick={handleAddToCart}
            disabled={adding || added || maxStock === 0}
            className="btn-primary w-full"
          >
            {added ? (
              "Added ✓"
            ) : adding ? (
              <span className="flex items-center justify-center gap-2">
                <span className="spinner w-4 h-4" />
                Adding…
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                <ShoppingCart size={16} />
                Add to Cart — ${(product.price * quantity).toFixed(2)}
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
