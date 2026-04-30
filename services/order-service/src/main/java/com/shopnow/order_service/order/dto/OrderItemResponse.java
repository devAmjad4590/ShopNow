package com.shopnow.order_service.order.dto;

import com.shopnow.order_service.order.OrderItem;

import java.math.BigDecimal;

public record OrderItemResponse(
        Long productId,
        String productName,
        BigDecimal price,
        Integer quantity
) {
    public static OrderItemResponse from(OrderItem item) {
        return new OrderItemResponse(item.getProductId(), item.getProductName(), item.getPrice(), item.getQuantity());
    }
}
