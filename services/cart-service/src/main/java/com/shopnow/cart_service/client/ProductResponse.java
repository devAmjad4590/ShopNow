package com.shopnow.cart_service.client;

import java.math.BigDecimal;

public record ProductResponse(
        Integer id,
        String name,
        String description,
        BigDecimal price,
        String imageUrl,
        Integer categoryId,
        String categoryName,
        Integer stock,
        java.time.Instant createdAt,
        java.time.Instant updatedAt
) {}
