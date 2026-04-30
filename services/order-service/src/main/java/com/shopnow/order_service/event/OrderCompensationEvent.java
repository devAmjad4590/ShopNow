package com.shopnow.order_service.event;

import java.time.Instant;

public record OrderCompensationEvent(
        String type,
        String correlationId,
        Long orderId,
        Integer userId,
        String reason,
        Instant timestamp
) {}
