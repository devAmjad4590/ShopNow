package com.shopnow.payment_service.controller;

import com.shopnow.payment_service.dto.response.PaymentStatusResponse;
import com.shopnow.payment_service.service.PaymentService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/payments")
@RequiredArgsConstructor
public class PaymentSimulationController {

    private final PaymentService paymentService;

    @PostMapping("/simulate-failure/next-for-user/{userId}")
    public ResponseEntity<Void> simulateFailureForUser(@PathVariable Integer userId) {
        paymentService.addForcedFailureForUser(userId);
        return ResponseEntity.ok().build();
    }

    @GetMapping("/{orderId}")
    public ResponseEntity<PaymentStatusResponse> getPaymentStatus(@PathVariable Long orderId) {
        return ResponseEntity.ok(paymentService.getPaymentStatus(orderId));
    }
}
