package com.shopnow.user_service.address;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface AddressRepository extends JpaRepository<Address, Integer> {
    List<Address> findAllByAuthUserId(Integer authUserId);
    Optional<Address> findByIdAndAuthUserId(Integer id, Integer authUserId);
}
