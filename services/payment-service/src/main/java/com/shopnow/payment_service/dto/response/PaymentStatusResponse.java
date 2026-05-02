package com.shopnow.payment_service.dto.response;

import com.shopnow.payment_service.entity.PaymentStatus;

import java.time.Instant;

public record PaymentStatusResponse(
        Long orderId,
        PaymentStatus status,
        String stripePaymentIntentId,
        String failureReason,
        Instant createdAt,
        Instant updatedAt
) {}
