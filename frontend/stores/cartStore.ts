import { create } from "zustand";

interface CartStore {
  itemCount: number;
  setItemCount: (n: number) => void;
}

export const useCartStore = create<CartStore>((set) => ({
  itemCount: 0,
  setItemCount: (n) => set({ itemCount: n }),
}));
