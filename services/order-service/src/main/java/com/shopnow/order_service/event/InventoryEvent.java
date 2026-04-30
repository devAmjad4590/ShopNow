package com.shopnow.order_service.event;

public record InventoryEvent(String type, String correlationId, String reason) {}
