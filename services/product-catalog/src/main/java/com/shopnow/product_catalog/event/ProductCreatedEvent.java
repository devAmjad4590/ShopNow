package com.shopnow.product_catalog.event;

public record ProductCreatedEvent(
        String type,
        Long productId,
        String productName,
        int stock
) {}
