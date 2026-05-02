package com.shopnow.payment_service.service;

import com.stripe.exception.StripeException;
import com.stripe.model.PaymentIntent;
import com.stripe.net.RequestOptions;
import com.stripe.param.PaymentIntentCreateParams;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;

@Slf4j
@Service
@RequiredArgsConstructor
public class StripePaymentService {

    private final CircuitBreaker stripeCircuitBreaker;

    public String charge(BigDecimal amount, String correlationId) throws StripeException {
        try {
            return stripeCircuitBreaker.executeCheckedSupplier(() -> doCharge(amount, correlationId));
        } catch (StripeException e) {
            throw e;
        } catch (Throwable e) {
            throw new RuntimeException(e);
        }
    }

    private String doCharge(BigDecimal amount, String correlationId) throws StripeException {
        long cents = amount.multiply(BigDecimal.valueOf(100)).longValue();

        PaymentIntentCreateParams params = PaymentIntentCreateParams.builder()
                .setAmount(cents)
                .setCurrency("usd")
                .setPaymentMethod("pm_card_visa")
                .setConfirm(true)
                .setAutomaticPaymentMethods(
                        PaymentIntentCreateParams.AutomaticPaymentMethods.builder()
                                .setEnabled(true)
                                .setAllowRedirects(PaymentIntentCreateParams.AutomaticPaymentMethods.AllowRedirects.NEVER)
                                .build()
                )
                .build();

        RequestOptions requestOptions = RequestOptions.builder()
                .setIdempotencyKey(correlationId)
                .build();

        PaymentIntent intent = PaymentIntent.create(params, requestOptions);
        log.info("Stripe PaymentIntent created id={} status={}", intent.getId(), intent.getStatus());
        return intent.getId();
    }

    public boolean isCircuitOpen() {
        return stripeCircuitBreaker.getState() == CircuitBreaker.State.OPEN;
    }
}
