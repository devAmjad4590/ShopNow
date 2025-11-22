package com.shopnow.auth_service.config;

import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

// needed cuz spring security protect routes by default
@Configuration
@RequiredArgsConstructor
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http){
http.
        csrf(AbstractHttpConfigurer::disable). // to allow public post req to get through
authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/v1/auth/**").permitAll() // public routes
        .anyRequest().authenticated());
        return http.build();
    }
}
