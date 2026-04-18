package com.shopnow.api_gateway.filter;

import lombok.RequiredArgsConstructor;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

// GlobalFilter = run this filter on every request passing through the gateway
// Ordered = lets us control priority; -1 means run before built-in gateway filters
@Component
@RequiredArgsConstructor
public class JWTAuthenticationFilter implements GlobalFilter, Ordered {

    private final JWTService jwtService;

    // exchange = the full HTTP context (request + response) for this one request
    // chain = the remaining filter pipeline after this filter
    // Mono<Void> = reactive "promise of completion" — gateway is non-blocking (WebFlux)
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getURI().getPath();

        // /auth/** routes are public — no token needed (login, register, refresh)
        if (path.startsWith("/auth/")) {
            return chain.filter(exchange); // pass through to next filter → downstream service
        }

        // read the Authorization header from the incoming request
        String authHeader = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);

        // header missing or not a Bearer token → reject immediately with 401
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete(); // end response, send nothing
        }

        // strip "Bearer " prefix (7 chars) to get the raw JWT string
        String token = authHeader.substring(7);

        // invalid signature or expired → reject with 401
        if (!jwtService.isTokenValid(token)) {
            exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete();
        }

        // inject caller identity headers so downstream services don't need to re-parse JWT
        ServerHttpRequest mutated = exchange.getRequest().mutate()
                .header("X-User-Id",   String.valueOf(jwtService.extractUserId(token)))
                .header("X-User-Role", jwtService.extractRole(token))
                .build();
        return chain.filter(exchange.mutate().request(mutated).build());
    }

    // -1 = run before Spring Cloud Gateway's own built-in filters
    @Override
    public int getOrder() {
        return -1;
    }
}
