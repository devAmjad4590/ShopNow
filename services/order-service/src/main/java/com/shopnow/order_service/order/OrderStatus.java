package com.shopnow.order_service.order;

public enum OrderStatus {
    PENDING,
    INVENTORY_RESERVED,
    CONFIRMED,
    FAILED,
    CANCELLED
}
