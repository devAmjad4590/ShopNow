package com.shopnow.notification_service.service;

import com.shopnow.notification_service.client.AuthServiceClient;
import com.shopnow.notification_service.client.UserInfoResponse;
import com.shopnow.notification_service.dto.events.OrderEvent;
import com.shopnow.notification_service.dto.events.PaymentEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class EmailService {

    private final JavaMailSender mailSender;
    private final AuthServiceClient authServiceClient;

    @Value("${spring.mail.from:noreply@shopnow.com}")
    private String fromAddress;

    public void sendOrderConfirmed(OrderEvent event) {
        UserInfoResponse user = authServiceClient.getUserById(event.userId());
        if (user == null) {
            log.warn("Cannot send order confirmed email — user not found for userId={}", event.userId());
            return;
        }
        send(
                user.email(),
                "Your ShopNow Order #" + event.orderId() + " is Confirmed!",
                "Hi " + user.firstName() + ",\n\n" +
                "Great news! Your order #" + event.orderId() + " has been confirmed.\n\n" +
                "Thank you for shopping with ShopNow!"
        );
    }

    public void sendOrderFailed(OrderEvent event) {
        UserInfoResponse user = authServiceClient.getUserById(event.userId());
        if (user == null) {
            log.warn("Cannot send order failed email — user not found for userId={}", event.userId());
            return;
        }
        send(
                user.email(),
                "ShopNow Order #" + event.orderId() + " Could Not Be Processed",
                "Hi " + user.firstName() + ",\n\n" +
                "Unfortunately, your order #" + event.orderId() + " could not be processed.\n" +
                "No charges were made. Please try again.\n\n" +
                "ShopNow Support"
        );
    }

    public void sendPaymentReceipt(PaymentEvent event) {
        UserInfoResponse user = authServiceClient.getUserById(event.userId());
        if (user == null) {
            log.warn("Cannot send payment receipt — user not found for userId={}", event.userId());
            return;
        }
        send(
                user.email(),
                "Payment Receipt for Order #" + event.orderId(),
                "Hi " + user.firstName() + ",\n\nYour payment for order #" + event.orderId() +
                " was successfully processed.\n\nThank you for shopping with ShopNow!"
        );
    }

    private void send(String to, String subject, String body) {
        try {
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom(fromAddress);
            message.setTo(to);
            message.setSubject(subject);
            message.setText(body);
            mailSender.send(message);
            log.info("Email sent to {}: {}", to, subject);
        } catch (Exception e) {
            log.error("Failed to send email to {}: {}", to, e.getMessage());
        }
    }
}
