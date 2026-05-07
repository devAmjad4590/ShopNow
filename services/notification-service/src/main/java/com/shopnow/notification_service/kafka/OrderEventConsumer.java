package com.shopnow.notification_service.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shopnow.notification_service.dto.events.OrderEvent;
import com.shopnow.notification_service.service.EmailService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class OrderEventConsumer {

    private final EmailService emailService;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "order-events", groupId = "notification-service")
    public void handleOrderEvent(String payload) {
        try {
            OrderEvent event = objectMapper.readValue(payload, OrderEvent.class);
            if ("ORDER_CONFIRMED".equals(event.type())) {
                log.info("Sending confirmation email for orderId={}", event.orderId());
                emailService.sendOrderConfirmed(event);
            } else if ("ORDER_COMPENSATION".equals(event.type())) {
                log.info("Sending failure email for orderId={}", event.orderId());
                emailService.sendOrderFailed(event);
            }
        } catch (Exception e) {
            log.error("Failed to process order event: {}", payload, e);
        }
    }
}
