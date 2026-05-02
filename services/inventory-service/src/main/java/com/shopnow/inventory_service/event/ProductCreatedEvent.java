package com.shopnow.inventory_service.event;

public record ProductCreatedEvent(
        String type,
        Long productId,
        String productName,
        int stock
) {}
