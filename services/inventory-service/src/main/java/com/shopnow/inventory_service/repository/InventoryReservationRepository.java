package com.shopnow.inventory_service.repository;

import com.shopnow.inventory_service.domain.InventoryReservation;
import com.shopnow.inventory_service.domain.ReservationStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface InventoryReservationRepository extends JpaRepository<InventoryReservation, Long> {
    List<InventoryReservation> findByCorrelationIdAndStatus(String correlationId, ReservationStatus status);
    boolean existsByOrderIdAndProductId(Long orderId, Long productId);
}
