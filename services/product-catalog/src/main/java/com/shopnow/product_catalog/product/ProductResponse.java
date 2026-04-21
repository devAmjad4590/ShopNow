package com.shopnow.product_catalog.product;

import java.math.BigDecimal;
import java.time.Instant;

public record ProductResponse(
        Integer id,
        String name,
        String description,
        BigDecimal price,
        String imageUrl,
        Integer categoryId,
        String categoryName,
        Integer stock,
        Instant createdAt,
        Instant updatedAt
) {
}
