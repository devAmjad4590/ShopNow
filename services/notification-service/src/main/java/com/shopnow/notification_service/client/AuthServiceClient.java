package com.shopnow.notification_service.client;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Slf4j
@Component
public class AuthServiceClient {

    private final RestTemplate restTemplate;
    private final String authServiceUrl;

    public AuthServiceClient(RestTemplate restTemplate,
                             @Value("${auth-service.base-url}") String authServiceUrl) {
        this.restTemplate = restTemplate;
        this.authServiceUrl = authServiceUrl;
    }

    public UserInfoResponse getUserById(Integer userId) {
        try {
            return restTemplate.getForObject(authServiceUrl + "/internal/users/" + userId, UserInfoResponse.class);
        } catch (Exception e) {
            log.error("Failed to fetch user info for userId={}: {}", userId, e.getMessage());
            return null;
        }
    }
}
