package com.shopnow.notification_service.dto.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PaymentEvent(
        String type,
        String correlationId,
        Long orderId,
        Integer userId,
        String reason
) {}
