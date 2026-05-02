package com.shopnow.inventory_service.event;

public record PaymentEvent(String type, String correlationId, String reason) {}
