package com.shopnow.cart_service.cart;

import com.shopnow.cart_service.client.ProductCatalogClient;
import com.shopnow.cart_service.client.ProductResponse;
import com.shopnow.cart_service.dto.AddItemRequest;
import com.shopnow.cart_service.dto.CartResponse;
import com.shopnow.cart_service.dto.UpdateItemRequest;
import com.shopnow.cart_service.exception.ProductNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Optional;

@Service
@RequiredArgsConstructor
public class CartService {

    private final CartRepository cartRepository;
    private final ProductCatalogClient productCatalogClient;

    public CartResponse getCart(String userId) {
        Cart cart = cartRepository.findByUserId(userId)
                .orElse(emptyCart(userId));
        return CartResponse.from(cart);
    }

    public CartResponse addItem(String userId, AddItemRequest req) {
        ProductResponse product = productCatalogClient.getProduct(req.productId());

        Cart cart = cartRepository.findByUserId(userId)
                .orElse(emptyCart(userId));

        Optional<CartItem> existing = cart.getItems().stream()
                .filter(i -> i.getProductId().equals(req.productId()))
                .findFirst();

        if (existing.isPresent()) {
            existing.get().setQuantity(existing.get().getQuantity() + req.quantity());
        } else {
            cart.getItems().add(CartItem.builder()
                    .productId(req.productId())
                    .productName(product.name())
                    .price(product.price())
                    .quantity(req.quantity())
                    .imageUrl(product.imageUrl())
                    .build());
        }

        cart.setUpdatedAt(Instant.now());
        cartRepository.save(cart);
        return CartResponse.from(cart);
    }

    public CartResponse updateItemQty(String userId, Long productId, UpdateItemRequest req) {
        Cart cart = cartRepository.findByUserId(userId)
                .orElse(emptyCart(userId));

        boolean found = cart.getItems().stream()
                .anyMatch(i -> i.getProductId().equals(productId));
        if (!found) throw new ProductNotFoundException(productId);

        if (req.quantity() == 0) {
            cart.getItems().removeIf(i -> i.getProductId().equals(productId));
        } else {
            cart.getItems().stream()
                    .filter(i -> i.getProductId().equals(productId))
                    .findFirst()
                    .ifPresent(i -> i.setQuantity(req.quantity()));
        }

        cart.setUpdatedAt(Instant.now());
        cartRepository.save(cart);
        return CartResponse.from(cart);
    }

    public CartResponse removeItem(String userId, Long productId) {
        Cart cart = cartRepository.findByUserId(userId)
                .orElse(emptyCart(userId));

        cart.getItems().removeIf(i -> i.getProductId().equals(productId));
        cart.setUpdatedAt(Instant.now());
        cartRepository.save(cart);
        return CartResponse.from(cart);
    }

    public void clearCart(String userId) {
        cartRepository.deleteByUserId(userId);
    }

    private Cart emptyCart(String userId) {
        return Cart.builder()
                .userId(userId)
                .items(new ArrayList<>())
                .updatedAt(Instant.now())
                .build();
    }
}
