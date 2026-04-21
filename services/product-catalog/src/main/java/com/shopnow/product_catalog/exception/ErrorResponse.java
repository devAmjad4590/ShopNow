package com.shopnow.product_catalog.exception;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class ErrorResponse {
    private String error;
    private String message;
    private long timestamp;
}
