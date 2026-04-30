package com.shopnow.order_service.client;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class CartServiceClient {

    private final RestClient restClient;

    public CartServiceClient(@Value("${cart-service.base-url}") String baseUrl) {
        this.restClient = RestClient.builder().baseUrl(baseUrl).build();
    }

    public CartResponse getCart(String userId) {
        return restClient.get()
                .uri("/internal/cart/{userId}", userId)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    throw new RestClientException("Failed to fetch cart for user " + userId);
                })
                .body(CartResponse.class);
    }

    public void clearCart(String userId) {
        restClient.delete()
                .uri("/cart")
                .header("X-User-Id", userId)
                .retrieve()
                .toBodilessEntity();
    }
}
