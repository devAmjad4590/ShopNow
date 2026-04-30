package com.shopnow.order_service.exception;

public class EmptyCartException extends RuntimeException {
    public EmptyCartException() {
        super("Cannot create order from an empty cart");
    }
}
