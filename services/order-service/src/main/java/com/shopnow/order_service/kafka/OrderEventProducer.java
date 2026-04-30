package com.shopnow.order_service.kafka;

import com.shopnow.order_service.event.OrderCompensationEvent;
import com.shopnow.order_service.event.OrderConfirmedEvent;
import com.shopnow.order_service.event.OrderCreatedEvent;
import com.shopnow.order_service.event.OrderItemPayload;
import com.shopnow.order_service.order.Order;
import lombok.RequiredArgsConstructor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

import java.time.Instant;

@Service
@RequiredArgsConstructor
public class OrderEventProducer {

    private static final String TOPIC = "order-events";

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public void publishOrderCreated(Order order) {
        var items = order.getItems().stream()
                .map(i -> new OrderItemPayload(i.getProductId(), i.getQuantity(), i.getPrice()))
                .toList();
        var event = new OrderCreatedEvent(
                "ORDER_CREATED",
                order.getCorrelationId(),
                order.getId(),
                order.getUserId(),
                items,
                order.getTotalAmount(),
                Instant.now()
        );
        kafkaTemplate.send(TOPIC, order.getCorrelationId(), event);
    }

    public void publishOrderConfirmed(Order order) {
        var event = new OrderConfirmedEvent(
                "ORDER_CONFIRMED",
                order.getCorrelationId(),
                order.getId(),
                order.getUserId(),
                Instant.now()
        );
        kafkaTemplate.send(TOPIC, order.getCorrelationId(), event);
    }

    public void publishOrderCompensation(Order order, String reason) {
        var event = new OrderCompensationEvent(
                "ORDER_COMPENSATION",
                order.getCorrelationId(),
                order.getId(),
                order.getUserId(),
                reason,
                Instant.now()
        );
        kafkaTemplate.send(TOPIC, order.getCorrelationId(), event);
    }
}
