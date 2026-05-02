package com.shopnow.inventory_service.event;

import java.math.BigDecimal;

public record OrderItemPayload(Long productId, int quantity, BigDecimal price) {}
