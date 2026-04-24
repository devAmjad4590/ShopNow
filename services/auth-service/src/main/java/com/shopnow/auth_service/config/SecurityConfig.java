package com.shopnow.auth_service.config;

import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@RequiredArgsConstructor
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/v1/auth/**").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((req, res, e) ->
                    res.sendError(HttpServletResponse.SC_UNAUTHORIZED))
                .accessDeniedHandler((req, res, e) ->
                    res.sendError(HttpServletResponse.SC_FORBIDDEN)));
        return http.build();
    }
}
