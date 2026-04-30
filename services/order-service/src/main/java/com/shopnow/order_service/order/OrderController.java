package com.shopnow.order_service.order;

import com.shopnow.order_service.order.dto.CreateOrderRequest;
import com.shopnow.order_service.order.dto.OrderResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/orders")
@RequiredArgsConstructor
public class OrderController {

    private final OrderService orderService;

    @PostMapping
    public ResponseEntity<OrderResponse> createOrder(
            @RequestHeader("X-User-Id") Integer userId,
            @RequestBody @Valid CreateOrderRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(orderService.createOrder(userId, request));
    }

    @GetMapping
    public ResponseEntity<List<OrderResponse>> listOrders(
            @RequestHeader("X-User-Id") Integer userId) {
        return ResponseEntity.ok(orderService.getOrdersForUser(userId));
    }

    @GetMapping("/{orderId}")
    public ResponseEntity<OrderResponse> getOrder(
            @RequestHeader("X-User-Id") Integer userId,
            @PathVariable Long orderId) {
        return ResponseEntity.ok(orderService.getOrder(userId, orderId));
    }
}
