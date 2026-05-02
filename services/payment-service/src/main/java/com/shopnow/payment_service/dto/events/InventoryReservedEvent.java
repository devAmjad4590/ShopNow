package com.shopnow.payment_service.dto.events;

import java.math.BigDecimal;

public record InventoryReservedEvent(
        String type,
        String correlationId,
        String reason,
        Long orderId,
        Integer userId,
        BigDecimal totalAmount
) {}
