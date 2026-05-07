package com.shopnow.notification_service.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shopnow.notification_service.dto.events.PaymentEvent;
import com.shopnow.notification_service.service.EmailService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class PaymentEventConsumer {

    private final EmailService emailService;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "payment-events", groupId = "notification-service")
    public void handlePaymentEvent(String payload) {
        try {
            PaymentEvent event = objectMapper.readValue(payload, PaymentEvent.class);
            if ("PAYMENT_SUCCESS".equals(event.type())) {
                log.info("Sending payment receipt for orderId={}", event.orderId());
                emailService.sendPaymentReceipt(event);
            }
        } catch (Exception e) {
            log.error("Failed to process payment event: {}", payload, e);
        }
    }
}
