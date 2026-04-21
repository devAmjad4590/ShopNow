package com.shopnow.product_catalog.category;

import java.time.Instant;

public record CategoryResponse(
        Integer id,
        String name,
        String description,
        Instant createdAt
) {
}
