package com.shopnow.cart_service.dto;

import com.shopnow.cart_service.cart.Cart;
import com.shopnow.cart_service.cart.CartItem;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record CartResponse(
        String userId,
        List<CartItem> items,
        BigDecimal totalAmount,
        Instant updatedAt
) {
    public static CartResponse from(Cart cart) {
        BigDecimal total = cart.getItems().stream()
                .map(item -> item.getPrice().multiply(BigDecimal.valueOf(item.getQuantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return new CartResponse(cart.getUserId(), cart.getItems(), total, cart.getUpdatedAt());
    }
}
