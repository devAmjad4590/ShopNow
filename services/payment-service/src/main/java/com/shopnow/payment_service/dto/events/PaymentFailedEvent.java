package com.shopnow.payment_service.dto.events;

public record PaymentFailedEvent(
        String type,
        String correlationId,
        Long orderId,
        Integer userId,
        String reason
) {
    public PaymentFailedEvent(String correlationId, Long orderId, Integer userId, String reason) {
        this("PAYMENT_FAILED", correlationId, orderId, userId, reason);
    }
}
