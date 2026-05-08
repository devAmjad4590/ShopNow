import { MapPin, Trash2 } from "lucide-react";
import { Address } from "@/types";

interface Props {
  address: Address;
  onDelete: (id: string) => void;
  deleting: boolean;
}

export default function AddressCard({ address, onDelete, deleting }: Props) {
  return (
    <div className="card p-4 flex gap-3 items-start">
      <div className="w-8 h-8 rounded-lg bg-primary-light flex items-center justify-center flex-none mt-0.5">
        <MapPin size={15} className="text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text">{address.street}</p>
        <p className="text-xs text-text-secondary mt-0.5">
          {address.city}, {address.country}
        </p>
      </div>
      <button
        onClick={() => onDelete(address.id)}
        disabled={deleting}
        className="p-1.5 text-text-muted hover:text-danger hover:bg-danger-bg rounded-md transition-colors flex-none disabled:opacity-40"
      >
        <Trash2 size={15} />
      </button>
    </div>
  );
}
