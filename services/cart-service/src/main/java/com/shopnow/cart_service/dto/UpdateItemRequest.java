package com.shopnow.cart_service.dto;

import jakarta.validation.constraints.Min;

public record UpdateItemRequest(
        @Min(0) int quantity
) {}
