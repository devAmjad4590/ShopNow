package com.shopnow.payment_service.dto.events;

public record PaymentSuccessEvent(
        String type,
        String correlationId,
        Long orderId,
        Integer userId,
        String stripePaymentIntentId
) {
    public PaymentSuccessEvent(String correlationId, Long orderId, Integer userId, String stripePaymentIntentId) {
        this("PAYMENT_SUCCESS", correlationId, orderId, userId, stripePaymentIntentId);
    }
}
