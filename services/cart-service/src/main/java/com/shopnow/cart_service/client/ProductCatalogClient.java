package com.shopnow.cart_service.client;

import com.shopnow.cart_service.exception.CatalogUnavailableException;
import com.shopnow.cart_service.exception.ProductNotFoundException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class ProductCatalogClient {

    private final RestClient restClient;

    public ProductCatalogClient(@Value("${product-catalog.base-url}") String baseUrl) {
        this.restClient = RestClient.builder().baseUrl(baseUrl).build();
    }

    public ProductResponse getProduct(Long productId) {
        try {
            return restClient.get()
                    .uri("/internal/products/{id}", productId)
                    .retrieve()
                    .onStatus(HttpStatusCode::is4xxClientError, (req, res) -> {
                        throw new ProductNotFoundException(productId);
                    })
                    .body(ProductResponse.class);
        } catch (ProductNotFoundException e) {
            throw e;
        } catch (RestClientException e) {
            throw new CatalogUnavailableException();
        }
    }
}
