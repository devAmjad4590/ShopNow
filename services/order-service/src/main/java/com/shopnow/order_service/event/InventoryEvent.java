package com.shopnow.order_service.event;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record InventoryEvent(String type, String correlationId, String reason) {}
