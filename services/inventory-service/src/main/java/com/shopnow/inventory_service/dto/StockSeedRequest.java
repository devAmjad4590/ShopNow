package com.shopnow.inventory_service.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record StockSeedRequest(
        @NotNull Long productId,
        @NotBlank String productName,
        @Min(0) int quantity
) {}
