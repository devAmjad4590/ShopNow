package com.shopnow.cart_service.cart;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.concurrent.TimeUnit;

@Repository
@RequiredArgsConstructor
public class CartRepository {

    private static final String KEY_PREFIX = "cart:";

    @Value("${cart.ttl.days:7}")
    private long ttlDays;

    private final RedisTemplate<String, Cart> cartRedisTemplate;

    public Optional<Cart> findByUserId(String userId) {
        return Optional.ofNullable(cartRedisTemplate.opsForValue().get(KEY_PREFIX + userId));
    }

    public void save(Cart cart) {
        cartRedisTemplate.opsForValue().set(KEY_PREFIX + cart.getUserId(), cart, ttlDays, TimeUnit.DAYS);
    }

    public void deleteByUserId(String userId) {
        cartRedisTemplate.delete(KEY_PREFIX + userId);
    }
}
