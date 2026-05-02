package com.shopnow.inventory_service.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shopnow.inventory_service.event.InventoryEvent;
import com.shopnow.inventory_service.event.OrderCreatedEvent;
import com.shopnow.inventory_service.event.PaymentEvent;
import com.shopnow.inventory_service.service.InventoryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class SagaEventHandler {

    private static final String INVENTORY_EVENTS = "inventory-events";

    private final InventoryService inventoryService;
    private final KafkaTemplate<String, Object> kafkaTemplate;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "order-events", groupId = "inventory-service")
    public void handleOrderCreated(String payload) {
        try {
            OrderCreatedEvent event = objectMapper.readValue(payload, OrderCreatedEvent.class);
            if (!"ORDER_CREATED".equals(event.type())) {
                return;
            }
            log.info("Received ORDER_CREATED for orderId={} correlationId={}", event.orderId(), event.correlationId());

            InventoryService.ReservationResult result = inventoryService.reserveStock(event);

            if (result.success()) {
                kafkaTemplate.send(INVENTORY_EVENTS,
                        new InventoryEvent("INVENTORY_RESERVED", event.correlationId(), null,
                                event.orderId(), event.userId(), event.totalAmount()));
                log.info("Stock reserved for correlationId={}", event.correlationId());
            } else {
                kafkaTemplate.send(INVENTORY_EVENTS,
                        new InventoryEvent("INVENTORY_RESERVATION_FAILED", event.correlationId(), result.failureReason(),
                                event.orderId(), event.userId(), event.totalAmount()));
                log.warn("Reservation failed for correlationId={}: {}", event.correlationId(), result.failureReason());
            }
        } catch (Exception e) {
            log.error("Failed to process order event: {}", payload, e);
        }
    }

    @KafkaListener(topics = "payment-events", groupId = "inventory-service")
    public void handlePaymentEvent(String payload) {
        try {
            PaymentEvent event = objectMapper.readValue(payload, PaymentEvent.class);
            log.info("Received payment event type={} correlationId={}", event.type(), event.correlationId());

            switch (event.type()) {
                case "PAYMENT_FAILED" -> {
                    inventoryService.releaseReservation(event.correlationId());
                    log.info("Reservation released (compensation) for correlationId={}", event.correlationId());
                }
                case "PAYMENT_SUCCESS" -> {
                    inventoryService.confirmReservation(event.correlationId());
                    log.info("Reservation confirmed for correlationId={}", event.correlationId());
                }
                default -> log.debug("Ignoring payment event type={}", event.type());
            }
        } catch (Exception e) {
            log.error("Failed to process payment event: {}", payload, e);
        }
    }
}
