package com.shopnow.product_catalog.exception;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.stream.Collectors;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(ResourceNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ErrorResponse.builder()
                .error("NOT_FOUND")
                .message(ex.getMessage())
                .timestamp(System.currentTimeMillis())
                .build());
    }

    @ExceptionHandler(CategoryInUseException.class)
    public ResponseEntity<ErrorResponse> handleCategoryInUse(CategoryInUseException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(ErrorResponse.builder()
                .error("CONFLICT")
                .message(ex.getMessage())
                .timestamp(System.currentTimeMillis())
                .build());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {
        String fields = ex.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + ": " + f.getDefaultMessage())
                .collect(Collectors.joining(", "));
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(ErrorResponse.builder()
                .error("VALIDATION_ERROR")
                .message(fields)
                .timestamp(System.currentTimeMillis())
                .build());
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ErrorResponse> handleResponseStatus(ResponseStatusException ex) {
        return ResponseEntity.status(ex.getStatusCode()).body(ErrorResponse.builder()
                .error(ex.getStatusCode().toString())
                .message(ex.getReason())
                .timestamp(System.currentTimeMillis())
                .build());
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<ErrorResponse> handleNoResource(NoResourceFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ErrorResponse.builder()
                .error("NOT_FOUND")
                .message(ex.getMessage())
                .timestamp(System.currentTimeMillis())
                .build());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneric(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(ErrorResponse.builder()
                .error("INTERNAL_ERROR")
                .message(ex.getMessage())
                .timestamp(System.currentTimeMillis())
                .build());
    }
}
