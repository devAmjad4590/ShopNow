package com.shopnow.order_service.event;

public record PaymentEvent(String type, String correlationId, String reason) {}
