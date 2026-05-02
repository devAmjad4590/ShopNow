package com.shopnow.inventory_service.service;

import com.shopnow.inventory_service.domain.Inventory;
import com.shopnow.inventory_service.domain.InventoryReservation;
import com.shopnow.inventory_service.domain.ReservationStatus;
import com.shopnow.inventory_service.dto.InventoryResponse;
import com.shopnow.inventory_service.event.OrderCreatedEvent;
import com.shopnow.inventory_service.exception.ProductNotFoundException;
import com.shopnow.inventory_service.repository.InventoryRepository;
import com.shopnow.inventory_service.repository.InventoryReservationRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class InventoryService {

    private final InventoryRepository inventoryRepository;
    private final InventoryReservationRepository reservationRepository;

    public record ReservationResult(boolean success, String failureReason) {}

    @Transactional
    public ReservationResult reserveStock(OrderCreatedEvent event) {
        // Validate all items before mutating any — all-or-nothing
        for (var item : event.items()) {
            var inventory = inventoryRepository.findByProductId(item.productId()).orElse(null);
            if (inventory == null || inventory.getAvailable() < item.quantity()) {
                String reason = inventory == null
                        ? "Product not found: " + item.productId()
                        : "Insufficient stock for product " + item.productId()
                          + " (available=" + inventory.getAvailable() + ", requested=" + item.quantity() + ")";
                log.warn("Reservation failed for order {}: {}", event.orderId(), reason);
                return new ReservationResult(false, reason);
            }
        }

        for (var item : event.items()) {
            Inventory inventory = inventoryRepository.findByProductId(item.productId()).orElseThrow();
            inventory.setAvailable(inventory.getAvailable() - item.quantity());
            inventory.setReserved(inventory.getReserved() + item.quantity());
            inventoryRepository.save(inventory);

            InventoryReservation reservation = InventoryReservation.builder()
                    .orderId(event.orderId())
                    .correlationId(event.correlationId())
                    .productId(item.productId())
                    .quantity(item.quantity())
                    .status(ReservationStatus.RESERVED)
                    .build();
            reservationRepository.save(reservation);
        }

        return new ReservationResult(true, null);
    }

    @Transactional
    public void releaseReservation(String correlationId) {
        List<InventoryReservation> reservations =
                reservationRepository.findByCorrelationIdAndStatus(correlationId, ReservationStatus.RESERVED);

        for (InventoryReservation reservation : reservations) {
            Inventory inventory = inventoryRepository.findByProductId(reservation.getProductId())
                    .orElseThrow(() -> new ProductNotFoundException(reservation.getProductId()));
            inventory.setAvailable(inventory.getAvailable() + reservation.getQuantity());
            inventory.setReserved(inventory.getReserved() - reservation.getQuantity());
            inventoryRepository.save(inventory);

            reservation.setStatus(ReservationStatus.RELEASED);
            reservationRepository.save(reservation);
        }
    }

    @Transactional
    public void confirmReservation(String correlationId) {
        List<InventoryReservation> reservations =
                reservationRepository.findByCorrelationIdAndStatus(correlationId, ReservationStatus.RESERVED);

        for (InventoryReservation reservation : reservations) {
            Inventory inventory = inventoryRepository.findByProductId(reservation.getProductId())
                    .orElseThrow(() -> new ProductNotFoundException(reservation.getProductId()));
            // Stock already deducted from available at reservation time; just clear the reserved hold
            inventory.setReserved(inventory.getReserved() - reservation.getQuantity());
            inventoryRepository.save(inventory);

            reservation.setStatus(ReservationStatus.CONFIRMED);
            reservationRepository.save(reservation);
        }
    }

    @Transactional
    public Inventory seedStock(Long productId, String productName, int quantity) {
        return inventoryRepository.findByProductId(productId)
                .map(existing -> {
                    existing.setTotalStock(existing.getTotalStock() + quantity);
                    existing.setAvailable(existing.getAvailable() + quantity);
                    return inventoryRepository.save(existing);
                })
                .orElseGet(() -> inventoryRepository.save(
                        Inventory.builder()
                                .productId(productId)
                                .productName(productName)
                                .totalStock(quantity)
                                .available(quantity)
                                .reserved(0)
                                .build()
                ));
    }

    public Inventory getStock(Long productId) {
        return inventoryRepository.findByProductId(productId)
                .orElseThrow(() -> new ProductNotFoundException(productId));
    }

    public List<Inventory> getAllStock() {
        return inventoryRepository.findAll();
    }

    @Transactional
    public Inventory adjustStock(Long productId, int quantityDelta) {
        Inventory inventory = inventoryRepository.findByProductId(productId)
                .orElseThrow(() -> new ProductNotFoundException(productId));

        int newAvailable = inventory.getAvailable() + quantityDelta;
        if (newAvailable < 0) {
            throw new IllegalStateException("Adjustment would put available stock below zero");
        }
        if (newAvailable < inventory.getReserved()) {
            throw new IllegalStateException("Adjustment would make available stock less than reserved");
        }

        inventory.setTotalStock(inventory.getTotalStock() + quantityDelta);
        inventory.setAvailable(newAvailable);
        return inventoryRepository.save(inventory);
    }

    public static InventoryResponse toResponse(Inventory inventory) {
        return new InventoryResponse(
                inventory.getProductId(),
                inventory.getProductName(),
                inventory.getTotalStock(),
                inventory.getAvailable(),
                inventory.getReserved()
        );
    }
}
