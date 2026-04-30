package com.shopnow.order_service.order.dto;

import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
        @NotBlank(message = "shippingAddress is required")
        String shippingAddress
) {}
