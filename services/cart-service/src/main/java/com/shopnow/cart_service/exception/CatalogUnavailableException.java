package com.shopnow.cart_service.exception;

public class CatalogUnavailableException extends RuntimeException {
    public CatalogUnavailableException() {
        super("Product catalog service is unavailable");
    }
}
