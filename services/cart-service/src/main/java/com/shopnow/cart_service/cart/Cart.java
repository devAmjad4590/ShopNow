package com.shopnow.cart_service.cart;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Cart {
    private String userId;

    @Builder.Default
    private List<CartItem> items = new ArrayList<>();

    private Instant updatedAt;
}
