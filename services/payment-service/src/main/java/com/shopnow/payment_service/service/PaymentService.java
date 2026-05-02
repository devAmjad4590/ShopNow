package com.shopnow.payment_service.service;

import com.shopnow.payment_service.dto.events.InventoryReservedEvent;
import com.shopnow.payment_service.dto.events.PaymentFailedEvent;
import com.shopnow.payment_service.dto.events.PaymentSuccessEvent;
import com.shopnow.payment_service.dto.response.PaymentStatusResponse;
import com.shopnow.payment_service.entity.Payment;
import com.shopnow.payment_service.entity.PaymentStatus;
import com.shopnow.payment_service.exception.PaymentNotFoundException;
import com.shopnow.payment_service.repository.PaymentRepository;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Slf4j
@Service
@RequiredArgsConstructor
public class PaymentService {

    private static final String PAYMENT_EVENTS = "payment-events";

    private final PaymentRepository paymentRepository;
    private final StripePaymentService stripePaymentService;
    private final KafkaTemplate<String, Object> kafkaTemplate;

    private final Set<Long> forcedFailureOrders = ConcurrentHashMap.newKeySet();

    public void processInventoryReservedEvent(InventoryReservedEvent event) {
        if (paymentRepository.existsByCorrelationId(event.correlationId())) {
            log.info("Duplicate event — skipping correlationId={}", event.correlationId());
            return;
        }

        Payment payment = Payment.builder()
                .orderId(event.orderId())
                .userId(event.userId())
                .correlationId(event.correlationId())
                .amount(event.totalAmount())
                .currency("usd")
                .status(PaymentStatus.PENDING)
                .build();
        paymentRepository.save(payment);
        log.info("Payment record created for orderId={} correlationId={}", event.orderId(), event.correlationId());

        if (forcedFailureOrders.remove(event.orderId())) {
            log.info("Forced failure triggered for orderId={}", event.orderId());
            fail(payment, "Forced failure");
            return;
        }

        if (stripePaymentService.isCircuitOpen()) {
            log.warn("Stripe circuit open — failing payment for orderId={}", event.orderId());
            fail(payment, "Stripe unavailable");
            return;
        }

        try {
            String intentId = stripePaymentService.charge(event.totalAmount(), event.correlationId());
            payment.setStripePaymentIntentId(intentId);
            payment.setStatus(PaymentStatus.SUCCESS);
            paymentRepository.save(payment);
            log.info("Payment succeeded orderId={} intentId={}", event.orderId(), intentId);

            kafkaTemplate.send(PAYMENT_EVENTS,
                    new PaymentSuccessEvent(event.correlationId(), event.orderId(), event.userId(), intentId));

        } catch (CallNotPermittedException e) {
            log.warn("Stripe circuit rejected call for orderId={}", event.orderId());
            fail(payment, "Stripe unavailable");
        } catch (Exception e) {
            log.error("Stripe charge failed for orderId={}: {}", event.orderId(), e.getMessage());
            fail(payment, e.getMessage());
        }
    }

    public void addForcedFailure(Long orderId) {
        forcedFailureOrders.add(orderId);
        log.info("Forced failure registered for orderId={}", orderId);
    }

    public PaymentStatusResponse getPaymentStatus(Long orderId) {
        Payment payment = paymentRepository.findByOrderId(orderId)
                .orElseThrow(() -> new PaymentNotFoundException(orderId));
        return toResponse(payment);
    }

    private void fail(Payment payment, String reason) {
        payment.setStatus(PaymentStatus.FAILED);
        payment.setFailureReason(reason);
        paymentRepository.save(payment);

        kafkaTemplate.send(PAYMENT_EVENTS,
                new PaymentFailedEvent(payment.getCorrelationId(), payment.getOrderId(), payment.getUserId(), reason));
        log.info("Payment failed orderId={} reason={}", payment.getOrderId(), reason);
    }

    private PaymentStatusResponse toResponse(Payment p) {
        return new PaymentStatusResponse(
                p.getOrderId(),
                p.getStatus(),
                p.getStripePaymentIntentId(),
                p.getFailureReason(),
                p.getCreatedAt(),
                p.getUpdatedAt()
        );
    }
}
