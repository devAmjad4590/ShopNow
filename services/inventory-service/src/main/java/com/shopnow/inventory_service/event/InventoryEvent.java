package com.shopnow.inventory_service.event;

import java.math.BigDecimal;

public record InventoryEvent(
        String type,
        String correlationId,
        String reason,
        Long orderId,
        Integer userId,
        BigDecimal totalAmount
) {}
