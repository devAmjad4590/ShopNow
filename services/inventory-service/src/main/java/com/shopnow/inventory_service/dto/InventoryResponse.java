package com.shopnow.inventory_service.dto;

public record InventoryResponse(
        Long productId,
        String productName,
        int totalStock,
        int available,
        int reserved
) {}
