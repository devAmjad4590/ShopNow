package com.shopnow.order_service.order;

import com.shopnow.order_service.client.CartResponse;
import com.shopnow.order_service.client.CartServiceClient;
import com.shopnow.order_service.event.InventoryEvent;
import com.shopnow.order_service.event.PaymentEvent;
import com.shopnow.order_service.exception.EmptyCartException;
import com.shopnow.order_service.exception.OrderNotFoundException;
import com.shopnow.order_service.kafka.OrderEventProducer;
import com.shopnow.order_service.order.dto.CreateOrderRequest;
import com.shopnow.order_service.order.dto.OrderResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository orderRepository;
    private final CartServiceClient cartClient;
    private final OrderEventProducer producer;

    @Transactional
    public OrderResponse createOrder(Integer userId, CreateOrderRequest request) {
        CartResponse cart = cartClient.getCart(String.valueOf(userId));

        if (cart.items() == null || cart.items().isEmpty()) {
            throw new EmptyCartException();
        }

        Order order = Order.builder()
                .userId(userId)
                .correlationId(UUID.randomUUID().toString())
                .status(OrderStatus.PENDING)
                .shippingAddress(request.shippingAddress())
                .totalAmount(cart.totalAmount())
                .build();

        List<OrderItem> items = cart.items().stream().map(cartItem -> OrderItem.builder()
                .order(order)
                .productId(cartItem.productId())
                .productName(cartItem.productName())
                .price(cartItem.price())
                .quantity(cartItem.quantity())
                .build()
        ).toList();

        order.getItems().addAll(items);

        Order saved = orderRepository.save(order);

        try {
            cartClient.clearCart(String.valueOf(userId));
        } catch (Exception e) {
            log.warn("Failed to clear cart for user {}, continuing anyway", userId);
        }

        producer.publishOrderCreated(saved);

        return OrderResponse.from(saved);
    }

    public List<OrderResponse> getOrdersForUser(Integer userId) {
        return orderRepository.findByUserId(userId).stream()
                .map(OrderResponse::from)
                .toList();
    }

    public OrderResponse getOrder(Integer userId, Long orderId) {
        Order order = orderRepository.findById(orderId)
                .filter(o -> o.getUserId().equals(userId))
                .orElseThrow(() -> new OrderNotFoundException(orderId));
        return OrderResponse.from(order);
    }

    public OrderResponse getOrderById(Long orderId) {
        return orderRepository.findById(orderId)
                .map(OrderResponse::from)
                .orElseThrow(() -> new OrderNotFoundException(orderId));
    }

    @Transactional
    public void handleInventoryEvent(InventoryEvent event) {
        orderRepository.findByCorrelationId(event.correlationId()).ifPresent(order -> {
            if (isTerminal(order.getStatus())) return;

            switch (event.type()) {
                case "INVENTORY_RESERVED" -> order.setStatus(OrderStatus.INVENTORY_RESERVED);
                case "INVENTORY_RESERVATION_FAILED" -> order.setStatus(OrderStatus.FAILED);
                default -> log.warn("Unknown inventory event type: {}", event.type());
            }

            orderRepository.save(order);
        });
    }

    @Transactional
    public void handlePaymentEvent(PaymentEvent event) {
        orderRepository.findByCorrelationId(event.correlationId()).ifPresent(order -> {
            if (isTerminal(order.getStatus())) return;

            switch (event.type()) {
                case "PAYMENT_SUCCESS" -> {
                    order.setStatus(OrderStatus.CONFIRMED);
                    orderRepository.save(order);
                    producer.publishOrderConfirmed(order);
                }
                case "PAYMENT_FAILED" -> {
                    order.setStatus(OrderStatus.FAILED);
                    orderRepository.save(order);
                    producer.publishOrderCompensation(order, event.reason());
                }
                default -> log.warn("Unknown payment event type: {}", event.type());
            }
        });
    }

    private boolean isTerminal(OrderStatus status) {
        return status == OrderStatus.CONFIRMED || status == OrderStatus.FAILED || status == OrderStatus.CANCELLED;
    }
}
