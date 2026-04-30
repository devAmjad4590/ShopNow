package com.shopnow.order_service.client;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record CartResponse(
        String userId,
        List<CartItemData> items,
        BigDecimal totalAmount,
        Instant updatedAt
) {}
