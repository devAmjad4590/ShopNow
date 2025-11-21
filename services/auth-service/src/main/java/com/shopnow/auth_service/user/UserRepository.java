package com.shopnow.auth_service.user;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface UserRepository extends JpaRepository<User, Integer> {

    // Spring boot uses this pattern "findBy<Field>" in which it automatically creates a query for you without dealing
    // with sql queries. so it will perform `SELECT u FROM User u WHERE u.email = :email` for you.
    // and the Optional<User> is for avoid null checks and safely deal with missing users.
    // if empty, it will return an empty Optional Object , else it will return a user, Optional<User>.
    // later the .orElseThrow will return the actual value or just return some exception
    Optional<User> findByEmail(String email);
}
