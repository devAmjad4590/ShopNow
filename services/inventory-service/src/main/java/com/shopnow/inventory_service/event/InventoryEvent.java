package com.shopnow.inventory_service.event;

public record InventoryEvent(String type, String correlationId, String reason) {}
