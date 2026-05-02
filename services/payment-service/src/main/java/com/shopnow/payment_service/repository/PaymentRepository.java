package com.shopnow.payment_service.repository;

import com.shopnow.payment_service.entity.Payment;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface PaymentRepository extends JpaRepository<Payment, UUID> {
    boolean existsByCorrelationId(String correlationId);
    Optional<Payment> findByOrderId(Long orderId);
}
