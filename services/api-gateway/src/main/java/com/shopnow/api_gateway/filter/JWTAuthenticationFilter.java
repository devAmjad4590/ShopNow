package com.shopnow.api_gateway.filter;

import lombok.RequiredArgsConstructor;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
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
        HttpMethod method = exchange.getRequest().getMethod();

        // Only enforce auth on explicitly protected routes.
        // Anything else passes through — unknown paths get a natural 404 from the router.
        boolean requiresAuth = path.startsWith("/users/")
                || (!HttpMethod.GET.equals(method)
                    && (path.startsWith("/products") || path.startsWith("/categories")));

        // read the Authorization header from the incoming request
        String authHeader = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        String token = (authHeader != null && authHeader.startsWith("Bearer "))
                ? authHeader.substring(7) : null;
        boolean tokenValid = token != null && jwtService.isTokenValid(token);

        if (requiresAuth && !tokenValid) {
            exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete();
        }

        if (!tokenValid) {
            return chain.filter(exchange);
        }

        // inject caller identity headers — use Decorator because Netty headers are read-only
        Integer userId = jwtService.extractUserId(token);
        String role = jwtService.extractRole(token);
        HttpHeaders headers = new HttpHeaders();
        headers.addAll(exchange.getRequest().getHeaders());
        headers.set("X-User-Id",   String.valueOf(userId));
        headers.set("X-User-Role", role);
        ServerHttpRequest mutated = new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public HttpHeaders getHeaders() { return headers; }
        };
        return chain.filter(exchange.mutate().request(mutated).build());
    }

    // -1 = run before Spring Cloud Gateway's own built-in filters
    @Override
    public int getOrder() {
        return -1;
    }
}
