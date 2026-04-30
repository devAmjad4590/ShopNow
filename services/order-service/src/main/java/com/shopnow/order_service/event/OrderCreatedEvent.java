package com.shopnow.order_service.event;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderCreatedEvent(
        String type,
        String correlationId,
        Long orderId,
        Integer userId,
        List<OrderItemPayload> items,
        BigDecimal totalAmount,
        Instant timestamp
) {}
