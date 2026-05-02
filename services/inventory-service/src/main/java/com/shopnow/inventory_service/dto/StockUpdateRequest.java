package com.shopnow.inventory_service.dto;

import jakarta.validation.constraints.NotNull;

public record StockUpdateRequest(@NotNull int quantityDelta) {}
