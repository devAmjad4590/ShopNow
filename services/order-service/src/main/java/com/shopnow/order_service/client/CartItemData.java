package com.shopnow.order_service.client;

import java.math.BigDecimal;

public record CartItemData(
        Long productId,
        String productName,
        BigDecimal price,
        int quantity,
        String imageUrl
) {}
