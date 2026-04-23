package com.shopnow.cart_service.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record AddItemRequest(
        @NotNull Long productId,
        @Min(1) int quantity
) {}
