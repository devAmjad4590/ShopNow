import { ShoppingCart } from "lucide-react";
import { Product } from "@/types";

interface Props {
  product: Product;
  onClick: (product: Product) => void;
}

export default function ProductCard({ product, onClick }: Props) {
  return (
    <div
      onClick={() => onClick(product)}
      className="card flex flex-col cursor-pointer hover:shadow-modal transition-shadow duration-150 overflow-hidden group"
    >
      {/* Image */}
      <div className="relative w-full aspect-square bg-surface-low overflow-hidden">
        {product.imageUrl ? (
          <img
            src={product.imageUrl}
            alt={product.name}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-4xl text-border">
            📦
          </div>
        )}
        {/* Stock badge */}
        {product.stock !== undefined && product.stock <= 5 && product.stock > 0 && (
          <span className="absolute top-2 left-2 badge badge-warning text-[10px]">
            Low stock
          </span>
        )}
        {product.stock === 0 && (
          <span className="absolute top-2 left-2 badge badge-danger text-[10px]">
            Sold out
          </span>
        )}
      </div>

      {/* Info */}
      <div className="flex flex-col flex-1 p-4 gap-2">
        <h3 className="text-sm font-semibold text-text leading-snug line-clamp-2">
          {product.name}
        </h3>
        {product.description && (
          <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
            {product.description}
          </p>
        )}
        <div className="mt-auto flex items-center justify-between pt-2">
          <span className="text-base font-bold text-text">
            ${product.price.toFixed(2)}
          </span>
          <button
            onClick={(e) => { e.stopPropagation(); onClick(product); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-hover transition-colors"
          >
            <ShoppingCart size={13} />
            Add
          </button>
        </div>
      </div>
    </div>
  );
}
