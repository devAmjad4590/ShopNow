export interface Category {
  id: string;
  name: string;
}

export interface Product {
  id: string;
  name: string;
  description: string;
  price: number;
  categoryId: string;
  imageUrl?: string;
  stock?: number;
}

export interface CartItem {
  productId: string;
  productName: string;
  quantity: number;
  unitPrice: number;
}

export interface Cart {
  userId: string;
  items: CartItem[];
  total: number;
}

export interface Order {
  id: string;
  status: "PENDING" | "CONFIRMED" | "FAILED";
  items: { productId: string; productName: string; quantity: number; unitPrice: number }[];
  totalAmount: number;
  createdAt: string;
  addressId: string;
}

export interface Address {
  id: string;
  street: string;
  city: string;
  country: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
}
