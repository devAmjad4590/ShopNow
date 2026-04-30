package com.shopnow.order_service.event;

import java.time.Instant;

public record OrderConfirmedEvent(
        String type,
        String correlationId,
        Long orderId,
        Integer userId,
        Instant timestamp
) {}
