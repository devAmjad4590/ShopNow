package com.shopnow.product_catalog.category;

import jakarta.validation.constraints.NotBlank;

public record CategoryRequest(
        @NotBlank String name,
        String description
) {
}
