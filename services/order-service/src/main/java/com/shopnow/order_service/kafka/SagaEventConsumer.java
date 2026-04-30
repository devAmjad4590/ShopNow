package com.shopnow.order_service.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shopnow.order_service.event.InventoryEvent;
import com.shopnow.order_service.event.PaymentEvent;
import com.shopnow.order_service.order.OrderService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class SagaEventConsumer {

    private final OrderService orderService;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "inventory-events", groupId = "order-service")
    public void handleInventoryEvent(String payload) {
        try {
            InventoryEvent event = objectMapper.readValue(payload, InventoryEvent.class);
            orderService.handleInventoryEvent(event);
        } catch (Exception e) {
            log.error("Failed to process inventory event: {}", payload, e);
        }
    }

    @KafkaListener(topics = "payment-events", groupId = "order-service")
    public void handlePaymentEvent(String payload) {
        try {
            PaymentEvent event = objectMapper.readValue(payload, PaymentEvent.class);
            orderService.handlePaymentEvent(event);
        } catch (Exception e) {
            log.error("Failed to process payment event: {}", payload, e);
        }
    }
}
