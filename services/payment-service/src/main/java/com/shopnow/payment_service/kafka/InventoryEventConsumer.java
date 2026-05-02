package com.shopnow.payment_service.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shopnow.payment_service.dto.events.InventoryReservedEvent;
import com.shopnow.payment_service.service.PaymentService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class InventoryEventConsumer {

    private final PaymentService paymentService;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "inventory-events", groupId = "payment-service")
    public void handleInventoryEvent(String payload) {
        try {
            InventoryReservedEvent event = objectMapper.readValue(payload, InventoryReservedEvent.class);
            if (!"INVENTORY_RESERVED".equals(event.type())) {
                return;
            }
            log.info("Received INVENTORY_RESERVED orderId={} correlationId={}", event.orderId(), event.correlationId());
            paymentService.processInventoryReservedEvent(event);
        } catch (Exception e) {
            log.error("Failed to process inventory event: {}", payload, e);
        }
    }
}
